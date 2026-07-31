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
PipelinePreparer = Callable[[config.AgentConfig], Awaitable[Any]]
PreparationSelector = Callable[[config.AgentConfig], bool]
StateListener = Callable[[dict[str, Any]], Any]


class SessionManager:
  """Owns one media connection and one replaceable processor task."""

  def __init__(
      self,
      config_store: config.ConfigStore,
      pipeline_factory: PipelineFactory,
      *,
      metrics: telemetry.MetricsStore | None = None,
      stop_timeout: float = 3.0,
      state_listener_timeout: float = 1.0,
      pipeline_preparer: PipelinePreparer | None = None,
      requires_preparation: PreparationSelector | None = None,
  ):
    if stop_timeout <= 0 or state_listener_timeout <= 0:
      raise ValueError('Session timeouts must be positive')
    self._config_store = config_store
    self._pipeline_factory = pipeline_factory
    self._metrics = metrics or telemetry.MetricsStore()
    self._stop_timeout = stop_timeout
    self._state_listener_timeout = state_listener_timeout
    self._pipeline_preparer = pipeline_preparer
    self._requires_preparation = requires_preparation or (lambda _config: False)
    self._state = SessionState.STOPPED
    self._session_id: str | None = None
    self._started_at: float | None = None
    self._sender: OutputSender | None = None
    self._input_queue: (
        asyncio.Queue[content_api.ProcessorPart | None] | None
    ) = None
    self._task: asyncio.Task[None] | None = None
    self._startup_task: asyncio.Task[None] | None = None
    self._startup_generation = 0
    self._last_error: str | None = None
    self._lock = asyncio.Lock()
    self._state_listeners: set[StateListener] = set()

  async def attach_media(self, sender: OutputSender) -> None:
    async with self._lock:
      if self._sender is not None:
        raise MediaAlreadyConnectedError('A media client is already connected')
      self._sender = sender

  async def detach_media(self) -> None:
    await self.stop()
    async with self._lock:
      self._sender = None

  def add_state_listener(self, listener: StateListener) -> None:
    self._state_listeners.add(listener)

  def remove_state_listener(self, listener: StateListener) -> None:
    self._state_listeners.discard(listener)

  async def _call(self, callback: Callable[..., Any], *args: Any) -> None:
    result = callback(*args)
    if inspect.isawaitable(result):
      await result

  async def _notify_state(self, snapshot: dict[str, Any]) -> None:
    """Publishes concurrently outside the lifecycle lock with a hard deadline."""

    async def publish(listener: StateListener) -> None:
      try:
        await asyncio.wait_for(
            self._call(listener, dict(snapshot)),
            timeout=self._state_listener_timeout,
        )
      except Exception as exc:  # Broken or stalled sockets cannot poison state.
        self._state_listeners.discard(listener)
        logging.warning(
            'Leonidas state listener removed error_type=%s',
            type(exc).__name__,
        )

    listeners = tuple(self._state_listeners)
    if listeners:
      await asyncio.gather(*(publish(listener) for listener in listeners))

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
      if self._state in (SessionState.STARTING, SessionState.RUNNING):
        return self.snapshot()
      if self._sender is None:
        raise MediaNotConnectedError('Connect the media WebSocket before Start')
      self._state = SessionState.STARTING
      self._last_error = None
      agent_config = self._config_store.snapshot().active
      if self._pipeline_preparer is not None and self._requires_preparation(
          agent_config
      ):
        self._startup_generation += 1
        generation = self._startup_generation
        self._startup_task = asyncio.create_task(
            self._prepare_and_start(agent_config, generation),
            name=f'leonidas-session-prepare-{generation}',
        )
      else:
        try:
          self._activate(agent_config)
        except Exception as exc:
          self._state = SessionState.ERROR
          self._last_error = type(exc).__name__
          snapshot = self.snapshot()
          asyncio.create_task(self._notify_state(snapshot))
          raise
      snapshot = self.snapshot()
    await self._notify_state(snapshot)
    return snapshot

  def _activate(self, agent_config: config.AgentConfig) -> None:
    started = time.perf_counter()
    live_processor = self._pipeline_factory(agent_config)
    queue: asyncio.Queue[content_api.ProcessorPart | None] = asyncio.Queue(
        maxsize=256
    )
    if self._sender is None:
      raise MediaNotConnectedError('Media disconnected during Start')
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

  async def _prepare_and_start(
      self, agent_config: config.AgentConfig, generation: int
  ) -> None:
    started = time.perf_counter()
    error: Exception | None = None
    try:
      if self._pipeline_preparer is None:
        return
      await self._pipeline_preparer(agent_config)
      self._metrics.observe(
          'local_model_load_ms', (time.perf_counter() - started) * 1000
      )
    except asyncio.CancelledError:
      return
    except Exception as exc:
      error = exc

    async with self._lock:
      if (
          generation != self._startup_generation
          or self._state != SessionState.STARTING
      ):
        return
      if error is not None:
        self._state = SessionState.ERROR
        self._last_error = type(error).__name__
      else:
        try:
          self._activate(agent_config)
        except Exception as exc:
          self._state = SessionState.ERROR
          self._last_error = type(exc).__name__
      self._startup_task = None
      snapshot = self.snapshot()
    await self._notify_state(snapshot)

  def _task_done(self, task: asyncio.Task[None]) -> None:
    asyncio.create_task(self._handle_task_done(task))

  async def _handle_task_done(self, task: asyncio.Task[None]) -> None:
    if task.cancelled():
      return
    try:
      exception = task.exception()
    except asyncio.CancelledError:
      return
    if exception is None:
      return
    async with self._lock:
      if task is not self._task or self._state in (
          SessionState.STOPPING,
          SessionState.STOPPED,
      ):
        return
      self._state = SessionState.ERROR
      self._last_error = type(exception).__name__
      snapshot = self.snapshot()
    logging.error(
        'Leonidas pipeline failed error_type=%s', type(exception).__name__
    )
    await self._notify_state(snapshot)

  async def stop(self) -> dict[str, Any]:
    async with self._lock:
      if self._state == SessionState.STOPPED:
        return self.snapshot()
      self._state = SessionState.STOPPING
      self._startup_generation += 1
      startup_task = self._startup_task
      task = self._task
      queue = self._input_queue
      self._startup_task = None
      stopping_snapshot = self.snapshot()
    await self._notify_state(stopping_snapshot)

    if startup_task is not None and not startup_task.done():
      startup_task.cancel()
      await asyncio.gather(startup_task, return_exceptions=True)
    if queue is not None:
      try:
        queue.put_nowait(None)
      except asyncio.QueueFull:
        pass
    if task is not None:
      try:
        await asyncio.wait_for(asyncio.shield(task), timeout=self._stop_timeout)
      except asyncio.TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
      except asyncio.CancelledError:
        pass
      except Exception:
        pass

    async with self._lock:
      if self._task is task:
        self._task = None
      if self._input_queue is queue:
        self._input_queue = None
      self._session_id = None
      self._started_at = None
      self._state = SessionState.STOPPED
      stopped_snapshot = self.snapshot()
    await self._notify_state(stopped_snapshot)
    return stopped_snapshot

  async def send(self, part: content_api.ProcessorPart) -> None:
    queue = self._input_queue
    if self._state != SessionState.RUNNING or queue is None:
      return
    queue.put_nowait(part)
    if content_api.is_audio(part.mimetype):
      self._metrics.increment('audio_chunks_received')
    elif content_api.is_image(part.mimetype):
      self._metrics.increment('frames_received')

  async def _wait_until_started(self) -> None:
    """Waits for background preparation and turns startup errors into failure."""
    while True:
      async with self._lock:
        task = self._startup_task
        state = self._state
        error = self._last_error
      if task is None:
        if state == SessionState.RUNNING:
          return
        raise RuntimeError(f'Leonidas startup failed: {error or state.value}')
      await asyncio.shield(task)

  async def apply_config(self) -> dict[str, Any]:
    """Applies a draft atomically from the caller's point of view.

    A prepared local pipeline settles before success is returned. Any async
    preparation or activation failure restores the previous active config and
    restarts the previous session before the original failure is re-raised.
    """
    was_running = self._state in (
        SessionState.STARTING,
        SessionState.RUNNING,
    )
    previous, _ = self._config_store.promote_draft()
    if not was_running:
      return self._config_store.snapshot().to_dict()

    await self.stop()
    try:
      await self.start()
      await self._wait_until_started()
    except Exception:
      self._config_store.restore_active(previous)
      await self.stop()
      try:
        await self.start()
        await self._wait_until_started()
      except Exception as rollback_error:
        logging.error(
            'Leonidas config rollback failed error_type=%s',
            type(rollback_error).__name__,
        )
      raise
    return self._config_store.snapshot().to_dict()
