"""Provider-independent empirical pipeline evaluator."""

import asyncio
import dataclasses
import re
import time
from typing import AsyncIterable, Iterable

from genai_processors import content_api
from genai_processors import processor


@dataclasses.dataclass(frozen=True)
class EmpiricalResult:
  model_id: str
  scenario_id: str
  passed: bool
  audio_seconds: float
  ttfa_ms: float | None
  transcription_received: bool
  semantic_matches: tuple[str, ...]
  output_parts: int
  error_code: str | None
  elapsed_seconds: float

  def to_dict(self) -> dict[str, object]:
    return dataclasses.asdict(self)


async def _iter_inputs(
    inputs: (
        Iterable[content_api.ProcessorPart]
        | AsyncIterable[content_api.ProcessorPart]
    ),
) -> AsyncIterable[content_api.ProcessorPart]:
  if hasattr(inputs, '__aiter__'):
    async for part in inputs:  # type: ignore[union-attr]
      yield part
  else:
    for part in inputs:  # type: ignore[union-attr]
      yield part


async def run_processor(
    live_processor: processor.Processor,
    inputs: (
        Iterable[content_api.ProcessorPart]
        | AsyncIterable[content_api.ProcessorPart]
    ),
    *,
    model_id: str,
    scenario_id: str,
    expected_terms: tuple[str, ...],
    timeout_seconds: float,
    minimum_audio_seconds: float,
) -> EmpiricalResult:
  """Runs one finite empirical scenario without persisting model content."""
  started = time.perf_counter()
  first_audio: float | None = None
  audio_bytes = 0
  output_parts = 0
  transcription: list[str] = []
  error_code = None
  try:
    async with asyncio.timeout(timeout_seconds):
      async for part in live_processor(_iter_inputs(inputs)):
        output_parts += 1
        if content_api.is_audio(part.mimetype) and part.part.inline_data:
          if first_audio is None:
            first_audio = time.perf_counter()
          audio_bytes += len(part.part.inline_data.data or b'')
        elif (
            content_api.is_text(part.mimetype)
            and part.substream_name == 'output_transcription'
        ):
          transcription.append(part.text)
        if audio_bytes >= minimum_audio_seconds * 24000 * 2 and (
            part.get_metadata('generation_complete', False)
            or part.get_metadata('turn_complete', False)
        ):
          break
  except TimeoutError:
    error_code = 'timeout'
  except Exception as exc:  # pylint: disable=broad-exception-caught
    error_code = type(exc).__name__
  elapsed = time.perf_counter() - started
  audio_seconds = audio_bytes / (24000 * 2)
  normalized = ' '.join(transcription).casefold()
  words = re.findall(r'\w+', normalized)

  def term_matches(term: str) -> bool:
    candidate = term.casefold()
    if candidate in normalized:
      return True
    return len(candidate) >= 6 and any(
        word.startswith(candidate[:6]) for word in words
    )

  matches = tuple(term for term in expected_terms if term_matches(term))
  if error_code is None and audio_seconds < minimum_audio_seconds:
    error_code = 'insufficient_audio'
  if error_code is None and first_audio is not None:
    if (first_audio - started) > 20:
      error_code = 'ttfa_threshold_exceeded'
  passed = (
      error_code is None
      and audio_seconds >= minimum_audio_seconds
      and (not expected_terms or bool(matches) or not transcription)
  )
  return EmpiricalResult(
      model_id=model_id,
      scenario_id=scenario_id,
      passed=passed,
      audio_seconds=audio_seconds,
      ttfa_ms=(
          (first_audio - started) * 1000 if first_audio is not None else None
      ),
      transcription_received=bool(transcription),
      semantic_matches=matches,
      output_parts=output_parts,
      error_code=error_code,
      elapsed_seconds=elapsed,
  )
