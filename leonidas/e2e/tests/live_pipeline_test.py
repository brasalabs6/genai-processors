import os
from pathlib import Path
import unittest

from leonidas import capabilities
from leonidas.e2e import generate_assets
from leonidas.e2e import manifest
from leonidas.e2e import run


@unittest.skipUnless(
    os.environ.get('LEONIDAS_RUN_LIVE_E2E') == '1',
    'Set LEONIDAS_RUN_LIVE_E2E=1 for paid provider tests',
)
class LivePipelineTest(unittest.IsolatedAsyncioTestCase):

  async def test_both_gemini_profiles_with_generated_media(self):
    scenarios = manifest.load(Path(__file__).parents[1] / 'scenarios.json')
    results = await run.run_models(
        api_key=os.environ['GOOGLE_API_KEY'],
        models=(capabilities.MODEL_LIVE_2_5, capabilities.MODEL_LIVE_3_1),
        scenarios=scenarios,
        asset_root=generate_assets.DEFAULT_ASSET_ROOT,
    )
    self.assertTrue(results)
    self.assertTrue(all(result.passed for result in results), results)


if __name__ == '__main__':
  unittest.main()
