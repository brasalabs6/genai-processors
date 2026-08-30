import asyncio
from pathlib import Path
import tempfile
import unittest

from genai_processors import content_api
from genai_processors import processor

from leonidas import config
from leonidas import runtime


class _EchoProcessor(processor.Processor):

  async def call(self, content):
    async for part in content:
      yield content_api.ProcessorPart(part.text, role='model')


class StateListenerTimeoutTest(unittest.IsolatedAsyncioTestCase):

  async def test_stalled_listener_is_removed_without_stalling_start(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      manager = runtime.SessionManager(
          store,
          lambda _config: _EchoProcessor(),
          stop_timeout=0.2,
          state_listener_timeout=0.01,
      )
      outputs = []
      entered = asyncio.Event()

      async def stalled_listener(_snapshot):
        entered.set()
        await asyncio.Future()

      await manager.attach_media(outputs.append)
      manager.add_state_listener(stalled_listener)

      snapshot = await asyncio.wait_for(manager.start(), timeout=0.1)

      self.assertTrue(entered.is_set())
      self.assertEqual(snapshot['state'], 'running')
      self.assertNotIn(stalled_listener, manager._state_listeners)
      await manager.stop()
      await manager.detach_media()

  async def test_invalid_listener_timeout_is_rejected(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      with self.assertRaisesRegex(ValueError, 'positive'):
        runtime.SessionManager(
            store,
            lambda _config: _EchoProcessor(),
            state_listener_timeout=0,
        )


if __name__ == '__main__':
  unittest.main()
