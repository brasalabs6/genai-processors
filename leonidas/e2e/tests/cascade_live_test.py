import os
import unittest

from leonidas.e2e import cascade_smoke


@unittest.skipUnless(
    os.environ.get('LEONIDAS_RUN_CASCADE_E2E') == '1',
    'Set LEONIDAS_RUN_CASCADE_E2E=1 after reviewing the XTTS license',
)
class CascadeLiveTest(unittest.IsolatedAsyncioTestCase):

  async def test_real_audio_through_parakeet_groq_and_xtts(self):
    await cascade_smoke.run(
        cascade_smoke.DEFAULT_AUDIO,
        cascade_smoke.DEFAULT_VOICE,
        os.environ.get('LEONIDAS_CASCADE_DEVICE', 'auto'),
    )


class CascadeSmokeContractTest(unittest.TestCase):

  def test_optional_diarization_does_not_invalidate_audio_readiness(self):
    snapshot = {
        'overall_state': 'ready',
        'components': [
            {'id': 'stt', 'state': 'ready'},
            {'id': 'tts', 'state': 'ready'},
            {'id': 'diarization', 'state': 'unavailable'},
        ],
    }
    self.assertTrue(cascade_smoke.required_resources_ready(snapshot))


if __name__ == '__main__':
  unittest.main()
