"""Asynchronous client for the isolated persistent XTTS worker."""

import asyncio
import base64
import collections
import json
import logging
import os
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any
import uuid

from leonidas import capabilities
from leonidas.cascade import device as device_selection


WORKER_RESPONSE_LIMIT = 64 * 1024 * 1024
ProgressCallback = Callable[[str], Awaitable[None]]


class XttsWorkerSynthesizer:
  """Serializes XTTS requests and recreates poisoned workers deterministically."""

  sample_rate = 24000

  def __init__(
      self,
      *,
      voices: dict[str, Path],
      device: str = 'auto',
      model_id: str = capabilities.XTTS_V2_MODEL,
      python: Path | None = None,
      tts_home: Path | None = None,
      worker_module: str = 'leonidas.cascade.xtts_worker',
      worker_cwd: Path | None = None,
      timeout: float = 180.0,
  ):
    self._voices = dict(voices)
    self.device = device_selection.resolve_device(device)
    self.model_id = model_id
    repository = Path(__file__).resolve().parents[2]
    configured = os.environ.get('LEONIDAS_XTTS_PYTHON')
    self._python = python or (
        Path(configured)
        if configured
        else repository / '.venv-xtts' / 'bin' / 'python'
    )
    self._process: asyncio.subprocess.Process | None = None
    self._worker_module = worker_module
    self._worker_cwd = worker_cwd or repository
    self._tts_home = tts_home or Path(
        os.environ.get('TTS_HOME', Path.home() / '.local' / 'share' / 'tts')
    )
    self._lock = asyncio.Lock()
    self._stderr_task: asyncio.Task[None] | None = None
    self._timeout = timeout
    self._diagnostics: collections.deque[str] = collections.deque(maxlen=40)

  async def _start(self) -> asyncio.subprocess.Process:
    if self._process is not None and self._process.returncode is None:
      return self._process
    if self._process is not None:
      await self._invalidate_worker(self._process)
    self.validate_runtime()
    self._process = await asyncio.create_subprocess_exec(
        str(self._python),
        '-m',
        self._worker_module,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=self._worker_cwd,
        limit=WORKER_RESPONSE_LIMIT,
    )
    self._stderr_task = asyncio.create_task(self._consume_stderr(self._process))
    return self._process

  def validate_runtime(self) -> None:
    if not self._python.is_file():
      raise RuntimeError(
          'XTTS runtime is missing. Run leonidas/cascade/install_xtts.sh.'
      )
    agreement = (
        self._tts_home
        / 'tts_models--multilingual--multi-dataset--xtts_v2'
        / 'tos_agreed.txt'
    )
    if not agreement.is_file():
      raise RuntimeError(
          'XTTS CPML terms have not been accepted. Run '
          '`.venv-xtts/bin/python -m TTS.bin.synthesize --model_name '
          'tts_models/multilingual/multi-dataset/xtts_v2 --text teste '
          '--speaker_wav leonidas/.runtime/voices/leonidas.wav '
          '--language_idx pt --use_cuda '
          '--out_path /tmp/leonidas-xtts-test.wav` and '
          'review the license prompt.'
      )
    for voice_id, path in self._voices.items():
      if not path.is_file():
        raise RuntimeError(f'XTTS voice reference is missing: {voice_id!r}')

  async def _consume_stderr(self, process: asyncio.subprocess.Process) -> None:
    if process.stderr is None:
      return
    while line := await process.stderr.readline():
      value = line.decode('utf-8', errors='replace').strip()
      if value:
        self._diagnostics.append(value[-2000:])

  async def synthesize(
      self, text: str, *, voice_id: str, language: str
  ) -> bytes:
    voice = self._voices.get(voice_id)
    if voice is None or not voice.is_file():
      raise ValueError(f'Unknown or unavailable voice_id: {voice_id!r}')
    if language != 'pt':
      raise ValueError('XTTS language must be pt')
    response = await self._request(
        {
            'op': 'synthesize',
            'model_id': self.model_id,
            'device': self.device,
            'text': text.strip()[:12000],
            'speaker_wav': str(voice.resolve()),
            'language': language,
        }
    )
    return base64.b64decode(response['audio'], validate=True)

  async def load(
      self, progress: ProgressCallback | None = None
  ) -> dict[str, Any]:
    """Loads and warms the persistent worker before a session starts."""
    self.validate_runtime()
    if not self._voices:
      raise RuntimeError('XTTS requires at least one configured voice')
    voice = next(iter(self._voices.values()))
    response = await self._request(
        {
            'op': 'load',
            'model_id': self.model_id,
            'device': self.device,
            'speaker_wav': str(voice.resolve()),
            'language': 'pt',
        },
        progress=progress,
    )
    return {
        name: response.get(name)
        for name in (
            'device',
            'gpu_name',
            'memory_allocated_mib',
            'memory_reserved_mib',
        )
    }

  async def _request(
      self,
      payload: dict[str, Any],
      *,
      progress: ProgressCallback | None = None,
  ) -> dict[str, Any]:
    async with self._lock:
      process = await self._start()
      if process.stdin is None or process.stdout is None:
        await self._invalidate_worker(process)
        raise RuntimeError('XTTS worker pipes are unavailable')
      request_id = uuid.uuid4().hex
      request = {'id': request_id, **payload}
      response_task: asyncio.Task[dict[str, Any]] | None = None
      try:
        process.stdin.write(
            (json.dumps(request, ensure_ascii=False) + '\n').encode()
        )
        await process.stdin.drain()
        response_task = asyncio.create_task(
            self._read_response(process, request_id, progress)
        )
        response = await asyncio.wait_for(
            response_task, timeout=self._timeout
        )
        if payload.get('op') == 'synthesize':
          encoded_audio = response.get('audio')
          if not isinstance(encoded_audio, str):
            raise ValueError('XTTS worker returned no base64 audio')
          base64.b64decode(encoded_audio, validate=True)
        return response
      except asyncio.CancelledError:
        if response_task is not None:
          response_task.cancel()
          await asyncio.gather(response_task, return_exceptions=True)
        await self._invalidate_worker(process)
        raise
      except TimeoutError:
        if response_task is not None:
          response_task.cancel()
          await asyncio.gather(response_task, return_exceptions=True)
        await self._invalidate_worker(process)
        raise
      except (BrokenPipeError, ConnectionResetError):
        await self._invalidate_worker(process)
        raise RuntimeError('XTTS worker connection was lost') from None
      except (
          json.JSONDecodeError,
          UnicodeDecodeError,
          ValueError,
          RuntimeError,
      ):
        await self._invalidate_worker(process)
        raise

  async def _read_response(
      self,
      process: asyncio.subprocess.Process,
      request_id: str,
      progress: ProgressCallback | None,
  ) -> dict[str, Any]:
    if process.stdout is None:
      raise RuntimeError('XTTS worker stdout is unavailable')
    while True:
      line = await process.stdout.readline()
      if not line:
        raise RuntimeError(
            f'XTTS worker exited unexpectedly with {process.returncode}'
        )
      response = json.loads(line)
      if response.get('id') != request_id:
        raise RuntimeError('XTTS worker response id mismatch')
      if response.get('type') == 'event':
        if progress is not None:
          await progress(str(response.get('phase', 'loading')))
        continue
      if response.get('error'):
        logging.error(
            'XTTS worker error=%s diagnostics_tail=%r',
            response['error'],
            list(self._diagnostics)[-10:],
        )
        raise RuntimeError(
            f'XTTS worker failed: {response["error"]}: '
            f'{response.get("message", "")}'
        )
      return response

  async def _invalidate_worker(
      self, process: asyncio.subprocess.Process | None = None
  ) -> None:
    target = process or self._process
    if target is self._process:
      self._process = None
    if target is not None:
      if target.stdin is not None:
        try:
          target.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
          pass
      if target.returncode is None:
        try:
          target.terminate()
        except ProcessLookupError:
          pass
        try:
          await asyncio.wait_for(target.wait(), timeout=2)
        except asyncio.TimeoutError:
          try:
            target.kill()
          except ProcessLookupError:
            pass
          await target.wait()
    stderr_task = self._stderr_task
    self._stderr_task = None
    if stderr_task is not None:
      await asyncio.gather(stderr_task, return_exceptions=True)

  async def close(self) -> None:
    async with self._lock:
      await self._invalidate_worker()
