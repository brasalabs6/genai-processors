"""Validation and decoding for locally generated E2E media."""

import dataclasses
from pathlib import Path
import wave

import numpy as np
from PIL import Image


@dataclasses.dataclass(frozen=True)
class AudioInfo:
  sample_rate: int
  channels: int
  sample_width: int
  frames: int
  duration_seconds: float


@dataclasses.dataclass(frozen=True)
class ImageInfo:
  width: int
  height: int
  format: str


def validate_audio(path: Path) -> AudioInfo:
  if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
    raise ValueError('Audio asset is missing or too large')
  try:
    with wave.open(str(path), 'rb') as source:
      info = AudioInfo(
          source.getframerate(),
          source.getnchannels(),
          source.getsampwidth(),
          source.getnframes(),
          source.getnframes() / source.getframerate(),
      )
  except (wave.Error, EOFError) as exc:
    raise ValueError('Audio asset is not a valid WAV file') from exc
  if info.sample_rate != 24000:
    raise ValueError('Generated audio must be 24000 Hz')
  if info.channels != 1 or info.sample_width != 2:
    raise ValueError('Generated audio must be mono 16-bit PCM')
  if not 0.25 <= info.duration_seconds <= 10:
    raise ValueError('Generated audio duration must be 0.25 to 10 seconds')
  return info


def validate_image(path: Path) -> ImageInfo:
  if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
    raise ValueError('Image asset is missing or too large')
  try:
    with Image.open(path) as image:
      image.verify()
    with Image.open(path) as image:
      info = ImageInfo(image.width, image.height, image.format or '')
  except (OSError, ValueError) as exc:
    raise ValueError('Image asset is invalid') from exc
  if info.format not in ('PNG', 'JPEG'):
    raise ValueError('Image asset must be PNG or JPEG')
  if info.width < 640 or info.height < 360:
    raise ValueError('Image asset must be at least 640x360')
  return info


def audio_as_pcm16_16khz(path: Path) -> bytes:
  validate_audio(path)
  with wave.open(str(path), 'rb') as source:
    samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
  target_length = round(len(samples) * 16000 / 24000)
  source_positions = np.arange(len(samples), dtype=np.float64)
  target_positions = np.linspace(0, len(samples) - 1, target_length)
  converted = np.interp(target_positions, source_positions, samples)
  return np.clip(converted, -32768, 32767).astype('<i2').tobytes()


def image_as_jpeg(path: Path) -> bytes:
  validate_image(path)
  from io import BytesIO

  output = BytesIO()
  with Image.open(path) as image:
    image.convert('RGB').save(output, format='JPEG', quality=80, optimize=True)
  return output.getvalue()
