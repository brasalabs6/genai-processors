"""Opt-in Chromium WebRTC smoke using the private Gemini audio corpus."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request
import wave

from leonidas.e2e import assets
from leonidas.e2e import codex_audio_corpus
from leonidas.e2e import codex_audio_smoke


@dataclasses.dataclass(frozen=True)
class CombinedAudioInfo:
  turns: int
  duration_seconds: float


@dataclasses.dataclass(frozen=True)
class BrowserResult:
  passed: bool
  code: str
  user_messages: int
  model_messages: int


def browser_ready(snapshot: dict[str, Any]) -> bool:
  """Return whether the standalone UI completed both startup handshakes."""
  return (
      snapshot.get('rest') == 'API online'
      and snapshot.get('websocket') == 'WebSocket online'
  )


def combine_microphone_audio(
    paths: tuple[Path, ...],
    output: Path,
    *,
    silence_seconds: float = 2.0,
) -> CombinedAudioInfo:
  """Combine corpus turns with silence so browser VAD sees separate turns."""
  if len(paths) < 2:
    raise ValueError('WebRTC smoke requires at least two audio turns')
  if not 0.5 <= silence_seconds <= 10:
    raise ValueError('Inter-turn silence must be between 0.5 and 10 seconds')
  frames: list[bytes] = []
  for path in paths:
    assets.validate_audio(path)
    with wave.open(str(path), 'rb') as source:
      frames.append(source.readframes(source.getnframes()))
  silence = bytes(round(24000 * 2 * silence_seconds))
  payload = silence.join(frames)
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_suffix('.wav.tmp')
  with wave.open(str(temporary), 'wb') as target:
    target.setnchannels(1)
    target.setsampwidth(2)
    target.setframerate(24000)
    target.writeframes(payload)
  os.replace(temporary, output)
  return CombinedAudioInfo(len(paths), len(payload) / (24000 * 2))


def evaluate_snapshot(snapshot: dict[str, Any]) -> BrowserResult:
  """Classify bounded DOM state without retaining conversation or errors."""
  users = int(snapshot.get('userMessages') or 0)
  models = int(snapshot.get('modelMessages') or 0)
  if users >= 2 and models >= 2:
    return BrowserResult(True, 'ok', users, models)
  detail = str(snapshot.get('errorDetail') or '').lower()
  if 'voice access denied' in detail or 'voice entitlement' in detail:
    code = 'voice_entitlement_denied'
  elif 'tempo esgotado' in detail or 'timeout' in detail:
    code = 'signaling_timeout'
  elif not bool(snapshot.get('errorHidden', True)):
    code = 'browser_session_error'
  else:
    code = 'turns_incomplete'
  return BrowserResult(False, code, users, models)


def _free_port() -> int:
  with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    return int(listener.getsockname()[1])


def _request_json(
    url: str, *, method: str = 'GET', payload: dict[str, Any] | None = None
) -> dict[str, Any]:
  data = None if payload is None else json.dumps(payload).encode('utf-8')
  request = urllib.request.Request(
      url,
      data=data,
      method=method,
      headers={'Content-Type': 'application/json'} if data else {},
  )
  with urllib.request.urlopen(request, timeout=5) as response:
    envelope = json.load(response)
  if envelope.get('error'):
    raise RuntimeError('Leonidas control API rejected the smoke request')
  result = envelope.get('data')
  if not isinstance(result, dict):
    raise RuntimeError('Leonidas control API returned an invalid envelope')
  return result


async def _wait_http(url: str, process: subprocess.Popen[bytes]) -> None:
  deadline = time.monotonic() + 15
  while time.monotonic() < deadline:
    if process.poll() is not None:
      raise RuntimeError('Leonidas exited during WebRTC smoke startup')
    try:
      await asyncio.to_thread(_request_json, url)
      return
    except (OSError, RuntimeError, urllib.error.URLError):
      await asyncio.sleep(0.1)
  raise TimeoutError('Leonidas did not become ready for WebRTC smoke')


async def _wait_devtools(port: int) -> str:
  url = f'http://127.0.0.1:{port}/json/list'
  deadline = time.monotonic() + 15
  while time.monotonic() < deadline:
    try:
      with urllib.request.urlopen(url, timeout=2) as response:
        pages = json.load(response)
      if pages and isinstance(pages[0].get('webSocketDebuggerUrl'), str):
        return str(pages[0]['webSocketDebuggerUrl'])
    except (OSError, KeyError, urllib.error.URLError):
      pass
    await asyncio.sleep(0.1)
  raise TimeoutError('Chromium DevTools did not become ready')


class _CdpClient:

  def __init__(self, connection: Any):
    self._connection = connection
    self._next_id = 0

  async def call(
      self, method: str, params: dict[str, Any] | None = None
  ) -> dict[str, Any]:
    self._next_id += 1
    request_id = self._next_id
    await self._connection.send(
        json.dumps({'id': request_id, 'method': method, 'params': params or {}})
    )
    while True:
      message = json.loads(await self._connection.recv())
      if message.get('id') == request_id:
        return message


async def _run_browser(debugger_url: str, *, timeout: float) -> BrowserResult:
  import websockets

  origin = 'http://127.0.0.1'
  async with websockets.connect(debugger_url, origin=origin) as connection:
    cdp = _CdpClient(connection)
    await cdp.call('Runtime.enable')
    readiness_expression = """JSON.stringify({
      rest: document.querySelector('#rest-status')?.textContent || '',
      websocket: document.querySelector('#ws-status')?.textContent || ''
    })"""
    readiness_deadline = time.monotonic() + 15
    while time.monotonic() < readiness_deadline:
      response = await cdp.call(
          'Runtime.evaluate',
          {'expression': readiness_expression, 'returnByValue': True},
      )
      serialized = (
          response.get('result', {}).get('result', {}).get('value', '{}')
      )
      if browser_ready(json.loads(serialized)):
        break
      await asyncio.sleep(0.1)
    else:
      raise TimeoutError('Leonidas browser did not become ready')
    await cdp.call(
        'Runtime.evaluate',
        {'expression': "document.querySelector('#start-session').click()"},
    )
    deadline = time.monotonic() + timeout
    last_snapshot: dict[str, Any] = {}
    expression = """JSON.stringify({
      session: document.querySelector('#session-status')?.textContent || '',
      errorHidden: document.querySelector('#error-banner')?.hidden ?? true,
      errorDetail: document.querySelector('#error-detail')?.textContent || '',
      userMessages: document.querySelectorAll('.message.user').length,
      modelMessages: document.querySelectorAll('.message.model').length
    })"""
    while time.monotonic() < deadline:
      response = await cdp.call(
          'Runtime.evaluate',
          {'expression': expression, 'returnByValue': True},
      )
      serialized = (
          response.get('result', {}).get('result', {}).get('value', '{}')
      )
      last_snapshot = json.loads(serialized)
      result = evaluate_snapshot(last_snapshot)
      if result.passed or result.code not in {'turns_incomplete'}:
        return result
      await asyncio.sleep(0.5)
    return evaluate_snapshot(last_snapshot)


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
  if process is None or process.poll() is not None:
    return
  process.terminate()
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    process.kill()
    process.wait(timeout=5)


async def run(corpus: Path, timeout: float) -> BrowserResult:
  chromium = shutil.which('chromium') or shutil.which('google-chrome')
  if chromium is None:
    raise RuntimeError('Chromium is required for the Codex WebRTC smoke')
  paths = codex_audio_smoke.load_corpus(corpus)
  combined = corpus / 'webrtc-multiturn.wav'
  combine_microphone_audio(paths, combined)
  web_port, websocket_port, debugger_port = (
      _free_port(),
      _free_port(),
      _free_port(),
  )
  server: subprocess.Popen[bytes] | None = None
  browser: subprocess.Popen[bytes] | None = None
  with tempfile.TemporaryDirectory(prefix='leonidas-codex-webrtc-') as temp_dir:
    temporary = Path(temp_dir)
    try:
      server = subprocess.Popen(
          [
              sys.executable,
              '-m',
              'leonidas',
              '--web-port',
              str(web_port),
              '--websocket-port',
              str(websocket_port),
              '--runtime-dir',
              str(temporary / 'runtime'),
              '--log-dir',
              str(temporary / 'logs'),
          ],
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )
      base_url = f'http://127.0.0.1:{web_port}'
      await _wait_http(f'{base_url}/api/v1/config', server)
      config = await asyncio.to_thread(
          _request_json, f'{base_url}/api/v1/config'
      )
      await asyncio.to_thread(
          _request_json,
          f'{base_url}/api/v1/config/draft',
          method='PUT',
          payload={
              'expected_revision': config['revision'],
              'updates': {
                  'pipeline_id': 'codex_realtime',
                  'model_id': 'gpt-realtime-1.5',
                  'voice_name': 'cove',
              },
          },
      )
      await asyncio.to_thread(
          _request_json,
          f'{base_url}/api/v1/config/apply',
          method='POST',
          payload={},
      )
      origin = 'http://127.0.0.1'
      browser = subprocess.Popen(
          [
              chromium,
              '--headless=new',
              '--disable-gpu',
              '--no-first-run',
              '--no-default-browser-check',
              '--autoplay-policy=no-user-gesture-required',
              '--use-fake-ui-for-media-stream',
              '--use-fake-device-for-media-stream',
              f'--use-file-for-fake-audio-capture={combined.resolve()}',
              f'--remote-debugging-port={debugger_port}',
              f'--remote-allow-origins={origin}',
              f'--user-data-dir={temporary / "chromium"}',
              (
                  f'{base_url}/?ws=ws://127.0.0.1:{websocket_port}'
                  '/api/v1/live'
              ),
          ],
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )
      debugger_url = await _wait_devtools(debugger_port)
      return await _run_browser(debugger_url, timeout=timeout)
    finally:
      _terminate(browser)
      _terminate(server)


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--corpus', type=Path, default=codex_audio_corpus.DEFAULT_ROOT
  )
  parser.add_argument('--timeout', type=float, default=45)
  args = parser.parse_args(argv)
  if os.environ.get('LEONIDAS_RUN_CODEX_WEBRTC_E2E') != '1':
    print(
        'codex_webrtc_smoke_skipped=true '
        'set LEONIDAS_RUN_CODEX_WEBRTC_E2E=1 to run'
    )
    return 0
  try:
    result = asyncio.run(run(args.corpus, args.timeout))
  except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
    print(
        'codex_webrtc_smoke_failed=true'
        f' error_type={type(exc).__name__}'
        ' error_code=runner_failure'
    )
    return 2
  status = 'ok' if result.passed else 'failed'
  print(
      f'codex_webrtc_smoke_{status}=true'
      f' error_code={result.code}'
      f' user_turns={result.user_messages}'
      f' model_turns={result.model_messages}'
  )
  return 0 if result.passed else 2


if __name__ == '__main__':
  raise SystemExit(main())
