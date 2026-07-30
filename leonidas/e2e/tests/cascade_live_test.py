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


if __name__ == '__main__':
  unittest.main()
