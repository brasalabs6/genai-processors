import asyncio
from pathlib import Path
import tempfile
import unittest

from genai_processors import content_api
from genai_processors import processor

from leonidas import config
from leonidas import runtime


class EchoProcessor(processor.Processor):

  async def call(self, content):
    async for part in content:
      yield content_api.ProcessorPart(f'echo:{part.text}', role='model')


class RuntimeTest(unittest.IsolatedAsyncioTestCase):

  async def asyncSetUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    self.store = config.ConfigStore(Path(self.temp_dir.name) / 'config.json')
    self.outputs = []
    self.instances = []

    def factory(_):
      instance = EchoProcessor()
      self.instances.append(instance)
      return instance

    self.manager = runtime.SessionManager(self.store, factory, stop_timeout=0.2)
    await self.manager.attach_media(self.outputs.append)

  async def asyncTearDown(self):
    await self.manager.stop()
    await self.manager.detach_media()
    self.temp_dir.cleanup()

  async def test_start_requires_media_connection(self):
    await self.manager.detach_media()
    with self.assertRaises(runtime.MediaNotConnectedError):
      await self.manager.start()

  async def test_stop_and_restart_use_fresh_processor_and_stream(self):
    await self.manager.start()
    await self.manager.send(content_api.ProcessorPart('first', role='user'))
    await asyncio.sleep(0)
    await self.manager.stop()

    await self.manager.start()
    await self.manager.send(content_api.ProcessorPart('second', role='user'))
    for _ in range(10):
      if len(self.outputs) == 2:
        break
      await asyncio.sleep(0)

    self.assertEqual(len(self.instances), 2)
    self.assertEqual(
        [part.text for part in self.outputs],
        [
            'echo:first',
            'echo:second',
        ],
    )
    self.assertEqual(self.manager.snapshot()['state'], 'running')

  async def test_stop_is_idempotent(self):
    await self.manager.start()
    await self.manager.stop()
    await self.manager.stop()
    self.assertEqual(self.manager.snapshot()['state'], 'stopped')

  async def test_local_start_prepares_in_background_before_running(self):
    prepare = asyncio.Event()
    calls = []

    async def preparer(_config):
      calls.append('prepare')
      await prepare.wait()

    manager = runtime.SessionManager(
        self.store,
        lambda _config: EchoProcessor(),
        pipeline_preparer=preparer,
        requires_preparation=lambda _config: True,
        stop_timeout=0.2,
    )
    await manager.attach_media(self.outputs.append)

    snapshot = await manager.start()
    self.assertEqual(snapshot['state'], 'starting')
    self.assertEqual(calls, [])
    await asyncio.sleep(0)
    self.assertEqual(calls, ['prepare'])

    prepare.set()
    for _ in range(10):
      if manager.snapshot()['state'] == 'running':
        break
      await asyncio.sleep(0)
    self.assertEqual(manager.snapshot()['state'], 'running')
    await manager.stop()
    await manager.detach_media()

  async def test_stop_during_preparation_never_starts_stale_session(self):
    prepare = asyncio.Event()

    async def preparer(_config):
      await prepare.wait()

    manager = runtime.SessionManager(
        self.store,
        lambda _config: EchoProcessor(),
        pipeline_preparer=preparer,
        requires_preparation=lambda _config: True,
        stop_timeout=0.2,
    )
    await manager.attach_media(self.outputs.append)
    await manager.start()
    await asyncio.sleep(0)
    await manager.stop()
    prepare.set()
    await asyncio.sleep(0)

    self.assertEqual(manager.snapshot()['state'], 'stopped')
    self.assertEqual(manager.snapshot()['session_id'], None)
    await manager.detach_media()

  async def test_gemini_style_start_remains_synchronous(self):
    prepared = False

    async def preparer(_config):
      nonlocal prepared
      prepared = True

    manager = runtime.SessionManager(
        self.store,
        lambda _config: EchoProcessor(),
        pipeline_preparer=preparer,
        requires_preparation=lambda _config: False,
    )
    await manager.attach_media(self.outputs.append)

    snapshot = await manager.start()

    self.assertEqual(snapshot['state'], 'running')
    self.assertFalse(prepared)
    await manager.stop()
    await manager.detach_media()

  async def test_background_failure_notifies_state_listeners(self):
    class FailingProcessor(processor.Processor):

      async def call(self, content):
        del content
        await asyncio.sleep(0)
        raise RuntimeError('provider failed')
        if False:
          yield None

    manager = runtime.SessionManager(
        self.store, lambda _: FailingProcessor(), stop_timeout=0.2
    )
    states = []
    await manager.attach_media(self.outputs.append)
    manager.add_state_listener(states.append)
    await manager.start()
    for _ in range(10):
      if states and states[-1]['state'] == 'error':
        break
      await asyncio.sleep(0)

    self.assertEqual(manager.snapshot()['state'], 'error')
    self.assertEqual(states[-1]['state'], 'error')
    await manager.stop()
    await manager.detach_media()

  async def test_preparation_failure_can_be_retried_without_reloading_page(
      self,
  ):
    attempts = 0

    async def preparer(_config):
      nonlocal attempts
      attempts += 1
      if attempts == 1:
        raise RuntimeError('temporary model load failure')

    manager = runtime.SessionManager(
        self.store,
        lambda _: EchoProcessor(),
        pipeline_preparer=preparer,
        requires_preparation=lambda _config: True,
        stop_timeout=0.2,
    )
    await manager.attach_media(self.outputs.append)

    await manager.start()
    for _ in range(20):
      if manager.snapshot()['state'] == 'error':
        break
      await asyncio.sleep(0)
    self.assertEqual(manager.snapshot()['state'], 'error')

    # A retry from the error state must create a fresh preparation/start path.
    await manager.start()
    for _ in range(20):
      if manager.snapshot()['state'] == 'running':
        break
      await asyncio.sleep(0)
    self.assertEqual(attempts, 2)
    self.assertEqual(manager.snapshot()['state'], 'running')
    await manager.stop()
    await manager.detach_media()


if __name__ == '__main__':
  unittest.main()
