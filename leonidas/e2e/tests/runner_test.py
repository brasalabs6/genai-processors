import asyncio
from pathlib import Path
import tempfile
import unittest

from genai_processors import content_api
from genai_processors import processor

from leonidas.e2e import runner


class DemoPipeline(processor.Processor):

  async def call(self, content):
    async for _ in content:
      pass
    yield content_api.ProcessorPart(
        b'\x00\x00' * 6000,
        role='model',
        mimetype='audio/pcm;rate=24000',
    )
    yield content_api.ProcessorPart(
        'Vejo uma caneca vermelha sobre a mesa e ouvi você.',
        role='model',
        substream_name='output_transcription',
    )


class RunnerTest(unittest.IsolatedAsyncioTestCase):

  async def test_empirical_result_checks_audio_and_semantic_terms(self):
    inputs = [
        content_api.ProcessorPart(b'image', mimetype='image/jpeg'),
        content_api.ProcessorPart(
            b'\x00\x00' * 1600, mimetype='audio/pcm;rate=16000'
        ),
    ]
    result = await runner.run_processor(
        DemoPipeline(),
        inputs,
        model_id='fake-model',
        scenario_id='scenario',
        expected_terms=('mesa', 'vermelho'),
        timeout_seconds=2,
        minimum_audio_seconds=0.25,
    )

    self.assertTrue(result.passed)
    self.assertGreaterEqual(result.audio_seconds, 0.25)
    self.assertEqual(result.semantic_matches, ('mesa', 'vermelho'))
    self.assertNotIn('caneca', result.to_dict())

  async def test_timeout_is_a_failed_result_not_a_hanging_task(self):
    class HangingPipeline(processor.Processor):

      async def call(self, content):
        async for _ in content:
          await asyncio.sleep(10)
        if False:
          yield None

    result = await runner.run_processor(
        HangingPipeline(),
        [content_api.ProcessorPart('input')],
        model_id='fake-model',
        scenario_id='timeout',
        expected_terms=(),
        timeout_seconds=0.01,
        minimum_audio_seconds=0.25,
    )
    self.assertFalse(result.passed)
    self.assertEqual(result.error_code, 'timeout')


if __name__ == '__main__':
  unittest.main()
