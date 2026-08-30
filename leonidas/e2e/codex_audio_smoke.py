"""Opt-in multi-turn Codex realtime smoke using Gemini microphone fixtures."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
import json
import os
from pathlib import Path
import time
from typing import Any

from leonidas import codex_app_server
from leonidas import codex_auth
from leonidas.e2e import assets
from leonidas.e2e import codex_audio_corpus
from leonidas.pipelines import codex_realtime


Sleep = Callable[[float], Awaitable[None]]


def failure_code(exc: BaseException) -> str:
  """Return a bounded public code without serializing provider diagnostics."""
  message = str(exc).lower()
  if 'requires api key auth' in message:
    return 'api_key_required'
  if 'unknown variant' in message or 'version must be' in message:
    return 'protocol_version_unsupported'
  if 'voice access denied' in message or 'voice entitlement' in message:
    return 'voice_entitlement_denied'
  if isinstance(exc, TimeoutError):
    return 'turn_timeout'
  return 'codex_realtime_failed'


def load_corpus(root: Path) -> tuple[Path, ...]:
  manifest_path = root / 'manifest.json'
  try:
    manifest = json.loads(manifest_path.read_text())
    turns = manifest['turns']
  except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
    raise ValueError('Codex audio corpus manifest is invalid') from exc
  if manifest.get('schema_version') != 1 or not isinstance(turns, list):
    raise ValueError('Codex audio corpus schema is unsupported')
  paths: list[Path] = []
  for turn in turns:
    filename = turn.get('file') if isinstance(turn, dict) else None
    if not isinstance(filename, str) or Path(filename).name != filename:
      raise ValueError('Codex audio corpus contains an invalid filename')
    path = root / filename
    assets.validate_audio(path)
    paths.append(path)
  if len(paths) < 2:
    raise ValueError('Codex audio corpus requires at least two turns')
  return tuple(paths)


async def stream_microphone_turn(
    client: Any,
    path: Path,
    *,
    chunk_ms: int = 100,
    trailing_silence_ms: int = 900,
    sleep: Sleep = asyncio.sleep,
) -> None:
  """Send one WAV as paced PCM16/16 kHz plus endpointing silence."""
  if chunk_ms <= 0 or trailing_silence_ms < 0:
    raise ValueError('Microphone pacing values must be non-negative')
  pcm = assets.audio_as_pcm16_16khz(path)
  chunk_bytes = 16000 * 2 * chunk_ms // 1000
  for offset in range(0, len(pcm), chunk_bytes):
    await client.append_audio(
        pcm[offset : offset + chunk_bytes],
        sample_rate=16000,
        num_channels=1,
    )
    await sleep(chunk_ms / 1000)
  silence_chunks = (trailing_silence_ms + chunk_ms - 1) // chunk_ms
  for _ in range(silence_chunks):
    await client.append_audio(
        bytes(chunk_bytes), sample_rate=16000, num_channels=1
    )
    await sleep(chunk_ms / 1000)


async def wait_for_assistant_turn(
    client: codex_app_server.CodexRealtimeClient, *, timeout: float
) -> tuple[int, int]:
  transcript_events = 0
  audio_bytes = 0

  async def consume() -> None:
    nonlocal transcript_events, audio_bytes
    while True:
      notification = await client.next_notification()
      if terminal_error := client.terminal_notification_error(notification):
        raise terminal_error
      method = notification.get('method')
      params = notification.get('params') or {}
      if method == 'thread/realtime/outputAudio/delta':
        audio = params.get('audio') or {}
        data = audio.get('data')
        if isinstance(data, str):
          import base64

          audio_bytes += len(base64.b64decode(data, validate=True))
      elif method == 'thread/realtime/transcript/done':
        transcript_events += 1
        if str(params.get('role', '')).lower() in {
            'assistant',
            'model',
        }:
          return

  await asyncio.wait_for(consume(), timeout=timeout)
  return transcript_events, audio_bytes


async def run(root: Path, version: str, timeout: float) -> None:
  paths = load_corpus(root)
  started = time.perf_counter()
  client, cleanup = await codex_realtime._open_client()
  completed_turns = 0
  transcript_events = 0
  audio_bytes = 0
  voice = 'marin' if version == 'v2' else 'cove'
  try:
    await client.start_realtime(
        objective=(
            'Converse em português e responda brevemente a cada fala do '
            'usuário. Considere o contexto dos turnos anteriores.'
        ),
        model='gpt-realtime-1.5' if version != 'v3' else None,
        voice=voice,
        version=version,
    )
    for path in paths:
      await stream_microphone_turn(client, path)
      transcripts, output_bytes = await wait_for_assistant_turn(
          client, timeout=timeout
      )
      transcript_events += transcripts
      audio_bytes += output_bytes
      completed_turns += 1
    await client.stop_realtime()
  finally:
    await cleanup()
  print(
      'codex_audio_smoke_ok=true'
      f' turns={completed_turns}'
      f' transcript_events={transcript_events}'
      f' output_audio_bytes={audio_bytes}'
      f' version={version}'
      f' elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--corpus', type=Path, default=codex_audio_corpus.DEFAULT_ROOT
  )
  parser.add_argument('--version', choices=('v1', 'v2', 'v3'), default='v2')
  parser.add_argument('--turn-timeout', type=float, default=30)
  args = parser.parse_args(argv)
  if os.environ.get('LEONIDAS_RUN_CODEX_AUDIO_E2E') != '1':
    print(
        'codex_audio_smoke_skipped=true '
        'set LEONIDAS_RUN_CODEX_AUDIO_E2E=1 to run'
    )
    return 0
  try:
    asyncio.run(run(args.corpus, args.version, args.turn_timeout))
  except (
      ValueError,
      codex_auth.CodexAuthError,
      codex_app_server.CodexProtocolError,
      TimeoutError,
  ) as exc:
    print(
        'codex_audio_smoke_failed=true'
        f' error_type={type(exc).__name__}'
        f' error_code={failure_code(exc)}'
    )
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
