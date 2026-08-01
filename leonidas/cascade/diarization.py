"""Optional speaker diarization contract for the local cascade."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib.util
from typing import Any, Protocol


@dataclass(frozen=True)
class SpeakerSegment:
  speaker_id: str
  start: float
  end: float
  confidence: float | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
        'speaker_id': self.speaker_id,
        'start': self.start,
        'end': self.end,
        'confidence': self.confidence,
    }


class Diarizer(Protocol):

  async def diarize(
      self, audio: bytes, *, sample_rate: int
  ) -> list[SpeakerSegment]:
    ...


class NullDiarizer:
  """No-op fallback that never blocks or changes the audio pipeline."""

  async def diarize(
      self, audio: bytes, *, sample_rate: int
  ) -> list[SpeakerSegment]:
    del audio, sample_rate
    return []


class PyannoteDiarizer:
  """Lazy pyannote adapter; optional dependencies stay outside base installs."""

  def __init__(
      self,
      *,
      model_id: str = 'pyannote/speaker-diarization-community-1',
      device: str = 'auto',
  ):
    self._model_id = model_id
    self._device = device
    self._pipeline: Any | None = None
    self._load_lock = asyncio.Lock()

  @property
  def device(self) -> str:
    return self._device

  async def load(self, progress=None) -> dict[str, Any]:
    """Loads weights outside the event loop for resource readiness."""
    if progress is not None:
      await progress('loading_weights')
    await self._load()
    if progress is not None:
      await progress('warming')
    return {'device': self._device, 'model_id': self._model_id}

  async def _load(self) -> Any:
    async with self._load_lock:
      if self._pipeline is not None:
        return self._pipeline

      def load() -> Any:
        try:
          from pyannote.audio import Pipeline
          import torch
        except ImportError as exc:
          raise RuntimeError(
              'pyannote.audio and torch are required for diarization'
          ) from exc
        pipeline = Pipeline.from_pretrained(self._model_id)
        requested = self._device
        if requested == 'auto':
          requested = 'cuda' if torch.cuda.is_available() else 'cpu'
        pipeline.to(torch.device(requested))
        return pipeline

      self._pipeline = await asyncio.to_thread(load)
      return self._pipeline

  async def diarize(
      self, audio: bytes, *, sample_rate: int
  ) -> list[SpeakerSegment]:
    pipeline = await self._load()

    def run() -> list[SpeakerSegment]:
      import torch

      waveform = torch.frombuffer(audio, dtype=torch.int16).clone().float()
      waveform = (waveform / 32768.0).reshape(1, -1)
      annotation = pipeline({'waveform': waveform, 'sample_rate': sample_rate})
      segments: list[SpeakerSegment] = []
      for turn, _track, speaker in annotation.itertracks(yield_label=True):
        segments.append(
            SpeakerSegment(
                speaker_id=str(speaker),
                start=float(turn.start),
                end=float(turn.end),
                confidence=None,
            )
        )
      return segments

    return await asyncio.to_thread(run)


def availability() -> dict[str, Any]:
  """Returns browser-safe installation status without loading model weights."""
  try:
    installed = importlib.util.find_spec('pyannote.audio') is not None
  except ModuleNotFoundError:
    installed = False
  return {
      'id': 'diarization',
      'state': 'available' if installed else 'unavailable',
      'model_id': 'pyannote/speaker-diarization-community-1',
      'device': None,
      'weights_loaded': False,
      'optional_dependency': 'pyannote.audio',
  }
