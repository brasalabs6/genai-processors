"""Bounded per-source async ingress queues for a realtime adapter."""

import asyncio
from collections.abc import AsyncIterator
from typing import Generic, TypeVar

from universal_ai.contracts import SourceSettings

T = TypeVar('T')
_SENTINEL = object()


class BoundedIngress(Generic[T]):
  """Single-producer inbox with bounded memory and explicit close.

  Audio/text/control writers backpressure instead of losing data. For image or
  telemetry, an adapter can select replace-oldest when its consumer is slow.
  Producers must not publish concurrently with close(); caller owns lifecycle.
  """

  def __init__(self, settings: SourceSettings):
    self.settings = settings
    self._queue: asyncio.Queue[T | object] = asyncio.Queue(
        maxsize=settings.capacity
    )
    self._closed = False
    self.dropped = 0

  async def publish(self, item: T) -> None:
    if self._closed:
      raise RuntimeError('source already closed')
    if item is _SENTINEL:
      raise ValueError('reserved sentinel')
    if self.settings.overflow == 'drop_oldest' and self._queue.full():
      self._queue.get_nowait()
      self.dropped += 1
    await self._queue.put(item)

  async def close(self) -> None:
    if self._closed:
      return
    self._closed = True
    # Backpressure for lossless sources: wake any consumer without discarding.
    # For replaceable video/telemetry, discard one item to avoid deadlock when
    # there is no consumer currently running.
    if self.settings.overflow == 'drop_oldest' and self._queue.full():
      self._queue.get_nowait()
      self.dropped += 1
    await self._queue.put(_SENTINEL)

  async def stream(self) -> AsyncIterator[T]:
    while True:
      item = await self._queue.get()
      if item is _SENTINEL:
        break
      yield item  # type: ignore[misc]
