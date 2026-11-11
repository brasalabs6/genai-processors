"""Integration tests: real GenAI Processor pipeline, fake backend only."""

import unittest

from genai_processors import content_api
from genai_processors import processor

from universal_ai import streaming
from universal_ai.contracts import ConversationNeeds
from universal_ai.contracts import ProviderCapabilities


class FakeBackend(processor.Processor):

  async def call(self, content):
    async for part in content:
      yield part


class StreamingTest(unittest.IsolatedAsyncioTestCase):

  async def test_stamping_preserves_part_and_metadata(self):
    image = content_api.ProcessorPart(
        b'not-decoded-by-test',
        mimetype='image/jpeg',
        substream_name='realtime',
        role='user',
        metadata={'private_key': 'kept'},
    )
    results = await streaming.StampSource('camera', clock=lambda: 100)(
        [image]
    ).gather()
    stamped = results[0]
    self.assertEqual(stamped.bytes, image.bytes)
    self.assertEqual(stamped.substream_name, 'realtime')
    self.assertEqual(stamped.get_metadata('private_key'), 'kept')
    self.assertEqual(stamped.get_metadata('ua_sequence'), 1)
    self.assertEqual(stamped.get_metadata('ua_received_ns'), 100)
    self.assertNotIn('ua_source', image.metadata)

  async def test_video_drop_does_not_drop_speech_or_controls(self):
    now = [1_000_000_000]
    clock = lambda: now[0]
    budget = streaming.VisionBudget(2.0, 2000, clock)
    image = lambda: content_api.ProcessorPart(
        b'frame', mimetype='image/jpeg', substream_name='realtime'
    )
    audio = content_api.ProcessorPart(
        b'pcm', mimetype='audio/pcm', substream_name='realtime'
    )
    control = content_api.ProcessorPart(
        '', mimetype='application/x-state', metadata={'interrupted': True}
    )
    results = await budget([image(), image(), audio, control]).gather()
    self.assertEqual(len(results), 3)
    self.assertEqual(results[1].bytes, audio.bytes)
    self.assertTrue(results[2].get_metadata('interrupted'))
    self.assertEqual(budget.dropped_rate, 1)

  async def test_stale_video_dropped(self):
    old = content_api.ProcessorPart(
        b'frame',
        mimetype='image/jpeg',
        substream_name='realtime',
        metadata={'ua_received_ns': 1},
    )
    result = await streaming.VisionBudget(
        2.0, 100, clock=lambda: 200_000_001
    )([old]).gather()
    self.assertEqual(len(result), 0)

  async def test_sources_and_backend_keep_source_identity(self):
    async def source(value):
      yield content_api.ProcessorPart(value, role='user')

    capability = ProviderCapabilities(
        provider_id='mock',
        input_modalities=frozenset({'text'}),
        output_modalities=frozenset({'text'}),
    )
    output = [
        part
        async for part in streaming.run_conversation(
            FakeBackend(),
            capability,
            ConversationNeeds(),
            {'terminal': source('hello'), 'sensor': source('world')},
        )
    ]
    self.assertEqual({p.text for p in output}, {'hello', 'world'})
    self.assertEqual(
        {p.get_metadata('ua_source') for p in output},
        {'terminal', 'sensor'},
    )


if __name__ == '__main__':
  unittest.main()
