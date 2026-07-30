"""Coqui XTTS v2 local PCM synthesis adapter."""

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from leonidas import capabilities
from leonidas.cascade import device as device_selection


def _default_engine_factory(model_id: str) -> Any:
  from TTS.api import TTS

  return TTS(model_name=model_id, progress_bar=False)


class XttsSynthesizer:

  sample_rate = 24000

  def __init__(
      self,
      *,
      model_id: str = capabilities.XTTS_V2_MODEL,
      device: str = 'auto',
      voices: Mapping[str, Path],
      engine_factory: Callable[[str], Any] = _default_engine_factory,
  ):
    if model_id != capabilities.XTTS_V2_MODEL:
      raise ValueError(f'Unsupported XTTS model: {model_id!r}')
    self.model_id = model_id
    self.device = device_selection.resolve_device(device)
    self._voices = dict(voices)
    self._engine_factory = engine_factory
    self._engine = None

  def _synthesize(self, text: str, voice_id: str, language: str) -> bytes:
    voice = self._voices.get(voice_id)
    if voice is None or not voice.is_file():
      raise ValueError(f'Unknown or unavailable voice_id: {voice_id!r}')
    if language != 'pt':
      raise ValueError('XTTS language must be pt')
    if self._engine is None:
      self._engine = self._engine_factory(self.model_id).to(self.device)
    waveform = np.asarray(
        self._engine.tts(text=text, speaker_wav=str(voice), language=language),
        dtype=np.float32,
    )
    waveform = np.clip(waveform, -1.0, 1.0)
    return (waveform * 32767).astype('<i2').tobytes()

  async def synthesize(
      self, text: str, *, voice_id: str, language: str
  ) -> bytes:
    if not text.strip():
      raise ValueError('XTTS text cannot be empty')
    if voice_id not in self._voices:
      raise ValueError(f'Unknown or unavailable voice_id: {voice_id!r}')
    return await asyncio.to_thread(
        self._synthesize, text.strip(), voice_id, language
    )
