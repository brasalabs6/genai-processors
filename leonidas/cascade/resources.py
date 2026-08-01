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
  """Owns one active, atomically replaceable local model generation."""

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
      listener_timeout: float = 1.0,
  ):
    if listener_timeout <= 0:
      raise ValueError('listener_timeout must be positive')
    self._voices = dict(voices)
    self._device_resolver = device_resolver
    self._transcriber_factory = transcriber_factory
    self._synthesizer_factory = synthesizer_factory
    self._listener_timeout = listener_timeout
    self._transcribers: dict[tuple[str, str], Any] = {}
    self._synthesizers: dict[tuple[str, str], Any] = {}
    self._listeners: set[Callable[[dict[str, Any]], Any]] = set()
    self._status = {
        'stt': self._empty_status('stt'),
        'tts': self._empty_status('tts'),
    }
    self._ready_status: dict[str, dict[str, Any]] | None = None
    self._last_error: dict[str, Any] | None = None
    self._prepare_lock = asyncio.Lock()
    self._prepare_task: asyncio.Task[None] | None = None
    self._prepare_key: tuple[str, str, str] | None = None
    self._ready_key: tuple[str, str, str] | None = None
    self._generation = 0
    self._closing = False

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
        'generation': self._generation,
        'overall_state': overall,
        'components': components,
        'last_error': copy.deepcopy(self._last_error),
    }

  async def _notify(self) -> None:
    snapshot = self.snapshot()

    async def publish(listener: Callable[[dict[str, Any]], Any]) -> None:
      try:
        result = listener(copy.deepcopy(snapshot))
        if inspect.isawaitable(result):
          await asyncio.wait_for(result, timeout=self._listener_timeout)
      except Exception as exc:
        self._listeners.discard(listener)
        logging.warning(
            'Resource listener removed error_type=%s', type(exc).__name__
        )

    listeners = tuple(self._listeners)
    if listeners:
      await asyncio.gather(*(publish(listener) for listener in listeners))

  async def _update(self, component_id: str, **values: Any) -> None:
    self._status[component_id].update(values)
    await self._notify()

  def transcriber(self, model_id: str, device: str) -> Any:
    if self._closing:
      raise RuntimeError('Cascade resources are closing')
    resolved = self._device_resolver(device)
    key = (model_id, resolved)
    if key not in self._transcribers:
      self._transcribers[key] = self._transcriber_factory(
          model_id=model_id, device=resolved
      )
    return self._transcribers[key]

  def synthesizer(self, model_id: str, device: str) -> Any:
    if self._closing:
      raise RuntimeError('Cascade resources are closing')
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
      await self._update(component_id, state=state, phase=phase)

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
    except asyncio.CancelledError:
      await self._update(
          component_id,
          state='unloaded',
          phase='unloaded',
          error=None,
      )
      raise
    except Exception as exc:
      if isinstance(exc, xtts_process.XttsResourceError):
        code = 'insufficient_system_memory'
      elif 'CUDA' in str(exc):
        code = 'cuda_unavailable'
      else:
        code = 'model_load_failed'
      error = {
          'stage': component_id,
          'code': code,
          'message': (
              str(exc)
              if getattr(exc, 'public_message', False)
              else f'{component_id.upper()} local não ficou disponível.'
          ),
          'recovery': 'Verifique CUDA, cache do modelo e os logs do Leonidas.',
      }
      self._last_error = copy.deepcopy(error)
      await self._update(
          component_id,
          state='error',
          phase='error',
          load_ms=(time.perf_counter() - started) * 1000,
          error=error,
      )
      raise

  @staticmethod
  async def _close_resource(resource: Any) -> None:
    close = getattr(resource, 'close', None)
    if close is None:
      return
    try:
      result = close()
      if inspect.isawaitable(result):
        await result
    except Exception as exc:
      logging.warning(
          'Cascade resource close failed error_type=%s', type(exc).__name__
      )

  async def _close_unique(self, values: list[Any]) -> None:
    seen: set[int] = set()
    for resource in values:
      identity = id(resource)
      if identity in seen:
        continue
      seen.add(identity)
      await self._close_resource(resource)

  async def _evict_inactive(
      self,
      active_stt: tuple[str, str],
      active_tts: tuple[str, str],
  ) -> None:
    stale: list[Any] = []
    for key in tuple(self._transcribers):
      if key != active_stt:
        stale.append(self._transcribers.pop(key))
    for key in tuple(self._synthesizers):
      if key != active_tts:
        stale.append(self._synthesizers.pop(key))
    await self._close_unique(stale)

  async def _discard_candidate(
      self,
      stt_key: tuple[str, str],
      tts_key: tuple[str, str],
      transcriber: Any,
      synthesizer: Any,
  ) -> None:
    candidates: list[Any] = []
    if self._transcribers.get(stt_key) is transcriber:
      candidates.append(self._transcribers.pop(stt_key))
    if self._synthesizers.get(tts_key) is synthesizer:
      candidates.append(self._synthesizers.pop(tts_key))
    await self._close_unique(candidates)

  async def _prepare(
      self, stt_model_id: str, tts_model_id: str, device: str
  ) -> None:
    stt_key = (stt_model_id, device)
    tts_key = (tts_model_id, device)
    transcriber = self.transcriber(stt_model_id, device)
    synthesizer = self.synthesizer(tts_model_id, device)
    try:
      await self._load_component(
          'stt',
          stt_model_id,
          transcriber,
          getattr(transcriber, 'device', device),
      )
      await self._load_component(
          'tts',
          tts_model_id,
          synthesizer,
          getattr(synthesizer, 'device', device),
      )
    except BaseException:
      await self._discard_candidate(stt_key, tts_key, transcriber, synthesizer)
      if self._ready_status is not None:
        self._status = copy.deepcopy(self._ready_status)
        await self._notify()
      raise

    ready_device = getattr(transcriber, 'device', device)
    ready_tts_device = getattr(synthesizer, 'device', device)
    self._ready_key = (stt_model_id, tts_model_id, ready_device)
    self._generation += 1
    self._last_error = None
    self._ready_status = copy.deepcopy(self._status)
    await self._evict_inactive(
        (stt_model_id, ready_device),
        (tts_model_id, ready_tts_device),
    )

  async def ensure_ready(
      self, stt_model_id: str, tts_model_id: str, device: str
  ) -> dict[str, Any]:
    if self._closing:
      raise RuntimeError('Cascade resources are closing')
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
      try:
        await asyncio.shield(task)
      except asyncio.CancelledError:
        raise
      except Exception:
        if preparing_key == key:
          raise
        continue
      if preparing_key == key:
        break
    return self.snapshot()

  async def close(self) -> None:
    self._closing = True
    async with self._prepare_lock:
      task = self._prepare_task
      self._prepare_task = None
      self._prepare_key = None
      self._ready_key = None
      self._ready_status = None
      if task is not None and not task.done():
        task.cancel()
    if task is not None:
      await asyncio.gather(task, return_exceptions=True)
    values = [*self._transcribers.values(), *self._synthesizers.values()]
    self._transcribers.clear()
    self._synthesizers.clear()
    await self._close_unique(values)
    self._status = {
        'stt': self._empty_status('stt'),
        'tts': self._empty_status('tts'),
    }
    self._last_error = None
