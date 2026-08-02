"""Turn-based audio/text conversation processor for the cascade runtime."""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
import time
from typing import Any

from genai_processors import content_api
from genai_processors import processor

from leonidas.cascade import context
from leonidas.cascade import diarization
from leonidas.cascade import transcript_filter
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
      context_trigger_tokens: int | None = None,
      context_target_tokens: int | None = None,
      metrics: telemetry.MetricsStore | None = None,
      diarizer: diarization.Diarizer | None = None,
      diarization_timeout: float = 30.0,
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
    trigger = context_trigger_tokens or 6000
    target = context_target_tokens or min(4500, trigger - 1)
    self._context = context.BoundedConversationHistory(
        max_turns=history_turns,
        trigger_tokens=trigger,
        target_tokens=target,
    )
    # Kept as a read-compatible snapshot for diagnostics and existing callers.
    self._history: list[tuple[str, str]] = []
    self._metrics = metrics or telemetry.MetricsStore()
    self._diarizer = diarizer or diarization.NullDiarizer()
    if diarization_timeout <= 0:
      raise ValueError('diarization_timeout must be positive')
    self._diarization_timeout = diarization_timeout
    self._speaker_numbers: dict[str, int] = {}

  def _reasoning_prompt(
      self,
      transcript: str,
      segments: list[diarization.SpeakerSegment],
  ) -> str:
    speakers = {segment.speaker_id for segment in segments}
    if len(speakers) != 1:
      return transcript
    speaker_id = next(iter(speakers))
    if speaker_id not in self._speaker_numbers:
      self._speaker_numbers[speaker_id] = len(self._speaker_numbers) + 1
    return f'speak{self._speaker_numbers[speaker_id]} falou: {transcript}'

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
    history, evicted = self._context.for_prompt(
        objective=self._objective, prompt=prompt
    )
    if evicted:
      self._metrics.increment('context_turns_evicted', evicted)
    self._history = history
    started = time.perf_counter()
    response = await self._reasoner.respond(
        objective=self._objective,
        history=history,
        prompt=prompt,
        model_id=self._model_id,
        reasoning_effort=self._reasoning_effort,
    )
    self._metrics.observe(
        'groq_reasoning_ms', (time.perf_counter() - started) * 1000
    )
    overflow = self._context.append(prompt, response)
    if overflow:
      self._metrics.increment('context_turns_evicted', overflow)
    self._history = self._context.snapshot()
    yield content_api.ProcessorPart(response, role='model')
    yield self._state('synthesizing')
    started = time.perf_counter()
    try:
      pcm = await self._synthesizer.synthesize(
          response, voice_id=self._voice_id, language=self._language
      )
    except asyncio.CancelledError:
      self._metrics.increment('local_tts_cancelled')
      raise
    self._metrics.observe(
        'local_tts_ms', (time.perf_counter() - started) * 1000
    )
    if not pcm or len(pcm) % 2:
      raise RuntimeError('XTTS returned invalid PCM16 audio')
    yield self._state('speaking')
    # 75 ms PCM chunks reduce scheduler pressure versus the original 50 ms,
    # retain progressive delivery, and stay below the player's 80 ms reservoir.
    chunk_bytes = 3600
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
      self._metrics.increment('turn_interruptions')
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

    async def diarize_turn(
        audio: bytes,
    ) -> list[diarization.SpeakerSegment]:
      started = time.perf_counter()
      try:
        segments = await asyncio.wait_for(
            self._diarizer.diarize(audio, sample_rate=16000),
            timeout=self._diarization_timeout,
        )
        self._metrics.observe(
            'diarization_ms', (time.perf_counter() - started) * 1000
        )
        if segments:
          await output.put(
              content_api.ProcessorPart(
                  '',
                  substream_name='diarization',
                  metadata={
                      'speaker_segments': [
                          segment.to_dict() for segment in segments
                      ],
                      'is_final': True,
                  },
              )
          )
          return segments
        if not isinstance(self._diarizer, diarization.NullDiarizer):
          self._metrics.increment('diarization_fallbacks')
        return []
      except asyncio.CancelledError:
        raise
      except (Exception, TimeoutError):
        self._metrics.increment('diarization_errors')
        return []

    async def handle_event(event: vad.EndpointEvent) -> None:
      if event.kind == 'start':
        self._metrics.increment('vad_utterances_started')
        await interrupt()
        return
      if event.kind == 'candidate_rejected':
        self._metrics.increment('vad_candidates_rejected')
        return
      if event.kind != 'utterance':
        return
      await output.put(self._state('transcribing'))
      diarization_task = asyncio.create_task(diarize_turn(event.audio))
      started = time.perf_counter()
      try:
        transcript = await self._transcriber.transcribe(event.audio)
      except BaseException:
        diarization_task.cancel()
        await asyncio.gather(diarization_task, return_exceptions=True)
        raise
      self._metrics.observe(
          'local_stt_ms', (time.perf_counter() - started) * 1000
      )
      segments = await diarization_task
      duration = len(event.audio) / (16000 * 2)
      if transcript_filter.is_probable_short_artifact(
          transcript,
          audio_duration_seconds=duration,
          language=self._language,
      ):
        self._metrics.increment('stt_artifacts_rejected')
        await output.put(self._state('listening'))
        return
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
      await start_turn(self._reasoning_prompt(transcript, segments))

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
