import asyncio
from collections.abc import AsyncIterable
import gc
import unittest
import warnings

from absl.testing import absltest
from absl.testing import parameterized
from genai_processors import content_api
from genai_processors import processor
from genai_processors import streams
from genai_processors.core import realtime
from genai_processors.core import window
from PIL import Image


ProcessorPart = content_api.ProcessorPart
ProcessorContent = content_api.ProcessorContent


def create_image(width, height):
  return Image.new('RGB', (width, height))


@processor.processor_function
async def main_model_fake(
    content: AsyncIterable[ProcessorPart],
) -> AsyncIterable[ProcessorPart]:
  yield 'model('
  async for part in content:
    if content_api.is_text(part.mimetype):
      yield part
    else:
      yield f'[{part.mimetype}]'
  yield ')'


@processor.part_processor_function
async def main_model_exception_fake(
    part: ProcessorPart,
) -> AsyncIterable[ProcessorPart]:
  yield part
  raise ValueError('model error')


class RealTimeConversationTest(
    parameterized.TestCase, unittest.IsolatedAsyncioTestCase
):

  @parameterized.parameters([
      dict(
          input_stream=[
              ProcessorPart('hello', role='user'),
              ProcessorPart(
                  b'\x01\x00\x01\x00',
                  mimetype='audio/wav',
                  role='user',
              ),
              ProcessorPart(
                  create_image(100, 100),
                  mimetype='image/png',
                  role='user',
              ),
          ],
          output_text='model(hello[audio/wav][image/png])',
      ),
      dict(
          input_stream=[
              ProcessorPart('hello', role='user'),
              ProcessorPart(
                  b'\x01\x00\x01\x00',
                  mimetype='audio/wav',
                  role='user',
              ),
              content_api.ProcessorPart.end_of_turn(),
              ProcessorPart('yo', role='user'),
              ProcessorPart(
                  create_image(100, 100),
                  mimetype='image/png',
                  role='user',
              ),
          ],
          output_text='model(hello[audio/wav]yo[image/png])',
      ),
  ])
  async def test_realtime_single_ok(self, input_stream, output_text):
    input_stream = streams.stream_content(input_stream)
    output_parts = await streams.gather_stream(
        realtime.LiveProcessor(
            main_model_fake.to_processor(),
        )(input_stream)
    )
    actual = content_api.as_text(output_parts, substream_name='')
    self.assertEqual(actual, output_text)

  async def test_realtime_raise_exception(self):
    conversation_mgr = realtime.LiveProcessor(
        turn_processor=main_model_exception_fake.to_processor()
    )
    input_stream = streams.stream_content([
        ProcessorPart('hello', role='user'),
    ])
    with self.assertRaises(ValueError):
      await streams.gather_stream(conversation_mgr(input_stream))


@processor.processor_function
async def model_fake(
    content: AsyncIterable[ProcessorPart],
) -> AsyncIterable[ProcessorPart]:
  buffer = content_api.ProcessorContent()
  async for part in content:
    buffer += part
  await asyncio.sleep(1)
  yield ProcessorPart(f'model({buffer.as_text()})', role='model')


class RealTimeConversationModelTest(unittest.IsolatedAsyncioTestCase):

  def setUp(self):
    super().setUp()
    self.output_queue = asyncio.Queue()
    self.user_not_talking = asyncio.Event()
    self.user_not_talking.set()
    self.rolling_prompt = window.RollingPrompt()

  def end_conversation(self):
    async def _end_conversation():
      await asyncio.sleep(5)
      self.output_queue.put_nowait(None)

    processor.create_task(_end_conversation())

  async def test_output_order_ok(self):
    model = realtime._RealTimeConversationModel(
        output_queue=self.output_queue,
        generation=model_fake,
        rolling_prompt=self.rolling_prompt,
        user_not_talking=self.user_not_talking,
    )
    model.user_input(ProcessorPart('hello'))
    model.user_input(ProcessorPart('world'))

    await model.turn()
    model.user_input(ProcessorPart('done', role='user'))

    self.end_conversation()
    output_parts = await streams.gather_stream(
        streams.dequeue(self.output_queue)
    )
    actual = content_api.as_text(output_parts, substream_name='')
    self.assertSequenceEqual(actual, 'model(helloworld)')

  async def test_prompt_order_ok(self):
    model = realtime._RealTimeConversationModel(
        output_queue=self.output_queue,
        generation=model_fake,
        rolling_prompt=self.rolling_prompt,
        user_not_talking=self.user_not_talking,
    )
    model.user_input(ProcessorPart('hello'))
    model.user_input(ProcessorPart('world'))
    await model.turn()

    self.end_conversation()
    _ = await streams.gather_stream(streams.dequeue(self.output_queue))

    await self.rolling_prompt.finalize_pending()
    prompt_pending = self.rolling_prompt.pending()
    await self.rolling_prompt.finalize_pending()
    prompt_actual = await streams.gather_stream(prompt_pending)
    self.assertSequenceEqual(
        content_api.as_text(prompt_actual, substream_name=''),
        'helloworldmodel(helloworld)',
    )

  async def test_early_cancel_does_not_orphan_inner_coroutine(self):
    with warnings.catch_warnings(record=True) as caught:
      warnings.simplefilter('always', RuntimeWarning)
      model = realtime._RealTimeConversationModel(
          output_queue=self.output_queue,
          generation=model_fake,
          rolling_prompt=self.rolling_prompt,
          user_not_talking=self.user_not_talking,
      )
      task = model._pending_generate_output
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)
      del model
      gc.collect()
      await asyncio.sleep(0)

    unawaited = [
        item
        for item in caught
        if issubclass(item.category, RuntimeWarning)
        and 'was never awaited' in str(item.message)
    ]
    self.assertEqual(unawaited, [])


if __name__ == '__main__':
  absltest.main()
