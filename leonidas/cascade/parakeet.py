"""NVIDIA Parakeet v3 local transcription adapter."""

import asyncio
from collections.abc import Callable
import re
from typing import Any

import numpy as np

from leonidas import capabilities
from leonidas.cascade import device as device_selection


_SPECIAL_TOKEN_RE = re.compile(r'<(?:blank|pad|unk)>', re.IGNORECASE)
_PUNCTUATION_SPACE_RE = re.compile(r'\s+([,.;:!?])')


def normalize_transcript(text: str) -> str:
  """Removes Parakeet's decoder control tokens at the STT boundary."""
  cleaned = _SPECIAL_TOKEN_RE.sub(' ', text)
  cleaned = ' '.join(cleaned.split())
  return _PUNCTUATION_SPACE_RE.sub(r'\1', cleaned).strip()


def _default_loader(model_id: str, device: str) -> tuple[Any, Any]:
  import torch
  from transformers import AutoModelForTDT
  from transformers import AutoProcessor

  processor = AutoProcessor.from_pretrained(model_id)
  dtype = torch.float16 if device == 'cuda' else torch.float32
  model = AutoModelForTDT.from_pretrained(model_id, dtype=dtype)
  model.to(device)
  model.eval()
  return processor, model


class ParakeetTranscriber:

  def __init__(
      self,
      *,
      model_id: str = capabilities.PARAKEET_V3_MODEL,
      device: str = 'auto',
      loader: Callable[[str, str], tuple[Any, Any]] = _default_loader,
  ):
    if model_id != capabilities.PARAKEET_V3_MODEL:
      raise ValueError(f'Unsupported Parakeet model: {model_id!r}')
    self.model_id = model_id
    self.device = device_selection.resolve_device(device)
    if loader is _default_loader:
      try:
        from transformers import AutoModelForTDT  # pylint: disable=g-import-not-at-top
        from transformers import AutoProcessor  # pylint: disable=g-import-not-at-top

        del AutoModelForTDT, AutoProcessor
      except ImportError as exc:
        raise RuntimeError(
            'Parakeet requires Transformers 5 with AutoModelForTDT'
        ) from exc
    self._loader = loader
    self._processor = None
    self._model = None
    self._lock = asyncio.Lock()
    self._drain_task: asyncio.Task[str] | None = None

  def _load(self) -> None:
    if self._processor is None or self._model is None:
      self._processor, self._model = self._loader(self.model_id, self.device)

  def _transcribe(self, pcm16: bytes) -> str:
    if len(pcm16) % 2:
      raise ValueError('PCM16 input byte length must be even')
    self._load()
    audio = np.frombuffer(pcm16, dtype='<i2').astype(np.float32) / 32768.0
    inputs = self._processor(
        audio, sampling_rate=16000, return_tensors='pt'
    ).to(self.device)
    model_dtype = getattr(self._model, 'dtype', None)
    if model_dtype is not None:
      for name, value in inputs.items():
        is_floating_point = getattr(value, 'is_floating_point', None)
        if callable(is_floating_point) and is_floating_point():
          inputs[name] = value.to(dtype=model_dtype)
    result = self._model.generate(**inputs)
    sequences = getattr(result, 'sequences', result)
    decoded = self._processor.batch_decode(sequences)
    return normalize_transcript(decoded[0]) if decoded else ''

  async def transcribe(self, pcm16: bytes) -> str:
    await self._lock.acquire()
    release_lock = True
    task = asyncio.create_task(asyncio.to_thread(self._transcribe, pcm16))
    try:
      return await asyncio.shield(task)
    except asyncio.CancelledError:
      release_lock = False
      self._drain_task = asyncio.create_task(self._drain(task))
      raise
    finally:
      if release_lock:
        self._lock.release()

  async def _drain(self, task: asyncio.Task[str]) -> str:
    try:
      return await task
    finally:
      self._lock.release()

  async def close(self) -> None:
    if self._drain_task is not None:
      await asyncio.gather(self._drain_task, return_exceptions=True)
      self._drain_task = None
