"""Opt-in real Pyannote diarization smoke over a synthetic two-speaker WAV."""

from __future__ import annotations

import asyncio
import argparse
import os
from pathlib import Path
import time

from leonidas.cascade import diarization_process
from leonidas.e2e import assets
from leonidas.e2e import diarization_corpus


async def run(audio_path: Path) -> None:
  started = time.perf_counter()
  pcm = assets.audio_as_pcm16_16khz(audio_path, max_duration_seconds=30.0)
  adapter = diarization_process.PyannoteWorkerDiarizer(
      device=os.environ.get('LEONIDAS_DIARIZATION_DEVICE', 'auto')
  )
  segments = await adapter.diarize(pcm, sample_rate=16000)
  speakers = sorted({segment.speaker_id for segment in segments})
  if len(speakers) < 2:
    raise RuntimeError('Pyannote did not identify both corpus speakers')
  print(
      'diarization_smoke_ok=true'
      f' segments={len(segments)} speakers={len(speakers)}'
      f' elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--audio',
      type=Path,
      default=diarization_corpus.DEFAULT_ROOT / 'two-speaker.wav',
  )
  args = parser.parse_args(argv)
  if os.environ.get('LEONIDAS_RUN_DIARIZATION_E2E') != '1':
    print(
        'diarization_smoke_skipped=true '
        'set LEONIDAS_RUN_DIARIZATION_E2E=1 to run'
    )
    return 0
  try:
    asyncio.run(run(args.audio))
  except Exception as exc:
    print(f'diarization_smoke_failed=true error_type={type(exc).__name__}')
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
