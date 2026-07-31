"""Shared, device-canonical local model resources for cascade sessions."""

import asyncio
import copy
import inspect
import logging
from pathlib import Path
import time
from typing import Any, Callable

from leonidas.cascade import device as device_selection
from leonidas.cascade import parakeet_process
from leonidas.cascade import xtts_process


class CascadeResources:
  """Prevents duplicate local models across restart and voice preview paths."""

  def __init__(
      self,
      *,
      voices: dict[str, Path],
      device_resolver: Callable[[str], str] = device_selection.resolve_device,
      transcriber_factory: Callable[..., Any] = (
          parakeet_process.ParakeetWorkerTranscriber
      ),
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
    self._listeners: set[Callable[[dict[str, Any]], Any]] = set()
    self._status = {
        'stt': self._empty_status('stt'),
        'tts': self._empty_status('tts'),
    }
    self._prepare_lock = asyncio.Lock()
    self._prepare_task: asyncio.Task[None] | None = None
    self._prepare_key: tuple[str, str, str] | None = None
    self._ready_key: tuple[str, str, str] | None = None

  @staticmethod
  def _empty_status(component_id: str) -> dict[str, Any]:
    return {
        'id': component_id,
        'model_id': None,
        'state': 'unloaded',
        'phase': 'unloaded',
        'device': None,
        'gpu_name': None,
        'load_ms': None,
        'memory_allocated_mib': None,
        'memory_reserved_mib': None,
        'error': None,
    }

  def add_listener(self, listener: Callable[[dict[str, Any]], Any]) -> None:
    self._listeners.add(listener)

  def remove_listener(self, listener: Callable[[dict[str, Any]], Any]) -> None:
    self._listeners.discard(listener)

  def snapshot(self) -> dict[str, Any]:
    components = [copy.deepcopy(self._status[name]) for name in ('stt', 'tts')]
    states = {item['state'] for item in components}
    if states == {'ready'}:
      overall = 'ready'
    elif 'error' in states:
      overall = 'error'
    elif states == {'unloaded'}:
      overall = 'unloaded'
    else:
      overall = 'loading'
    return {
        'schema_version': 1,
        'overall_state': overall,
        'components': components,
    }

  async def _notify(self) -> None:
    snapshot = self.snapshot()
    for listener in tuple(self._listeners):
      try:
        result = listener(snapshot)
        if inspect.isawaitable(result):
          await result
      except Exception as exc:
        self._listeners.discard(listener)
        logging.warning(
            'Resource listener removed error_type=%s', type(exc).__name__
        )

  async def _update(self, component_id: str, **values: Any) -> None:
    self._status[component_id].update(values)
    await self._notify()

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

  async def _load_component(
      self,
      component_id: str,
      model_id: str,
      resource: Any,
      device: str,
  ) -> None:
    started = time.perf_counter()
    await self._update(
        component_id,
        model_id=model_id,
        state='validating',
        phase='validating',
        device=device,
        error=None,
    )

    async def progress(phase: str) -> None:
      state = 'warming' if phase == 'warming' else 'loading'
      await self._update(
          component_id,
          state=state,
          phase=phase,
      )

    try:
      await self._update(component_id, state='loading', phase='loading')
      details = await resource.load(progress=progress)
      await self._update(
          component_id,
          **dict(details or {}),
          state='ready',
          phase='ready',
          load_ms=(time.perf_counter() - started) * 1000,
          error=None,
      )
    except Exception as exc:
      code = 'cuda_unavailable' if 'CUDA' in str(exc) else 'model_load_failed'
      await self._update(
          component_id,
          state='error',
          phase='error',
          load_ms=(time.perf_counter() - started) * 1000,
          error={
              'stage': component_id,
              'code': code,
              'message': f'{component_id.upper()} local não ficou disponível.',
              'recovery': (
                  'Verifique CUDA, cache do modelo e os logs do Leonidas.'
              ),
          },
      )
      raise

  async def _prepare(
      self, stt_model_id: str, tts_model_id: str, device: str
  ) -> None:
    transcriber = self.transcriber(stt_model_id, device)
    synthesizer = self.synthesizer(tts_model_id, device)
    await self._load_component(
        'stt', stt_model_id, transcriber, getattr(transcriber, 'device', device)
    )
    await self._load_component(
        'tts', tts_model_id, synthesizer, getattr(synthesizer, 'device', device)
    )
    self._ready_key = (
        stt_model_id,
        tts_model_id,
        getattr(transcriber, 'device', device),
    )

  async def ensure_ready(
      self, stt_model_id: str, tts_model_id: str, device: str
  ) -> dict[str, Any]:
    resolved = self._device_resolver(device)
    key = (stt_model_id, tts_model_id, resolved)
    while self._ready_key != key:
      async with self._prepare_lock:
        if self._ready_key == key:
          break
        if self._prepare_task is None or self._prepare_task.done():
          self._prepare_key = key
          self._prepare_task = asyncio.create_task(
              self._prepare(stt_model_id, tts_model_id, resolved),
              name='leonidas-local-model-prepare',
          )
        task = self._prepare_task
        preparing_key = self._prepare_key
      await asyncio.shield(task)
      if preparing_key == key:
        break
    return self.snapshot()

  async def close(self) -> None:
    if self._prepare_task is not None:
      await asyncio.gather(self._prepare_task, return_exceptions=True)
      self._prepare_task = None
      self._prepare_key = None
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
