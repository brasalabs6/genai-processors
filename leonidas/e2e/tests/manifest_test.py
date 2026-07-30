from pathlib import Path
import unittest

from leonidas.e2e import manifest


class ManifestTest(unittest.TestCase):

  def test_canonical_manifest_is_valid_and_deterministic(self):
    scenarios = manifest.load(Path(__file__).parents[1] / 'scenarios.json')
    self.assertEqual(
        [item.id for item in scenarios], ['red_object_on_desk_ptbr']
    )
    self.assertIn('Leonidas', scenarios[0].audio_script)
    self.assertGreaterEqual(scenarios[0].timeout_seconds, 20)

  def test_rejects_path_unsafe_scenario_id(self):
    with self.assertRaisesRegex(ValueError, 'scenario id'):
      manifest.Scenario.from_dict(
          {
              'id': '../escape',
              'description': 'test',
              'image_prompt': 'image',
              'audio_script': 'audio',
              'expected_terms': [],
              'timeout_seconds': 30,
              'minimum_audio_seconds': 0.25,
          }
      )


if __name__ == '__main__':
  unittest.main()
