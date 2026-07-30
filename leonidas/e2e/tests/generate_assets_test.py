from pathlib import Path
import tempfile
import unittest
import base64

from PIL import Image

from leonidas.e2e import generate_assets
from leonidas.e2e import manifest
from leonidas.e2e.tests.assets_test import _wave_bytes


class FakeAudioGenerator:

  async def generate(self, script):
    self.script = script
    return _wave_bytes()


class FakeImageGenerator:

  async def generate(self, prompt):
    self.prompt = prompt
    path_bytes = __import__('io').BytesIO()
    Image.new('RGB', (1280, 720), 'red').save(path_bytes, format='PNG')
    return path_bytes.getvalue()


class GenerateAssetsTest(unittest.IsolatedAsyncioTestCase):

  async def test_gemini_audio_generator_uses_tts_and_wraps_pcm_as_wav(self):
    class Interactions:

      def create(inner_self, **kwargs):
        inner_self.kwargs = kwargs
        return type(
            'Interaction',
            (),
            {
                'output_audio': type(
                    'Audio',
                    (),
                    {'data': base64.b64encode(b'\x00\x00' * 7200).decode()},
                )()
            },
        )()

    interactions = Interactions()
    client = type('Client', (), {'interactions': interactions})()
    generator = generate_assets.GeminiAudioGenerator('ignored', client=client)
    wav = await generator.generate('Leia isto.')
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'fixture.wav'
      path.write_bytes(wav)
      self.assertEqual(
          generate_assets.assets.validate_audio(path).sample_rate, 24000
      )
    self.assertEqual(
        interactions.kwargs['model'], 'gemini-3.1-flash-tts-preview'
    )
    self.assertIn('Leia isto.', interactions.kwargs['input'])

  async def test_generates_and_validates_both_assets_atomically(self):
    scenario = manifest.Scenario.from_dict(
        {
            'id': 'demo',
            'description': 'demo',
            'image_prompt': 'red mug',
            'audio_script': 'hello',
            'expected_terms': [],
            'timeout_seconds': 30,
            'minimum_audio_seconds': 0.25,
        }
    )
    with tempfile.TemporaryDirectory() as temp_dir:
      generated = await generate_assets.generate_scenario(
          scenario,
          Path(temp_dir),
          FakeAudioGenerator(),
          FakeImageGenerator(),
      )
      self.assertTrue(generated.audio_path.is_file())
      self.assertTrue(generated.image_path.is_file())
      self.assertEqual(generated.image_source, 'gemini')
      self.assertFalse(any(Path(temp_dir).glob('*.tmp')))

  async def test_explicit_synthetic_generator_is_visibly_labeled(self):
    generated = await generate_assets.SyntheticImageGenerator().generate(
        'ignored by deterministic fixture'
    )
    self.assertTrue(generated.startswith(b'\x89PNG'))


if __name__ == '__main__':
  unittest.main()
