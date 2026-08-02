import unittest

from leonidas.e2e import coexistence_smoke


class CoexistenceSmokeTest(unittest.IsolatedAsyncioTestCase):

  def test_requires_every_local_component_to_be_ready(self):
    snapshot = {
        'overall_state': 'ready',
        'components': [
            {'id': 'stt', 'state': 'ready'},
            {'id': 'tts', 'state': 'ready'},
            {'id': 'diarization', 'state': 'unavailable'},
        ],
    }

    self.assertFalse(coexistence_smoke.all_resources_ready(snapshot))
    snapshot['components'][2]['state'] = 'ready'
    self.assertTrue(coexistence_smoke.all_resources_ready(snapshot))

  def test_failure_codes_are_actionable_and_redacted(self):
    self.assertEqual(
        coexistence_smoke.failure_code(
            coexistence_smoke.diarization_process.DiarizationWorkerError(
                'private provider detail'
            )
        ),
        'diarization_unavailable_or_unauthorized',
    )
    self.assertEqual(
        coexistence_smoke.failure_code(RuntimeError('unknown private detail')),
        'unexpected_runtime_failure',
    )

  async def test_closes_resources_when_diarization_load_fails(self):
    class Pool:

      def __init__(self):
        self.closed = False

      async def ensure_ready(self, *_args, **kwargs):
        self.diarization_enabled = kwargs['diarization_enabled']
        raise RuntimeError('gated model')

      async def close(self):
        self.closed = True

    pool = Pool()

    phases = []
    with self.assertRaisesRegex(RuntimeError, 'gated model'):
      await coexistence_smoke.run(
          audio=b'audio',
          diarization_audio=b'diarization',
          voice_path=None,
          device='cuda',
          pool_factory=lambda _voice: pool,
          cascade_runner=lambda *_args, **_kwargs: self.fail(
              'cascade must not run after failed model load'
          ),
          memory_probe=lambda phase: phases.append(phase) or {},
      )

    self.assertTrue(pool.diarization_enabled)
    self.assertTrue(pool.closed)
    self.assertEqual(phases, ['before_load', 'after_cleanup'])

  async def test_runs_real_contract_with_three_resident_workers(self):
    class Diarizer:

      async def diarize(self, audio, *, sample_rate):
        self.request = (audio, sample_rate)
        return [
            type('Segment', (), {'speaker_id': 'A'})(),
            type('Segment', (), {'speaker_id': 'B'})(),
        ]

    class Pool:

      def __init__(self):
        self.closed = False
        self.worker = Diarizer()

      async def ensure_ready(self, *_args, **kwargs):
        self.diarization_enabled = kwargs['diarization_enabled']
        return {
            'overall_state': 'ready',
            'components': [
                {'id': 'stt', 'state': 'ready'},
                {'id': 'tts', 'state': 'ready'},
                {'id': 'diarization', 'state': 'ready'},
            ],
        }

      def diarizer(self, _device):
        return self.worker

      async def close(self):
        self.closed = True

    phases = []
    cascade_calls = []
    pool = Pool()

    async def cascade_runner(pool_arg, audio, device, turns, diarizer):
      cascade_calls.append((pool_arg, audio, device, turns, diarizer))

    result = await coexistence_smoke.run(
        audio=b'turn-audio',
        diarization_audio=b'two-speaker-audio',
        voice_path=None,
        device='cuda',
        pool_factory=lambda _voice: pool,
        cascade_runner=cascade_runner,
        memory_probe=lambda phase: phases.append(phase) or {'phase': phase},
    )

    self.assertEqual(
        phases,
        [
            'before_load',
            'models_ready',
            'after_diarization',
            'complete',
            'after_cleanup',
        ],
    )
    self.assertEqual(pool.worker.request, (b'two-speaker-audio', 16000))
    self.assertEqual(len(cascade_calls), 1)
    self.assertEqual(cascade_calls[0][2:4], ('cuda', 3))
    self.assertIs(cascade_calls[0][4], pool.worker)
    self.assertTrue(pool.closed)
    self.assertEqual(result['speakers'], 2)
    self.assertEqual(result['turns'], 3)


if __name__ == '__main__':
  unittest.main()
