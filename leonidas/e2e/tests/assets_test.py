import io
from pathlib import Path
import tempfile
import unittest
import wave

from PIL import Image

from leonidas.e2e import assets


def _wave_bytes(sample_rate=24000, seconds=0.3):
  output = io.BytesIO()
  with wave.open(output, 'wb') as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    wav_file.writeframes(b'\x00\x00' * int(sample_rate * seconds))
  return output.getvalue()


class AssetValidationTest(unittest.TestCase):

  def test_validates_generated_wave_and_image(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      audio = root / 'demo.wav'
      image = root / 'demo.png'
      audio.write_bytes(_wave_bytes())
      Image.new('RGB', (1280, 720), 'red').save(image)

      audio_info = assets.validate_audio(audio)
      image_info = assets.validate_image(image)

      self.assertEqual(audio_info.sample_rate, 24000)
      self.assertGreaterEqual(audio_info.duration_seconds, 0.25)
      self.assertEqual((image_info.width, image_info.height), (1280, 720))

  def test_rejects_wrong_audio_format(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'demo.wav'
      path.write_bytes(_wave_bytes(sample_rate=16000))
      with self.assertRaisesRegex(ValueError, '24000'):
        assets.validate_audio(path)


if __name__ == '__main__':
  unittest.main()
