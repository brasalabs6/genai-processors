"""GenAI Processor stages for stamping, vision budgeting and conversations."""

from collections.abc import AsyncIterable, AsyncIterator, Mapping
import time
from typing import Callable

from genai_processors import content_api
from genai_processors import processor
from genai_processors import streams

from universal_ai.contracts import ConversationNeeds
from universal_ai.contracts import ProviderCapabilities


Clock = Callable[[], int]


class StampSource(processor.Processor):
  """Stamp monotonic receive time and source ID without replacing media."""

  def __init__(self, source: str, clock: Clock = time.monotonic_ns):
    if not source:
      raise ValueError('source must be non-empty')
    self._source = source
    self._clock = clock
    self._sequence = 0

  async def call(
      self, content: processor.ProcessorStream
  ) -> AsyncIterator[content_api.ProcessorPartTypes]:
    async for part in content:
      self._sequence += 1
      metadata = dict(part.metadata)
      metadata.update(
          {
              'ua_source': self._source,
              'ua_sequence': self._sequence,
              'ua_received_ns': self._clock(),
          }
      )
      copied = part.copy()
      copied.metadata = metadata
      yield copied


class VisionBudget(processor.Processor):
  """Keep newest timely camera frames; never discard audio or control."""

  def __init__(
      self,
      max_fps: float,
      max_age_ms: int,
      clock: Clock = time.monotonic_ns,
  ):
    if max_fps <= 0 or max_age_ms <= 0:
      raise ValueError('invalid vision budget')
    self._interval_ns = int(1e9 / max_fps)
    self._max_age_ns = max_age_ms * 1_000_000
    self._last_frame_ns: dict[str, int] = {}
    self._clock = clock
    self.dropped_rate = 0
    self.dropped_stale = 0

  async def call(
      self, content: processor.ProcessorStream
  ) -> AsyncIterator[content_api.ProcessorPartTypes]:
    async for part in content:
      if (
          not content_api.is_image(part.mimetype)
          or part.substream_name != 'realtime'
      ):
        yield part
        continue
      now = self._clock()
      source = str(part.get_metadata('ua_source', 'video'))
      received = part.get_metadata('ua_received_ns', now)
      if (
          isinstance(received, int)
          and 0 <= now - received
          and now - received > self._max_age_ns
      ):
        self.dropped_stale += 1
        continue
      last = self._last_frame_ns.get(source)
      if last is not None and now - last < self._interval_ns:
        self.dropped_rate += 1
        continue
      self._last_frame_ns[source] = now
      yield part


async def merge_sources(
    sources: Mapping[str, AsyncIterable[content_api.ProcessorPart]],
    clock: Clock = time.monotonic_ns,
) -> AsyncIterator[content_api.ProcessorPart]:
  """Merge independently arriving streams; ordering is by arrival, not clock."""
  if not sources:
    raise ValueError('at least one source is required')
  stamped = [StampSource(name, clock)(source) for name, source in sources.items()]
  async for part in streams.merge(stamped):
    yield part


def compose_conversation(
    backend: processor.Processor,
    capability: ProviderCapabilities,
    requirements: ConversationNeeds,
    clock: Clock = time.monotonic_ns,
) -> processor.Processor:
  """Compose a validated backend without knowing its provider SDK.

  Backend is responsible for VAD, interruption and audio pacing. This stage
  restricts only realtime image volume, never speech or control events.
  """
  requirements.validate(capability)
  return VisionBudget(
      requirements.video_max_fps,
      requirements.video_max_age_ms,
      clock=clock,
  ) + backend


async def run_conversation(
    backend: processor.Processor,
    capability: ProviderCapabilities,
    requirements: ConversationNeeds,
    sources: Mapping[str, AsyncIterable[content_api.ProcessorPart]],
) -> AsyncIterator[content_api.ProcessorPart]:
  """Run one session with managed cancellation and composition context."""
  pipeline = compose_conversation(backend, capability, requirements)
  async with processor.context():
    async for part in pipeline(merge_sources(sources)):
      yield part
