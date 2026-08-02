"""Generate a private two-human-voice Gemini corpus for diarization smokes."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Sequence
import wave

from leonidas.e2e import assets
from leonidas.e2e import generate_assets


DEFAULT_ROOT = (
    Path(__file__).parents[1] / '.runtime' / 'e2e' / 'diarization_audio'
)
DEFAULT_SCRIPTS = (
    'Bom dia. Esta é a primeira voz falando sobre o projeto.',
    'Olá. Esta é a segunda voz respondendo com clareza.',
)


@dataclasses.dataclass(frozen=True)
class DiarizationCorpus:
  audio_path: Path
  speakers: int
  duration_seconds: float


async def generate_corpus(
    root: Path,
    generators: Sequence[generate_assets.AudioGenerator],
    *,
    scripts: tuple[str, str] = DEFAULT_SCRIPTS,
    silence_seconds: float = 1.0,
    force: bool = False,
) -> DiarizationCorpus:
  """Generate two voice clips and combine them without overlapping speech."""
  if len(generators) != 2 or len(scripts) != 2:
    raise ValueError('Diarization corpus requires exactly two speakers')
  if not 0.5 <= silence_seconds <= 3.0:
    raise ValueError('Diarization silence must be between 0.5 and 3 seconds')
  root.mkdir(parents=True, exist_ok=True)
  clips: list[Path] = []
  clip_metadata: list[dict[str, object]] = []
  for index, (generator, script) in enumerate(
      zip(generators, scripts, strict=True), start=1
  ):
    if not script.strip():
      raise ValueError('Diarization scripts must not be empty')
    path = root / f'speaker-{index:02d}.wav'
    if force or not path.is_file():
      generate_assets.write_atomic(path, await generator.generate(script))
    info = assets.validate_audio(path)
    clips.append(path)
    clip_metadata.append(
        {
            'id': f'speaker-{index:02d}',
            'file': path.name,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'duration_seconds': round(info.duration_seconds, 3),
        }
    )

  frames: list[bytes] = []
  for path in clips:
    with wave.open(str(path), 'rb') as source:
      frames.append(source.readframes(source.getnframes()))
  silence = bytes(round(24000 * 2 * silence_seconds))
  payload = silence.join(frames)
  output = io.BytesIO()
  with wave.open(output, 'wb') as target:
    target.setnchannels(1)
    target.setsampwidth(2)
    target.setframerate(24000)
    target.writeframes(payload)
  audio_path = root / 'two-speaker.wav'
  generate_assets.write_atomic(audio_path, output.getvalue())
  info = assets.validate_audio(audio_path, max_duration_seconds=30.0)
  manifest = {
      'schema_version': 1,
      'generator': generate_assets.DEFAULT_AUDIO_MODEL,
      'speakers': 2,
      'sample_rate': info.sample_rate,
      'channels': info.channels,
      'sample_width': info.sample_width,
      'duration_seconds': round(info.duration_seconds, 3),
      'clips': clip_metadata,
  }
  generate_assets.write_atomic(
      root / 'manifest.json',
      (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'),
  )
  return DiarizationCorpus(audio_path, 2, info.duration_seconds)


async def _main(args: argparse.Namespace) -> int:
  api_key = os.environ.get('GOOGLE_API_KEY')
  if not api_key:
    print('diarization_corpus_failed=true reason=google_api_key_missing')
    return 2
  corpus = await generate_corpus(
      args.output,
      (
          generate_assets.GeminiAudioGenerator(
              api_key, model=args.model, voice='Kore'
          ),
          generate_assets.GeminiAudioGenerator(
              api_key, model=args.model, voice='Puck'
          ),
      ),
      force=args.force,
  )
  print(
      f'diarization_corpus_ok=true speakers={corpus.speakers} '
      f'duration_seconds={corpus.duration_seconds:.2f}'
  )
  return 0


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, default=DEFAULT_ROOT)
  parser.add_argument('--model', default=generate_assets.DEFAULT_AUDIO_MODEL)
  parser.add_argument('--force', action='store_true')
  return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == '__main__':
  raise SystemExit(main())
