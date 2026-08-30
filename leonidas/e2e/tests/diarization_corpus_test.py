"""Tests for the private two-human-voice diarization corpus."""

from pathlib import Path
import io
import tempfile
import unittest
import wave

from leonidas.e2e import diarization_corpus


class FakeGenerator:

  def __init__(self, marker: int, seconds: float = 0.5):
    self._marker = marker
    self._seconds = seconds

  async def generate(self, script: str) -> bytes:
    del script
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav_file:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(24000)
      wav_file.writeframes(
          self._marker.to_bytes(2, 'little') * int(24000 * self._seconds)
      )
    return output.getvalue()


class DiarizationCorpusTest(unittest.IsolatedAsyncioTestCase):

  async def test_builds_non_overlapping_two_voice_wav_and_redacted_manifest(
      self,
  ):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      result = await diarization_corpus.generate_corpus(
          root,
          (FakeGenerator(100), FakeGenerator(200)),
          silence_seconds=1.0,
      )

      self.assertEqual(result.speakers, 2)
      self.assertTrue(result.audio_path.is_file())
      with wave.open(str(result.audio_path), 'rb') as source:
        self.assertEqual(source.getframerate(), 24000)
        self.assertEqual(source.getnchannels(), 1)
      manifest = (root / 'manifest.json').read_text()
      self.assertIn('"speakers": 2', manifest)
      self.assertNotIn('Primeira voz', manifest)
      self.assertFalse(any(root.glob('*.tmp')))

  async def test_combined_corpus_may_exceed_single_turn_limit(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      result = await diarization_corpus.generate_corpus(
          Path(temp_dir),
          (FakeGenerator(100, 5.0), FakeGenerator(200, 5.0)),
          silence_seconds=1.0,
      )

      self.assertAlmostEqual(result.duration_seconds, 11.0)


if __name__ == '__main__':
  unittest.main()
