"""Asynchronous client for the persistent Parakeet worker."""

import asyncio
import base64
from collections.abc import Awaitable, Callable
import collections
import json
import logging
from pathlib import Path
import sys
from typing import Any
import uuid

from leonidas import capabilities
from leonidas.cascade import device as device_selection


ProgressCallback = Callable[[str], Awaitable[None]]


class ParakeetWorkerTranscriber:
  """Keeps Parakeet isolated and recreates workers after protocol failures."""

  def __init__(
      self,
      *,
      model_id: str = capabilities.PARAKEET_V3_MODEL,
      device: str = 'auto',
      python: Path | None = None,
      worker_module: str = 'leonidas.cascade.parakeet_worker',
      worker_cwd: Path | None = None,
      timeout: float = 180.0,
  ):
    self.model_id = model_id
    self.device = device_selection.resolve_device(device)
    repository = Path(__file__).resolve().parents[2]
    self._python = python or Path(sys.executable)
    self._worker_module = worker_module
    self._worker_cwd = worker_cwd or repository
    self._timeout = timeout
    self._process: asyncio.subprocess.Process | None = None
    self._lock = asyncio.Lock()
    self._stderr_task: asyncio.Task[None] | None = None
    self._diagnostics: collections.deque[str] = collections.deque(maxlen=40)

  async def _start(self) -> asyncio.subprocess.Process:
    if self._process is not None and self._process.returncode is None:
      return self._process
    self._process = await asyncio.create_subprocess_exec(
        str(self._python),
        '-m',
        self._worker_module,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=self._worker_cwd,
    )
    self._stderr_task = asyncio.create_task(self._consume_stderr(self._process))
    return self._process

  async def _consume_stderr(self, process: asyncio.subprocess.Process) -> None:
    if process.stderr is None:
      return
    while line := await process.stderr.readline():
      value = line.decode('utf-8', errors='replace').strip()
      if value:
        self._diagnostics.append(value[-2000:])

  async def _read_response(
      self,
      process: asyncio.subprocess.Process,
      request_id: str,
      progress: ProgressCallback | None,
  ) -> dict[str, Any]:
    if process.stdout is None:
      raise RuntimeError('Parakeet worker stdout is unavailable')
    while line := await process.stdout.readline():
      response = json.loads(line)
      if response.get('id') != request_id:
        raise RuntimeError('Parakeet worker response id mismatch')
      if response.get('type') == 'event':
        if progress is not None:
          await progress(str(response.get('phase', 'loading')))
        continue
      if response.get('error'):
        logging.error(
            'Parakeet worker error=%s diagnostics_tail=%r',
            response['error'],
            list(self._diagnostics)[-10:],
        )
        raise RuntimeError(
            f'Parakeet worker failed: {response["error"]}: '
            f'{response.get("message", "")}'
        )
      return response
    raise RuntimeError(
        f'Parakeet worker exited unexpectedly with {process.returncode}'
    )

  async def _request(
      self,
      payload: dict[str, Any],
      *,
      progress: ProgressCallback | None = None,
  ) -> dict[str, Any]:
    async with self._lock:
      process = await self._start()
      if process.stdin is None:
        await self._invalidate_worker(process)
        raise RuntimeError('Parakeet worker stdin is unavailable')
      request_id = uuid.uuid4().hex
      request = {
          **payload,
          'id': request_id,
          'model_id': self.model_id,
          'device': self.device,
      }
      try:
        process.stdin.write(
            (json.dumps(request, ensure_ascii=True) + '\n').encode()
        )
        await process.stdin.drain()
        response_task = asyncio.create_task(
            self._read_response(process, request_id, progress)
        )
        try:
          return await asyncio.wait_for(response_task, timeout=self._timeout)
        except asyncio.CancelledError:
          response_task.cancel()
          await asyncio.gather(response_task, return_exceptions=True)
          await self._invalidate_worker(process)
          raise
        except TimeoutError:
          response_task.cancel()
          await asyncio.gather(response_task, return_exceptions=True)
          await self._invalidate_worker(process)
          raise
      except (BrokenPipeError, ConnectionResetError):
        await self._invalidate_worker(process)
        raise RuntimeError('Parakeet worker connection was lost') from None
      except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        await self._invalidate_worker(process)
        raise

  async def load(
      self, progress: ProgressCallback | None = None
  ) -> dict[str, Any]:
    response = await self._request({'op': 'load'}, progress=progress)
    return {
        name: response.get(name)
        for name in (
            'device',
            'gpu_name',
            'memory_allocated_mib',
            'memory_reserved_mib',
        )
    }

  async def transcribe(self, pcm16: bytes) -> str:
    response = await self._request(
        {
            'op': 'transcribe',
            'audio': base64.b64encode(pcm16).decode('ascii'),
        }
    )
    return str(response.get('text', '')).strip()

  async def _invalidate_worker(
      self, process: asyncio.subprocess.Process | None = None
  ) -> None:
    target = process or self._process
    if target is self._process:
      self._process = None
    if target is not None and target.returncode is None:
      if target.stdin is not None:
        target.stdin.close()
      target.terminate()
      try:
        await asyncio.wait_for(target.wait(), timeout=2)
      except asyncio.TimeoutError:
        target.kill()
        await target.wait()
    stderr_task = self._stderr_task
    self._stderr_task = None
    if stderr_task is not None:
      await asyncio.gather(stderr_task, return_exceptions=True)

  async def close(self) -> None:
    async with self._lock:
      await self._invalidate_worker()
