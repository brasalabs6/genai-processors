"""Generate a private Portuguese XTTS speaker reference with Gemini TTS."""

import argparse
import asyncio
import os
from pathlib import Path
import wave

from leonidas.e2e.generate_assets import GeminiAudioGenerator


DEFAULT_OUTPUT = (
    Path(__file__).parents[1] / '.runtime' / 'voices' / 'leonidas.wav'
)
SCRIPT = (
    'Olá, eu sou Leonidas. Estou preparando uma voz clara, calma e natural '
    'para conversar em português. Posso ouvir suas perguntas, organizar ideias '
    'e responder com atenção. Esta gravação contém frases variadas e pausas '
    'naturais para criar uma referência de voz consistente.'
)


def _validate(path: Path) -> float:
  with wave.open(str(path), 'rb') as source:
    if (
        source.getnchannels() != 1
        or source.getsampwidth() != 2
        or source.getframerate() != 24000
    ):
      raise ValueError('Voice reference must be mono PCM16 at 24 kHz')
    duration = source.getnframes() / source.getframerate()
  if duration < 6:
    raise ValueError('Voice reference must contain at least 6 seconds')
  return duration


async def _main(output: Path, force: bool) -> int:
  api_key = os.environ.get('GOOGLE_API_KEY')
  if not api_key:
    print('BLOCKED_EXTERNAL: GOOGLE_API_KEY is not set')
    return 2
  if force or not output.is_file():
    data = await GeminiAudioGenerator(api_key).generate(SCRIPT)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.wav.tmp')
    temporary.write_bytes(data)
    temporary.replace(output)
  duration = _validate(output)
  print(f'voice_reference_ok path={output} duration_seconds={duration:.2f}')
  return 0


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
  parser.add_argument('--force', action='store_true')
  args = parser.parse_args(argv)
  return asyncio.run(_main(args.output, args.force))


if __name__ == '__main__':
  raise SystemExit(main())
