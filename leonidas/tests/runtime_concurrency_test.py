import asyncio
from pathlib import Path
import tempfile
import unittest

from genai_processors import content_api
from genai_processors import processor

from leonidas import config
from leonidas import runtime
from leonidas import telemetry


class EchoProcessor(processor.Processor):

  async def call(self, content):
    async for part in content:
      yield content_api.ProcessorPart(part.text, role='model')


class RuntimeConcurrencyTest(unittest.IsolatedAsyncioTestCase):

  async def test_stop_waits_for_inflight_config_apply(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      prepare_started = asyncio.Event()
      release_prepare = asyncio.Event()

      async def preparer(agent_config):
        if agent_config.objective == 'candidate':
          prepare_started.set()
          await release_prepare.wait()

      manager = runtime.SessionManager(
          store,
          lambda _config: EchoProcessor(),
          pipeline_preparer=preparer,
          requires_preparation=lambda value: value.objective == 'candidate',
          stop_timeout=0.2,
      )
      await manager.attach_media(lambda _part: None)
      await manager.start()
      store.update_draft({'objective': 'candidate'}, expected_revision=0)

      apply_task = asyncio.create_task(manager.apply_config())
      await asyncio.wait_for(prepare_started.wait(), timeout=0.2)
      stop_task = asyncio.create_task(manager.stop())
      await asyncio.sleep(0)

      self.assertFalse(stop_task.done())
      release_prepare.set()
      await asyncio.wait_for(apply_task, timeout=0.2)
      await asyncio.wait_for(stop_task, timeout=0.2)
      self.assertEqual(manager.snapshot()['state'], 'stopped')
      await manager.detach_media()

  async def test_full_queue_drops_image_without_blocking_audio_budget(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      metrics = telemetry.MetricsStore()
      manager = runtime.SessionManager(
          store,
          lambda _config: EchoProcessor(),
          metrics=metrics,
          input_queue_timeout=0.01,
      )
      queue = asyncio.Queue(maxsize=1)
      queue.put_nowait(content_api.ProcessorPart('occupied'))
      manager._state = runtime.SessionState.RUNNING
      manager._input_queue = queue

      await manager.send(
          content_api.ProcessorPart(b'image', mimetype='image/jpeg')
      )

      snapshot = metrics.snapshot()
      self.assertEqual(snapshot['counters']['frames_dropped_backpressure'], 1)
      self.assertEqual(queue.qsize(), 1)
      await manager.stop()

  async def test_full_queue_bounds_non_droppable_input_wait(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      metrics = telemetry.MetricsStore()
      manager = runtime.SessionManager(
          store,
          lambda _config: EchoProcessor(),
          metrics=metrics,
          input_queue_timeout=0.01,
      )
      queue = asyncio.Queue(maxsize=1)
      queue.put_nowait(content_api.ProcessorPart('occupied'))
      manager._state = runtime.SessionState.RUNNING
      manager._input_queue = queue

      with self.assertRaises(runtime.InputBackpressureError):
        await manager.send(
            content_api.ProcessorPart(b'audio', mimetype='audio/pcm;rate=16000')
        )

      snapshot = metrics.snapshot()
      self.assertEqual(snapshot['counters']['input_backpressure_timeouts'], 1)
      await manager.stop()


if __name__ == '__main__':
  unittest.main()
