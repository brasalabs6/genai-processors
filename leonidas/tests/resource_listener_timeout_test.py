import asyncio
import unittest

from leonidas.cascade import resources


class _Resource:

  async def load(self, progress=None):
    if progress is not None:
      await progress('warming')
    return {'device': 'cpu'}

  async def close(self):
    pass


class ResourceListenerTimeoutTest(unittest.IsolatedAsyncioTestCase):

  async def test_stalled_listener_cannot_block_model_preparation(self):
    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=lambda **_kwargs: _Resource(),
        synthesizer_factory=lambda **_kwargs: _Resource(),
        listener_timeout=0.01,
    )
    entered = asyncio.Event()

    async def stalled_listener(_snapshot):
      entered.set()
      await asyncio.Future()

    pool.add_listener(stalled_listener)

    snapshot = await asyncio.wait_for(
        pool.ensure_ready('stt', 'tts', 'cpu'), timeout=0.2
    )

    self.assertTrue(entered.is_set())
    self.assertEqual(snapshot['overall_state'], 'ready')
    self.assertNotIn(stalled_listener, pool._listeners)
    await pool.close()

  async def test_invalid_listener_timeout_is_rejected(self):
    with self.assertRaisesRegex(ValueError, 'positive'):
      resources.CascadeResources(voices={}, listener_timeout=0)


if __name__ == '__main__':
  unittest.main()
