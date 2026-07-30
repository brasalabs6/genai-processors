"""Shared, device-canonical local model resources for cascade sessions."""

import inspect
from pathlib import Path
from typing import Any, Callable

from leonidas.cascade import device as device_selection
from leonidas.cascade import parakeet
from leonidas.cascade import xtts_process


class CascadeResources:
  """Prevents duplicate local models across restart and voice preview paths."""

  def __init__(
      self,
      *,
      voices: dict[str, Path],
      device_resolver: Callable[[str], str] = device_selection.resolve_device,
      transcriber_factory: Callable[..., Any] = parakeet.ParakeetTranscriber,
      synthesizer_factory: Callable[..., Any] = (
          xtts_process.XttsWorkerSynthesizer
      ),
  ):
    self._voices = dict(voices)
    self._device_resolver = device_resolver
    self._transcriber_factory = transcriber_factory
    self._synthesizer_factory = synthesizer_factory
    self._transcribers: dict[tuple[str, str], Any] = {}
    self._synthesizers: dict[tuple[str, str], Any] = {}

  def transcriber(self, model_id: str, device: str) -> Any:
    resolved = self._device_resolver(device)
    key = (model_id, resolved)
    if key not in self._transcribers:
      self._transcribers[key] = self._transcriber_factory(
          model_id=model_id, device=resolved
      )
    return self._transcribers[key]

  def synthesizer(self, model_id: str, device: str) -> Any:
    resolved = self._device_resolver(device)
    key = (model_id, resolved)
    if key not in self._synthesizers:
      self._synthesizers[key] = self._synthesizer_factory(
          model_id=model_id,
          device=resolved,
          voices=self._voices,
      )
    return self._synthesizers[key]

  async def close(self) -> None:
    values = [*self._transcribers.values(), *self._synthesizers.values()]
    self._transcribers.clear()
    self._synthesizers.clear()
    for value in values:
      close = getattr(value, 'close', None)
      if close is None:
        continue
      result = close()
      if inspect.isawaitable(result):
        await result
