"""Opt-in real Pyannote diarization smoke over a synthetic two-speaker WAV."""

from __future__ import annotations

import asyncio
import math
import os
import struct
import time

from leonidas.cascade import diarization


def _synthetic_two_speaker_pcm(sample_rate: int = 16000) -> bytes:
  """Builds two non-overlapping voiced tone regions without external assets."""
  samples: list[int] = []
  for frequency in (180.0, 240.0):
    for index in range(sample_rate):
      envelope = min(1.0, index / (sample_rate * 0.05))
      envelope *= min(1.0, (sample_rate - index) / (sample_rate * 0.05))
      value = int(
          9000
          * envelope
          * math.sin(2 * math.pi * frequency * index / sample_rate)
      )
      samples.append(value)
  return struct.pack(f'<{len(samples)}h', *samples)


async def run() -> None:
  started = time.perf_counter()
  adapter = diarization.PyannoteDiarizer(
      device=os.environ.get('LEONIDAS_DIARIZATION_DEVICE', 'auto')
  )
  segments = await adapter.diarize(
      _synthetic_two_speaker_pcm(), sample_rate=16000
  )
  speakers = sorted({segment.speaker_id for segment in segments})
  print(
      'diarization_smoke_ok=true'
      f' segments={len(segments)} speakers={len(speakers)}'
      f' elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main() -> int:
  if os.environ.get('LEONIDAS_RUN_DIARIZATION_E2E') != '1':
    print(
        'diarization_smoke_skipped=true '
        'set LEONIDAS_RUN_DIARIZATION_E2E=1 to run'
    )
    return 0
  try:
    asyncio.run(run())
  except Exception as exc:
    print(f'diarization_smoke_failed=true error_type={type(exc).__name__}')
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
