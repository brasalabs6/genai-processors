"""Explicit, restart-safe Leonidas session lifecycle."""

import asyncio
import enum
import inspect
import logging
import time
import uuid
from typing import Any, AsyncIterable, Awaitable, Callable

from genai_processors import content_api
from genai_processors import processor

from leonidas import config
from leonidas import telemetry


class SessionState(enum.StrEnum):
  STOPPED = 'stopped'
  STARTING = 'starting'
  RUNNING = 'running'
  STOPPING = 'stopping'
  ERROR = 'error'


class MediaNotConnectedError(RuntimeError):
  """Raised when starting without an owning media connection."""


class MediaAlreadyConnectedError(RuntimeError):
  """Raised when a second media owner attempts to attach."""


OutputSender = Callable[[content_api.ProcessorPart], Any]
PipelineFactory = Callable[[config.AgentConfig], processor.Processor]


class SessionManager:
  """Owns one media connection and one replaceable processor task."""

  def __init__(
      self,
      config_store: config.ConfigStore,
      pipeline_factory: PipelineFactory,
      *,
      metrics: telemetry.MetricsStore | None = None,
      stop_timeout: float = 3.0,
  ):
    self._config_store = config_store
    self._pipeline_factory = pipeline_factory
    self._metrics = metrics or telemetry.MetricsStore()
    self._stop_timeout = stop_timeout
    self._state = SessionState.STOPPED
    self._session_id: str | None = None
    self._started_at: float | None = None
    self._sender: OutputSender | None = None
    self._input_queue: (
        asyncio.Queue[content_api.ProcessorPart | None] | None
    ) = None
    self._task: asyncio.Task[None] | None = None
    self._last_error: str | None = None
    self._lock = asyncio.Lock()
    self._state_listeners: set[Callable[[dict[str, Any]], Any]] = set()

  async def attach_media(self, sender: OutputSender) -> None:
    async with self._lock:
      if self._sender is not None:
        raise MediaAlreadyConnectedError('A media client is already connected')
      self._sender = sender

  async def detach_media(self) -> None:
    await self.stop()
    async with self._lock:
      self._sender = None

  def add_state_listener(
      self, listener: Callable[[dict[str, Any]], Any]
  ) -> None:
    self._state_listeners.add(listener)

  def remove_state_listener(
      self, listener: Callable[[dict[str, Any]], Any]
  ) -> None:
    self._state_listeners.discard(listener)

  async def _call(self, callback: Callable[..., Any], *args: Any) -> None:
    result = callback(*args)
    if inspect.isawaitable(result):
      await result

  async def _notify_state(self) -> None:
    snapshot = self.snapshot()
    for listener in tuple(self._state_listeners):
      await self._call(listener, snapshot)

  def snapshot(self) -> dict[str, Any]:
    return {
        'state': self._state.value,
        'session_id': self._session_id,
        'media_connected': self._sender is not None,
        'started_at': self._started_at,
        'last_error': self._last_error,
    }

  async def _inputs(
      self, queue: asyncio.Queue[content_api.ProcessorPart | None]
  ) -> AsyncIterable[content_api.ProcessorPart]:
    while True:
      part = await queue.get()
      if part is None:
        return
      yield part

  async def _run(
      self,
      live_processor: processor.Processor,
      queue: asyncio.Queue[content_api.ProcessorPart | None],
      sender: OutputSender,
  ) -> None:
    async for part in live_processor(self._inputs(queue)):
      await self._call(sender, part)

  async def start(self) -> dict[str, Any]:
    async with self._lock:
      if self._state == SessionState.RUNNING:
        return self.snapshot()
      if self._sender is None:
        raise MediaNotConnectedError('Connect the media WebSocket before Start')
      self._state = SessionState.STARTING
      self._last_error = None
      await self._notify_state()
      started = time.perf_counter()
      try:
        live_processor = self._pipeline_factory(
            self._config_store.snapshot().active
        )
        queue: asyncio.Queue[content_api.ProcessorPart | None] = asyncio.Queue(
            maxsize=256
        )
        self._input_queue = queue
        self._session_id = uuid.uuid4().hex
        self._started_at = time.time()
        self._task = asyncio.create_task(
            self._run(live_processor, queue, self._sender),
            name=f'leonidas-session-{self._session_id}',
        )
        self._task.add_done_callback(self._task_done)
        self._state = SessionState.RUNNING
        self._metrics.observe(
            'pipeline_startup_ms', (time.perf_counter() - started) * 1000
        )
      except Exception as exc:
        self._state = SessionState.ERROR
        self._last_error = type(exc).__name__
        self._input_queue = None
        self._task = None
        await self._notify_state()
        raise
      await self._notify_state()
      return self.snapshot()

  def _task_done(self, task: asyncio.Task[None]) -> None:
    if task.cancelled():
      return
    try:
      exception = task.exception()
    except asyncio.CancelledError:
      return
    if exception is not None and self._state not in (
        SessionState.STOPPING,
        SessionState.STOPPED,
    ):
      self._state = SessionState.ERROR
      self._last_error = type(exception).__name__
      logging.error(
          'Leonidas pipeline failed error_type=%s', type(exception).__name__
      )
      asyncio.create_task(self._notify_state())

  async def stop(self) -> dict[str, Any]:
    async with self._lock:
      if self._state == SessionState.STOPPED:
        return self.snapshot()
      self._state = SessionState.STOPPING
      await self._notify_state()
      task = self._task
      if self._input_queue is not None:
        try:
          self._input_queue.put_nowait(None)
        except asyncio.QueueFull:
          pass
      if task is not None:
        try:
          await asyncio.wait_for(task, timeout=self._stop_timeout)
        except asyncio.TimeoutError:
          task.cancel()
          try:
            await task
          except asyncio.CancelledError:
            pass
        except asyncio.CancelledError:
          pass
        except Exception:
          # The failed task is being torn down; Start creates a fresh one.
          pass
      self._task = None
      self._input_queue = None
      self._session_id = None
      self._started_at = None
      self._state = SessionState.STOPPED
      await self._notify_state()
      return self.snapshot()

  async def send(self, part: content_api.ProcessorPart) -> None:
    queue = self._input_queue
    if self._state != SessionState.RUNNING or queue is None:
      return
    queue.put_nowait(part)
    if content_api.is_audio(part.mimetype):
      self._metrics.increment('audio_chunks_received')
    elif content_api.is_image(part.mimetype):
      self._metrics.increment('frames_received')

  async def apply_config(self) -> dict[str, Any]:
    was_running = self._state == SessionState.RUNNING
    previous, _ = self._config_store.promote_draft()
    if not was_running:
      return self._config_store.snapshot().to_dict()
    await self.stop()
    try:
      await self.start()
    except Exception:
      self._config_store.restore_active(previous)
      await self.start()
      raise
    return self._config_store.snapshot().to_dict()
