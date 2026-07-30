"""Asynchronous client for the isolated persistent XTTS worker."""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import uuid

from leonidas import capabilities
from leonidas.cascade import device as device_selection


WORKER_RESPONSE_LIMIT = 64 * 1024 * 1024


class XttsWorkerSynthesizer:

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
    self._drain_task: asyncio.Task[None] | None = None
    self._timeout = timeout

  async def _start(self) -> asyncio.subprocess.Process:
    if self._process is not None and self._process.returncode is None:
      return self._process
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
    line_count = 0
    while line := await process.stderr.readline():
      del line
      line_count += 1
    if line_count:
      logging.debug('XTTS worker emitted diagnostic_lines=%d', line_count)

  async def synthesize(
      self, text: str, *, voice_id: str, language: str
  ) -> bytes:
    voice = self._voices.get(voice_id)
    if voice is None or not voice.is_file():
      raise ValueError(f'Unknown or unavailable voice_id: {voice_id!r}')
    if language != 'pt':
      raise ValueError('XTTS language must be pt')
    await self._lock.acquire()
    release_lock = True
    try:
      process = await self._start()
      if process.stdin is None or process.stdout is None:
        raise RuntimeError('XTTS worker pipes are unavailable')
      request_id = uuid.uuid4().hex
      payload = {
          'id': request_id,
          'model_id': self.model_id,
          'device': self.device,
          'text': text.strip()[:12000],
          'speaker_wav': str(voice.resolve()),
          'language': language,
      }
      process.stdin.write(
          (json.dumps(payload, ensure_ascii=False) + '\n').encode()
      )
      await process.stdin.drain()
      response_task = asyncio.create_task(process.stdout.readline())
      try:
        line = await asyncio.wait_for(
            asyncio.shield(response_task), timeout=self._timeout
        )
      except (asyncio.CancelledError, TimeoutError):
        release_lock = False
        self._drain_task = asyncio.create_task(
            self._drain_cancelled_response(response_task)
        )
        raise
      if not line:
        raise RuntimeError(
            f'XTTS worker exited unexpectedly with {process.returncode}'
        )
      response = json.loads(line)
      if response.get('id') != request_id:
        raise RuntimeError('XTTS worker response id mismatch')
      if response.get('error'):
        raise RuntimeError(
            f'XTTS worker failed: {response["error"]}: '
            f'{response.get("message", "")}'
        )
      return base64.b64decode(response['audio'], validate=True)
    finally:
      if release_lock:
        self._lock.release()

  async def _drain_cancelled_response(
      self, response_task: asyncio.Task[bytes]
  ) -> None:
    try:
      await response_task
    finally:
      self._lock.release()

  async def close(self) -> None:
    process = self._process
    self._process = None
    if process is not None and process.returncode is None:
      if process.stdin is not None:
        process.stdin.close()
      try:
        await asyncio.wait_for(process.wait(), timeout=2)
      except asyncio.TimeoutError:
        process.terminate()
        await process.wait()
    if self._drain_task is not None:
      await asyncio.gather(self._drain_task, return_exceptions=True)
      self._drain_task = None
    if self._stderr_task is not None:
      await asyncio.gather(self._stderr_task, return_exceptions=True)
      self._stderr_task = None
