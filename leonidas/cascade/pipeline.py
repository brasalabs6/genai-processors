"""Turn-based audio/text conversation processor for the cascade runtime."""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
import time
from typing import Any

from genai_processors import content_api
from genai_processors import processor

from leonidas.cascade import vad
from leonidas import telemetry


class CascadeProcessor(processor.Processor):

  def __init__(
      self,
      *,
      transcriber: Any,
      reasoner: Any,
      synthesizer: Any,
      objective: str,
      model_id: str,
      reasoning_effort: str,
      voice_id: str,
      language: str = 'pt',
      endpoint_detector: vad.EndpointDetector | None = None,
      history_turns: int = 20,
      metrics: telemetry.MetricsStore | None = None,
  ):
    super().__init__()
    self._transcriber = transcriber
    self._reasoner = reasoner
    self._synthesizer = synthesizer
    self._objective = objective
    self._model_id = model_id
    self._reasoning_effort = reasoning_effort
    self._voice_id = voice_id
    self._language = language
    self._endpoint = endpoint_detector or vad.EndpointDetector()
    self._audio_buffer = bytearray()
    self._history: list[tuple[str, str]] = []
    self._history_turns = history_turns
    self._metrics = metrics or telemetry.MetricsStore()

  @staticmethod
  def _state(value: str) -> content_api.ProcessorPart:
    return content_api.ProcessorPart(
        '',
        role='model',
        mimetype='application/x-state',
        metadata={'agent_state': value},
    )

  async def _turn(
      self, prompt: str
  ) -> AsyncIterator[content_api.ProcessorPart]:
    yield self._state('thinking')
    started = time.perf_counter()
    response = await self._reasoner.respond(
        objective=self._objective,
        history=self._history,
        prompt=prompt,
        model_id=self._model_id,
        reasoning_effort=self._reasoning_effort,
    )
    self._metrics.observe(
        'groq_reasoning_ms', (time.perf_counter() - started) * 1000
    )
    self._history.extend((('user', prompt), ('assistant', response)))
    self._history = self._history[-self._history_turns * 2 :]
    yield content_api.ProcessorPart(response, role='model')
    yield self._state('speaking')
    started = time.perf_counter()
    pcm = await self._synthesizer.synthesize(
        response, voice_id=self._voice_id, language=self._language
    )
    self._metrics.observe(
        'local_tts_ms', (time.perf_counter() - started) * 1000
    )
    chunk_bytes = 2400
    for offset in range(0, len(pcm), chunk_bytes):
      yield content_api.ProcessorPart(
          pcm[offset : offset + chunk_bytes],
          role='model',
          mimetype='audio/pcm;rate=24000',
      )
      await asyncio.sleep(0)
    yield self._state('listening')
    yield content_api.ProcessorPart(
        '', metadata={'generation_complete': True, 'turn_complete': True}
    )

  async def call(
      self, content: AsyncIterable[content_api.ProcessorPart]
  ) -> AsyncIterator[content_api.ProcessorPart]:
    output: asyncio.Queue[content_api.ProcessorPart | Exception | None] = (
        asyncio.Queue(64)
    )
    response_task: asyncio.Task[None] | None = None

    async def produce_turn(prompt: str) -> None:
      try:
        async for result in self._turn(prompt):
          await output.put(result)
      except Exception as exc:
        await output.put(exc)

    async def interrupt() -> None:
      nonlocal response_task
      if response_task is None:
        return
      if response_task.done():
        finished = response_task
        response_task = None
        await finished
        return
      await output.put(
          content_api.ProcessorPart(
              '', metadata={'interrupted': True, 'interrupt_request': True}
          )
      )
      response_task.cancel()
      try:
        await response_task
      except asyncio.CancelledError:
        pass
      response_task = None

    async def start_turn(prompt: str) -> None:
      nonlocal response_task
      await interrupt()
      response_task = asyncio.create_task(produce_turn(prompt))

    async def handle_event(event: vad.EndpointEvent) -> None:
      if event.kind == 'start':
        await interrupt()
        return
      if event.kind != 'utterance':
        return
      await output.put(self._state('transcribing'))
      started = time.perf_counter()
      transcript = await self._transcriber.transcribe(event.audio)
      self._metrics.observe(
          'local_stt_ms', (time.perf_counter() - started) * 1000
      )
      if not transcript:
        await output.put(self._state('listening'))
        return
      await output.put(
          content_api.ProcessorPart(
              transcript,
              role='user',
              substream_name='input_transcription',
              metadata={'is_final': True},
          )
      )
      await start_turn(transcript)

    async def consume() -> None:
      try:
        async for part in content:
          if content_api.is_image(part.mimetype):
            raise ValueError('cascade_local does not support vision input')
          if content_api.is_text(part.mimetype) and part.text.strip():
            await start_turn(part.text.strip())
          elif content_api.is_audio(part.mimetype) and part.bytes:
            if part.mimetype != 'audio/pcm;rate=16000':
              raise ValueError('cascade_local requires audio/pcm;rate=16000')
            self._audio_buffer.extend(part.bytes)
            while len(self._audio_buffer) >= vad.FRAME_BYTES:
              frame = bytes(self._audio_buffer[: vad.FRAME_BYTES])
              del self._audio_buffer[: vad.FRAME_BYTES]
              for event in self._endpoint.push(frame):
                await handle_event(event)
          if part.get_metadata('audio_stream_end'):
            for event in self._endpoint.flush():
              await handle_event(event)
            self._audio_buffer.clear()
        for event in self._endpoint.flush():
          await handle_event(event)
        if response_task is not None:
          await response_task
      finally:
        await output.put(None)

    consumer = asyncio.create_task(consume())
    try:
      while True:
        result = await output.get()
        if result is None:
          break
        if isinstance(result, Exception):
          raise result
        yield result
      await consumer
    finally:
      if not consumer.done():
        consumer.cancel()
      tasks = [consumer]
      if response_task is not None and not response_task.done():
        response_task.cancel()
      if response_task is not None:
        tasks.append(response_task)
      await asyncio.gather(*tasks, return_exceptions=True)
      close = getattr(self._reasoner, 'close', None)
      if close is not None:
        await close()
