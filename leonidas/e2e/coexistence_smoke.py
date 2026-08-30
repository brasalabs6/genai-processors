"""Empirical Parakeet, XTTS, and Pyannote CUDA coexistence smoke."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from leonidas import capabilities
from leonidas.cascade import diarization_process
from leonidas.cascade import resources
from leonidas.cascade import xtts_process
from leonidas.e2e import assets
from leonidas.e2e import cascade_smoke
from leonidas.e2e import diarization_corpus


MemoryProbe = Callable[[str], dict[str, Any]]
CascadeRunner = Callable[..., Awaitable[None]]


def failure_code(exc: Exception) -> str:
  if isinstance(exc, diarization_process.DiarizationWorkerError):
    return 'diarization_unavailable_or_unauthorized'
  if isinstance(exc, xtts_process.XttsResourceError):
    return 'insufficient_system_memory'
  if isinstance(exc, xtts_process.XttsWorkerCrashedError):
    return 'tts_worker_crashed'
  if isinstance(exc, ValueError):
    return 'invalid_configuration'
  return 'unexpected_runtime_failure'


def all_resources_ready(snapshot: dict[str, Any]) -> bool:
  states = {
      item['id']: item['state']
      for item in snapshot.get('components', [])
      if item.get('id') in ('stt', 'tts', 'diarization')
  }
  return snapshot.get('overall_state') == 'ready' and states == {
      'stt': 'ready',
      'tts': 'ready',
      'diarization': 'ready',
  }


def _meminfo_mib() -> tuple[int | None, int]:
  values: dict[str, int] = {}
  try:
    with open('/proc/meminfo', encoding='utf-8') as source:
      for line in source:
        name, raw = line.split(':', 1)
        if name in ('MemAvailable', 'SwapTotal'):
          values[name] = int(raw.strip().split()[0]) // 1024
  except (OSError, ValueError):
    pass
  return values.get('MemAvailable'), values.get('SwapTotal', 0)


def memory_snapshot(phase: str) -> dict[str, Any]:
  available, swap = _meminfo_mib()
  snapshot: dict[str, Any] = {
      'phase': phase,
      'system_available_mib': available,
      'swap_total_mib': swap,
      'gpu_used_mib': None,
      'gpu_free_mib': None,
  }
  try:
    result = subprocess.run(
        [
            'nvidia-smi',
            '--query-gpu=memory.used,memory.free',
            '--format=csv,noheader,nounits',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    used, free = result.stdout.strip().splitlines()[0].split(',')
    snapshot['gpu_used_mib'] = int(used.strip())
    snapshot['gpu_free_mib'] = int(free.strip())
  except (OSError, ValueError, subprocess.SubprocessError):
    pass
  print('coexistence_memory=' + json.dumps(snapshot, sort_keys=True))
  return snapshot


def _default_pool(voice_path: Path | None) -> resources.CascadeResources:
  voices = {'leonidas': voice_path} if voice_path is not None else {}
  return resources.CascadeResources(voices=voices)


async def run(
    *,
    audio: bytes,
    diarization_audio: bytes,
    voice_path: Path | None,
    device: str,
    turns: int = 3,
    pool_factory: Callable[[Path | None], Any] = _default_pool,
    cascade_runner: CascadeRunner = cascade_smoke.run_prepared,
    memory_probe: MemoryProbe = memory_snapshot,
) -> dict[str, Any]:
  if turns != 3:
    raise ValueError('coexistence smoke requires exactly three turns')
  pool = pool_factory(voice_path)
  measurements = [memory_probe('before_load')]
  try:
    snapshot = await pool.ensure_ready(
        capabilities.PARAKEET_V3_MODEL,
        capabilities.XTTS_V2_MODEL,
        device,
        diarization_enabled=True,
    )
    if not all_resources_ready(snapshot):
      raise RuntimeError('All three local resources did not reach ready state')
    measurements.append(memory_probe('models_ready'))
    diarizer = pool.diarizer(device)
    segments = await diarizer.diarize(diarization_audio, sample_rate=16000)
    speakers = {segment.speaker_id for segment in segments}
    if len(speakers) < 2:
      raise RuntimeError('Pyannote did not identify both corpus speakers')
    measurements.append(memory_probe('after_diarization'))
    await cascade_runner(pool, audio, device, turns, diarizer)
    measurements.append(memory_probe('complete'))
    return {
        'speakers': len(speakers),
        'segments': len(segments),
        'turns': turns,
        'measurements': measurements,
    }
  finally:
    try:
      await pool.close()
    finally:
      measurements.append(memory_probe('after_cleanup'))


async def _run_cli(args: argparse.Namespace) -> None:
  if not os.environ.get('GROQ_API_KEY'):
    raise ValueError('GROQ_API_KEY is required')
  audio = assets.audio_as_pcm16_16khz(args.audio)
  diarization_audio = assets.audio_as_pcm16_16khz(
      args.diarization_audio, max_duration_seconds=30.0
  )
  result = await run(
      audio=audio,
      diarization_audio=diarization_audio,
      voice_path=args.voice,
      device=args.device,
  )
  print(
      'coexistence_ok=true '
      f'speakers={result["speakers"]} segments={result["segments"]} '
      f'turns={result["turns"]}'
  )


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--audio', type=Path, default=cascade_smoke.DEFAULT_AUDIO)
  parser.add_argument('--voice', type=Path, default=cascade_smoke.DEFAULT_VOICE)
  parser.add_argument(
      '--diarization-audio',
      type=Path,
      default=diarization_corpus.DEFAULT_ROOT / 'two-speaker.wav',
  )
  parser.add_argument(
      '--device', choices=('auto', 'cuda', 'cpu'), default='cuda'
  )
  args = parser.parse_args(argv)
  try:
    asyncio.run(_run_cli(args))
  except Exception as exc:
    print(
        'coexistence_failed=true '
        f'error_code={failure_code(exc)} error_type={type(exc).__name__}'
    )
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
