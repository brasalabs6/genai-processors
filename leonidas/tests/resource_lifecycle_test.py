import asyncio
import unittest

from leonidas.cascade import resources


class ResourceLifecycleTest(unittest.IsolatedAsyncioTestCase):

  async def test_successful_generation_closes_and_evicts_previous_workers(self):
    created = {}

    class Resource:

      def __init__(self, model_id):
        self.model_id = model_id
        self.closed = False

      async def load(self, progress=None):
        del progress
        return {'device': 'cpu'}

      async def close(self):
        self.closed = True

    def factory(**kwargs):
      value = Resource(kwargs['model_id'])
      created.setdefault(kwargs['model_id'], []).append(value)
      return value

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=factory,
        synthesizer_factory=factory,
    )
    await pool.ensure_ready('stt-a', 'tts-a', 'cpu')
    first_generation = pool.snapshot()['generation']
    await pool.ensure_ready('stt-b', 'tts-b', 'cpu')

    self.assertEqual(pool.snapshot()['generation'], first_generation + 1)
    self.assertTrue(created['stt-a'][0].closed)
    self.assertTrue(created['tts-a'][0].closed)
    self.assertFalse(created['stt-b'][0].closed)
    self.assertFalse(created['tts-b'][0].closed)
    self.assertEqual(list(pool._transcribers), [('stt-b', 'cpu')])
    self.assertEqual(list(pool._synthesizers), [('tts-b', 'cpu')])
    await pool.close()

  async def test_failed_candidate_is_closed_and_active_status_is_restored(self):
    created = {}
    failing_tts_attempts = 0

    class Resource:

      def __init__(self, model_id, should_fail=False):
        self.model_id = model_id
        self.should_fail = should_fail
        self.closed = False

      async def load(self, progress=None):
        del progress
        if self.should_fail:
          raise RuntimeError('candidate failed')
        return {'device': 'cpu'}

      async def close(self):
        self.closed = True

    def factory(**kwargs):
      nonlocal failing_tts_attempts
      model_id = kwargs['model_id']
      should_fail = False
      if model_id == 'tts-b':
        failing_tts_attempts += 1
        should_fail = failing_tts_attempts == 1
      value = Resource(model_id, should_fail)
      created.setdefault(model_id, []).append(value)
      return value

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=factory,
        synthesizer_factory=factory,
    )
    await pool.ensure_ready('stt-a', 'tts-a', 'cpu')
    active_generation = pool.snapshot()['generation']

    with self.assertRaisesRegex(RuntimeError, 'candidate failed'):
      await pool.ensure_ready('stt-b', 'tts-b', 'cpu')

    failed_snapshot = pool.snapshot()
    self.assertEqual(failed_snapshot['overall_state'], 'ready')
    self.assertEqual(failed_snapshot['generation'], active_generation)
    self.assertEqual(failed_snapshot['last_error']['stage'], 'tts')
    self.assertFalse(created['stt-a'][0].closed)
    self.assertFalse(created['tts-a'][0].closed)
    self.assertTrue(created['stt-b'][0].closed)
    self.assertTrue(created['tts-b'][0].closed)
    self.assertEqual(list(pool._transcribers), [('stt-a', 'cpu')])
    self.assertEqual(list(pool._synthesizers), [('tts-a', 'cpu')])

    successful = await pool.ensure_ready('stt-b', 'tts-b', 'cpu')
    self.assertEqual(successful['overall_state'], 'ready')
    self.assertEqual(successful['generation'], active_generation + 1)
    self.assertIsNone(successful['last_error'])
    self.assertEqual(len(created['stt-b']), 2)
    self.assertEqual(len(created['tts-b']), 2)
    await pool.close()

  async def test_failed_diarization_toggle_preserves_active_shared_workers(self):
    created = {}

    class Resource:

      def __init__(self, model_id, *, should_fail=False):
        self.model_id = model_id
        self.should_fail = should_fail
        self.closed = False

      async def load(self, progress=None):
        del progress
        if self.should_fail:
          raise RuntimeError('diarization candidate failed')
        return {'device': 'cpu'}

      async def close(self):
        self.closed = True

    def model_factory(**kwargs):
      value = Resource(kwargs['model_id'])
      created.setdefault(kwargs['model_id'], []).append(value)
      return value

    diarizers = []

    def diarizer_factory(**_kwargs):
      value = Resource('diarization', should_fail=True)
      diarizers.append(value)
      return value

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=model_factory,
        synthesizer_factory=model_factory,
        diarizer_factory=diarizer_factory,
    )
    ready = await pool.ensure_ready(
        'stt-a', 'tts-a', 'cpu', diarization_enabled=False
    )
    active_generation = ready['generation']
    active_stt = created['stt-a'][0]
    active_tts = created['tts-a'][0]

    with self.assertRaisesRegex(RuntimeError, 'diarization candidate failed'):
      await pool.ensure_ready(
          'stt-a', 'tts-a', 'cpu', diarization_enabled=True
      )

    failed = pool.snapshot()
    self.assertEqual(failed['overall_state'], 'ready')
    self.assertEqual(failed['generation'], active_generation)
    self.assertFalse(active_stt.closed)
    self.assertFalse(active_tts.closed)
    self.assertTrue(diarizers[0].closed)
    self.assertIs(pool._transcribers[('stt-a', 'cpu')], active_stt)
    self.assertIs(pool._synthesizers[('tts-a', 'cpu')], active_tts)
    self.assertNotIn('cpu', pool._diarizers)

    restored = await pool.ensure_ready(
        'stt-a', 'tts-a', 'cpu', diarization_enabled=False
    )
    self.assertEqual(restored['generation'], active_generation)
    self.assertEqual(len(created['stt-a']), 1)
    self.assertEqual(len(created['tts-a']), 1)
    await pool.close()

  async def test_waiter_for_another_key_does_not_inherit_failed_generation(
      self,
  ):
    loaded = []

    class Resource:

      def __init__(self, model_id):
        self.model_id = model_id

      async def load(self, progress=None):
        del progress
        loaded.append(self.model_id)
        await asyncio.sleep(0)
        if self.model_id == 'stt-failing':
          raise RuntimeError('candidate failed')
        return {'device': 'cpu'}

      async def close(self):
        pass

    def factory(**kwargs):
      return Resource(kwargs['model_id'])

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=factory,
        synthesizer_factory=factory,
    )

    failed, successful = await asyncio.gather(
        pool.ensure_ready('stt-failing', 'tts-failing', 'cpu'),
        pool.ensure_ready('stt-good', 'tts-good', 'cpu'),
        return_exceptions=True,
    )

    self.assertIsInstance(failed, RuntimeError)
    self.assertIsInstance(successful, dict)
    self.assertEqual(successful['overall_state'], 'ready')
    self.assertEqual(loaded, ['stt-failing', 'stt-good', 'tts-good'])
    await pool.close()

  async def test_close_cancels_inflight_preparation_before_closing_worker(self):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingResource:

      def __init__(self):
        self.closed = False

      async def load(self, progress=None):
        del progress
        started.set()
        try:
          await asyncio.Future()
        except asyncio.CancelledError:
          cancelled.set()
          raise

      async def close(self):
        self.closed = True

    stt = BlockingResource()
    tts = BlockingResource()
    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=lambda **_kwargs: stt,
        synthesizer_factory=lambda **_kwargs: tts,
    )
    preparation = asyncio.create_task(pool.ensure_ready('stt', 'tts', 'cpu'))
    await started.wait()

    await asyncio.wait_for(pool.close(), timeout=0.2)
    await asyncio.gather(preparation, return_exceptions=True)

    self.assertTrue(cancelled.is_set())
    self.assertTrue(stt.closed)
    self.assertTrue(tts.closed)


if __name__ == '__main__':
  unittest.main()
