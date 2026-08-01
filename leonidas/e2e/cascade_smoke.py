"""Opt-in empirical Parakeet -> Groq -> XTTS cascade smoke."""

import argparse
import asyncio
import os
from pathlib import Path
import time

from genai_processors import content_api

from leonidas import capabilities
from leonidas.cascade import groq_reasoning
from leonidas.cascade import pipeline
from leonidas.cascade import resources
from leonidas.e2e import assets


DEFAULT_AUDIO = (
    Path(__file__).parents[1]
    / '.runtime'
    / 'e2e'
    / 'assets'
    / 'red_object_on_desk_ptbr.wav'
)
DEFAULT_VOICE = (
    Path(__file__).parents[1] / '.runtime' / 'voices' / 'leonidas.wav'
)


def required_resources_ready(snapshot: dict) -> bool:
  """Accepts optional components while requiring the audio critical path."""
  required = {
      item['id']: item['state']
      for item in snapshot['components']
      if item['id'] in ('stt', 'tts')
  }
  return snapshot['overall_state'] == 'ready' and required == {
      'stt': 'ready',
      'tts': 'ready',
  }


async def run(
    audio_path: Path, voice_path: Path, device: str, turns: int = 1
) -> None:
  if turns < 1:
    raise ValueError('turns must be positive')
  api_key = os.environ.get('GROQ_API_KEY')
  if not api_key:
    raise RuntimeError('GROQ_API_KEY is not set')
  pcm = assets.audio_as_pcm16_16khz(audio_path)
  pool = resources.CascadeResources(voices={'leonidas': voice_path})
  resource_state = await pool.ensure_ready(
      capabilities.PARAKEET_V3_MODEL,
      capabilities.XTTS_V2_MODEL,
      device,
  )
  if not required_resources_ready(resource_state):
    raise RuntimeError('Cascade resources did not reach canonical ready state')
  transcriber = pool.transcriber(capabilities.PARAKEET_V3_MODEL, device)
  synthesizer = pool.synthesizer(capabilities.XTTS_V2_MODEL, device)
  started = time.perf_counter()
  try:
    for turn in range(1, turns + 1):
      reasoner = groq_reasoning.GroqReasoner(api_key=api_key)
      cascade = pipeline.CascadeProcessor(
          transcriber=transcriber,
          reasoner=reasoner,
          synthesizer=synthesizer,
          objective='Converse em português e responda de forma útil e concisa.',
          model_id=capabilities.GROQ_GPT_OSS_20B,
          reasoning_effort='low',
          voice_id='leonidas',
      )

      async def inputs():
        for offset in range(0, len(pcm), 4096):
          yield content_api.ProcessorPart(
              pcm[offset : offset + 4096], mimetype='audio/pcm;rate=16000'
          )
        yield content_api.ProcessorPart('', metadata={'audio_stream_end': True})

      transcript = ''
      response = ''
      audio = bytearray()
      completed = False
      async for part in cascade(inputs()):
        if part.substream_name == 'input_transcription':
          transcript = part.text
        elif content_api.is_text(part.mimetype) and part.text:
          response = part.text
        elif content_api.is_audio(part.mimetype) and part.bytes:
          audio.extend(part.bytes)
        completed = completed or bool(part.get_metadata('generation_complete'))
      duration = len(audio) / (24000 * 2)
      if not transcript or not response or duration < 0.25 or not completed:
        raise RuntimeError(
            f'Cascade smoke failed its turn {turn} audio contract'
        )
      print(
          f'cascade_turn={turn} transcript_chars={len(transcript)} '
          f'response_chars={len(response)} audio_seconds={duration:.2f}'
      )
  finally:
    await pool.close()
  print(
      'cascade_ok=true '
      f'device={synthesizer.device} '
      f'turns={turns} '
      f'elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--audio', type=Path, default=DEFAULT_AUDIO)
  parser.add_argument('--voice', type=Path, default=DEFAULT_VOICE)
  parser.add_argument(
      '--device', choices=('auto', 'cuda', 'cpu'), default='auto'
  )
  parser.add_argument('--turns', type=int, default=1)
  args = parser.parse_args(argv)
  asyncio.run(run(args.audio, args.voice, args.device, args.turns))
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
