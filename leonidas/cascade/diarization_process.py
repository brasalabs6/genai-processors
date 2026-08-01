"""Async client for the optional isolated Pyannote diarization worker."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import json
import os
from pathlib import Path
from typing import Any
import uuid

from leonidas.cascade import diarization


ProgressCallback = Callable[[str], Awaitable[None]]


class DiarizationWorkerError(RuntimeError):
  """The isolated diarization worker failed or became unavailable."""

  public_message = True


class PyannoteWorkerDiarizer:
  """Keeps optional Pyannote dependencies out of the server process."""

  def __init__(
      self,
      *,
      model_id: str = 'pyannote/speaker-diarization-community-1',
      device: str = 'auto',
      python: Path | None = None,
      worker_module: str = 'leonidas.cascade.diarization_worker',
      worker_cwd: Path | None = None,
      timeout: float = 180.0,
  ):
    self.model_id = model_id
    self.device = device
    repository = Path(__file__).resolve().parents[2]
    configured = os.environ.get('LEONIDAS_DIARIZATION_PYTHON')
    self._python = python or Path(
        configured or repository / '.venv-diarization' / 'bin' / 'python'
    )
    self._worker_module = worker_module
    self._worker_cwd = worker_cwd or repository
    self._timeout = timeout
    self._process: asyncio.subprocess.Process | None = None
    self._lock = asyncio.Lock()

  async def _start(self) -> asyncio.subprocess.Process:
    if self._process is not None and self._process.returncode is None:
      return self._process
    if not self._python.is_file():
      raise DiarizationWorkerError(
          'Diarization runtime is missing. Configure '
          'LEONIDAS_DIARIZATION_PYTHON.'
      )
    self._process = await asyncio.create_subprocess_exec(
        str(self._python),
        '-m',
        self._worker_module,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=self._worker_cwd,
    )
    return self._process

  async def _request(
      self,
      payload: dict[str, Any],
      *,
      progress: ProgressCallback | None = None,
  ) -> dict[str, Any]:
    async with self._lock:
      process = await self._start()
      if process.stdin is None or process.stdout is None:
        await self._invalidate(process)
        raise DiarizationWorkerError('Diarization worker pipes are unavailable')
      request_id = uuid.uuid4().hex
      process.stdin.write(
          (json.dumps({'id': request_id, **payload}) + '\n').encode('utf-8')
      )
      await process.stdin.drain()
      try:
        while True:
          line = await asyncio.wait_for(
              process.stdout.readline(), timeout=self._timeout
          )
          if not line:
            raise DiarizationWorkerError(
                f'Diarization worker exited with {process.returncode}'
            )
          response = json.loads(line)
          if response.get('id') != request_id:
            raise DiarizationWorkerError(
                'Diarization worker response id mismatch'
            )
          if response.get('type') == 'event':
            if progress is not None:
              await progress(str(response.get('phase', 'loading')))
            continue
          if response.get('error'):
            raise DiarizationWorkerError(
                f'Diarization worker failed: {response["error"]}'
            )
          return response
      except asyncio.CancelledError:
        await self._invalidate(process)
        raise
      except DiarizationWorkerError:
        await self._invalidate(process)
        raise
      except (BrokenPipeError, ConnectionResetError, TimeoutError, ValueError):
        await self._invalidate(process)
        raise DiarizationWorkerError(
            'Diarization worker protocol or timeout failure'
        ) from None

  async def load(
      self, progress: ProgressCallback | None = None
  ) -> dict[str, Any]:
    response = await self._request(
        {'op': 'load', 'model_id': self.model_id, 'device': self.device},
        progress=progress,
    )
    return {
        name: response.get(name)
        for name in (
            'device',
            'gpu_name',
            'memory_allocated_mib',
            'memory_reserved_mib',
            'model_id',
        )
    }

  async def diarize(
      self, audio: bytes, *, sample_rate: int
  ) -> list[diarization.SpeakerSegment]:
    response = await self._request(
        {
            'op': 'diarize',
            'sample_rate': sample_rate,
            'audio': base64.b64encode(audio).decode('ascii'),
        }
    )
    raw_segments = response.get('segments', [])
    if not isinstance(raw_segments, list):
      raise DiarizationWorkerError(
          'Diarization worker returned invalid segments'
      )
    return [
        diarization.SpeakerSegment(
            speaker_id=str(item['speaker_id']),
            start=float(item['start']),
            end=float(item['end']),
            confidence=(
                float(item['confidence'])
                if item.get('confidence') is not None
                else None
            ),
        )
        for item in raw_segments
    ]

  async def _invalidate(
      self, process: asyncio.subprocess.Process | None = None
  ) -> None:
    target = process or self._process
    if target is self._process:
      self._process = None
    if target is not None and target.returncode is None:
      try:
        target.terminate()
        await asyncio.wait_for(target.wait(), timeout=2)
      except (ProcessLookupError, asyncio.TimeoutError):
        try:
          target.kill()
        except ProcessLookupError:
          pass
        await target.wait()

  async def close(self) -> None:
    async with self._lock:
      await self._invalidate()


def default_python() -> Path:
  repository = Path(__file__).resolve().parents[2]
  configured = os.environ.get('LEONIDAS_DIARIZATION_PYTHON')
  return Path(configured or repository / '.venv-diarization' / 'bin' / 'python')
