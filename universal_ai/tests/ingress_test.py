"""Bounded source queue tests with no API or hardware dependencies."""

import asyncio
import unittest

from universal_ai.contracts import SourceSettings
from universal_ai.ingress import BoundedIngress


class IngressTest(unittest.IsolatedAsyncioTestCase):

  async def test_camera_drops_oldest_when_full(self):
    ingress = BoundedIngress[int](
        SourceSettings('camera', 'image', capacity=2, overflow='drop_oldest')
    )
    for i in range(4):
      await ingress.publish(i)
    self.assertEqual(ingress.dropped, 2)
    await ingress.close()
    self.assertEqual([i async for i in ingress.stream()], [3])
    # Closing a full replaceable queue discards one more frame to signal EOF.
    self.assertEqual(ingress.dropped, 3)

  async def test_audio_backpressures_instead_of_dropping(self):
    ingress = BoundedIngress[int](
        SourceSettings('microphone', 'audio', capacity=1)
    )
    await ingress.publish(1)
    producer = asyncio.create_task(ingress.publish(2))
    await asyncio.sleep(0)
    self.assertFalse(producer.done())
    stream = ingress.stream()
    self.assertEqual(await anext(stream), 1)
    await asyncio.wait_for(producer, 1)
    # Already queued audio is kept, and EOF may wait for a consumer.
    close_task = asyncio.create_task(ingress.close())
    self.assertEqual(await anext(stream), 2)
    await asyncio.wait_for(close_task, 1)
    with self.assertRaises(StopAsyncIteration):
      await anext(stream)
    self.assertEqual(ingress.dropped, 0)

  async def test_cannot_publish_after_close(self):
    ingress = BoundedIngress[int](SourceSettings('text', 'text'))
    await ingress.close()
    with self.assertRaises(RuntimeError):
      await ingress.publish(1)


if __name__ == '__main__':
  unittest.main()
