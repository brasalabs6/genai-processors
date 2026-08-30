"""Generate private E2E media with Gemini APIs."""

import argparse
import asyncio
import base64
import dataclasses
import io
import os
from pathlib import Path
from typing import Protocol
import wave

from google import genai
from PIL import Image
from PIL import ImageDraw

from leonidas.e2e import assets
from leonidas.e2e import manifest


DEFAULT_IMAGE_MODEL = 'gemini-3.1-flash-image'
DEFAULT_AUDIO_MODEL = 'gemini-3.1-flash-tts-preview'
DEFAULT_ASSET_ROOT = Path(__file__).parents[1] / '.runtime' / 'e2e' / 'assets'


class AudioGenerator(Protocol):

  async def generate(self, script: str) -> bytes:
    ...


class ImageGenerator(Protocol):

  async def generate(self, prompt: str) -> bytes:
    ...


class GeminiAudioGenerator:

  def __init__(
      self,
      api_key: str,
      *,
      model: str = DEFAULT_AUDIO_MODEL,
      voice: str = 'Kore',
      client=None,
  ):
    self._client = client or genai.Client(api_key=api_key)
    self._model = model
    self._voice = voice

  async def generate(self, script: str) -> bytes:
    interaction = await asyncio.to_thread(
        self._client.interactions.create,
        model=self._model,
        input=f'Leia exatamente este texto em português, sem adicionar nada: {script}',
        response_format={'type': 'audio'},
        generation_config={'speech_config': [{'voice': self._voice}]},
    )
    output_audio = getattr(interaction, 'output_audio', None)
    data = getattr(output_audio, 'data', None)
    if not data:
      raise RuntimeError('Gemini TTS returned no audio')
    pcm = (
        base64.b64decode(data, validate=True)
        if isinstance(data, str)
        else bytes(data)
    )
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav_file:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(24000)
      wav_file.writeframes(pcm[: 24000 * 2 * 10])
    return output.getvalue()


class GeminiImageGenerator:

  def __init__(self, api_key: str, model: str = DEFAULT_IMAGE_MODEL):
    self._client = genai.Client(api_key=api_key)
    self._model = model

  async def generate(self, prompt: str) -> bytes:
    interaction = await asyncio.to_thread(
        self._client.interactions.create,
        model=self._model,
        input=prompt,
    )
    output_image = getattr(interaction, 'output_image', None)
    data = getattr(output_image, 'data', None)
    if not data:
      raise RuntimeError('Gemini image generation returned no image')
    if isinstance(data, str):
      return base64.b64decode(data, validate=True)
    return bytes(data)


class SyntheticImageGenerator:
  """Deterministic visible fixture used only after explicit CLI opt-in."""

  async def generate(self, prompt: str) -> bytes:
    del prompt
    from io import BytesIO

    image = Image.new('RGB', (1280, 720), '#d9d0c2')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 410, 1280, 720), fill='#8b5a38')
    draw.rectangle(
        (780, 465, 1080, 625), fill='#ece7dd', outline='#463c33', width=5
    )
    draw.rectangle(
        (400, 350, 610, 610), fill='#d72727', outline='#721313', width=8
    )
    draw.ellipse((560, 405, 685, 545), outline='#d72727', width=28)
    draw.ellipse(
        (430, 330, 580, 380), fill='#ef5252', outline='#721313', width=6
    )
    draw.ellipse((435, 565, 575, 625), fill='#6d3927')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


@dataclasses.dataclass(frozen=True)
class GeneratedAssets:
  audio_path: Path
  image_path: Path
  image_source: str


def write_atomic(path: Path, data: bytes) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  temp = path.with_suffix(path.suffix + '.tmp')
  with temp.open('wb') as output:
    output.write(data)
    output.flush()
    os.fsync(output.fileno())
  os.replace(temp, path)


async def generate_scenario(
    scenario: manifest.Scenario,
    root: Path,
    audio_generator: AudioGenerator,
    image_generator: ImageGenerator,
    *,
    force: bool = False,
    image_source: str = 'gemini',
) -> GeneratedAssets:
  """Generates both assets and validates them before returning."""
  audio_path = root / f'{scenario.id}.wav'
  image_path = root / f'{scenario.id}.png'
  if force or not audio_path.is_file():
    write_atomic(
        audio_path, await audio_generator.generate(scenario.audio_script)
    )
  if force or not image_path.is_file():
    write_atomic(
        image_path, await image_generator.generate(scenario.image_prompt)
    )
  try:
    assets.validate_audio(audio_path)
    assets.validate_image(image_path)
  except Exception:
    if audio_path.is_file() and audio_path.stat().st_size == 0:
      audio_path.unlink()
    if image_path.is_file() and image_path.stat().st_size == 0:
      image_path.unlink()
    raise
  return GeneratedAssets(audio_path, image_path, image_source)


async def _main(args: argparse.Namespace) -> int:
  api_key = os.environ.get('GOOGLE_API_KEY')
  if not api_key:
    print('BLOCKED_EXTERNAL: GOOGLE_API_KEY is not set')
    return 2
  scenarios = manifest.load(args.manifest)
  audio_generator = GeminiAudioGenerator(api_key)
  image_generator: ImageGenerator = (
      SyntheticImageGenerator()
      if args.synthetic_image
      else GeminiImageGenerator(api_key, args.image_model)
  )
  image_source = 'synthetic' if args.synthetic_image else 'gemini'
  for scenario in scenarios:
    generated = await generate_scenario(
        scenario,
        args.output,
        audio_generator,
        image_generator,
        force=args.force,
        image_source=image_source,
    )
    print(
        f'generated scenario={scenario.id} '
        f'audio={generated.audio_path} image={generated.image_path} '
        f'image_source={generated.image_source}'
    )
  return 0


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--manifest',
      type=Path,
      default=Path(__file__).with_name('scenarios.json'),
  )
  parser.add_argument('--output', type=Path, default=DEFAULT_ASSET_ROOT)
  parser.add_argument('--image-model', default=DEFAULT_IMAGE_MODEL)
  parser.add_argument('--force', action='store_true')
  parser.add_argument(
      '--synthetic-image',
      action='store_true',
      help='Explicitly use a deterministic Pillow image instead of Gemini.',
  )
  return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == '__main__':
  raise SystemExit(main())
