"""Generate a private Gemini TTS corpus for Codex microphone smokes."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path

from leonidas.e2e import assets
from leonidas.e2e import generate_assets


DEFAULT_ROOT = Path(__file__).parents[1] / '.runtime' / 'e2e' / 'codex_audio'


@dataclasses.dataclass(frozen=True)
class CorpusTurn:
  id: str
  script: str


DEFAULT_TURNS = (
    CorpusTurn(
        'turn-01',
        'Olá, Leonidas. Confirme que você está me ouvindo com clareza.',
    ),
    CorpusTurn(
        'turn-02',
        'Agora responda qual foi o assunto da minha mensagem anterior.',
    ),
)


async def generate_corpus(
    root: Path,
    generator: generate_assets.AudioGenerator,
    *,
    scripts: tuple[CorpusTurn, ...] = DEFAULT_TURNS,
    force: bool = False,
) -> tuple[Path, ...]:
  """Generate validated WAV turns and a content-redacted technical manifest."""
  if len(scripts) < 2:
    raise ValueError('Codex microphone corpus requires at least two turns')
  root.mkdir(parents=True, exist_ok=True)
  generated: list[Path] = []
  manifest_turns: list[dict[str, object]] = []
  for turn in scripts:
    if not turn.id or not turn.script.strip():
      raise ValueError('Corpus turns require a non-empty id and script')
    path = root / f'{turn.id}.wav'
    if force or not path.is_file():
      generate_assets.write_atomic(path, await generator.generate(turn.script))
    info = assets.validate_audio(path)
    payload = path.read_bytes()
    generated.append(path)
    manifest_turns.append(
        {
            'id': turn.id,
            'file': path.name,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'bytes': len(payload),
            'sample_rate': info.sample_rate,
            'channels': info.channels,
            'sample_width': info.sample_width,
            'duration_seconds': round(info.duration_seconds, 3),
        }
    )
  manifest = {
      'schema_version': 1,
      'generator': generate_assets.DEFAULT_AUDIO_MODEL,
      'turns': manifest_turns,
  }
  generate_assets.write_atomic(
      root / 'manifest.json',
      (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'),
  )
  return tuple(generated)


async def _main(args: argparse.Namespace) -> int:
  api_key = os.environ.get('GOOGLE_API_KEY')
  if not api_key:
    print('codex_audio_corpus_failed=true reason=google_api_key_missing')
    return 2
  generated = await generate_corpus(
      args.output,
      generate_assets.GeminiAudioGenerator(api_key, model=args.model),
      force=args.force,
  )
  durations = [
      assets.validate_audio(path).duration_seconds for path in generated
  ]
  print(
      f'codex_audio_corpus_ok=true turns={len(generated)} '
      f'total_duration_seconds={sum(durations):.2f}'
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
