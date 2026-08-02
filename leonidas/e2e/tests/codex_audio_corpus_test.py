"""Tests for the private Codex microphone corpus generator."""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from leonidas.e2e import codex_audio_corpus
from leonidas.e2e import generate_assets


class CodexAudioCorpusTest(unittest.TestCase):

  def test_generates_valid_redacted_multiturn_manifest(self):
    class ValidGenerator:

      async def generate(self, script: str) -> bytes:
        del script
        import io
        import wave

        output = io.BytesIO()
        with wave.open(output, 'wb') as wav_file:
          wav_file.setnchannels(1)
          wav_file.setsampwidth(2)
          wav_file.setframerate(24000)
          wav_file.writeframes(b'\x01\x00' * 24000)
        return output.getvalue()

    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      generated = asyncio.run(
          codex_audio_corpus.generate_corpus(
              root,
              ValidGenerator(),
              scripts=(
                  codex_audio_corpus.CorpusTurn('turn-1', 'Primeira fala.'),
                  codex_audio_corpus.CorpusTurn('turn-2', 'Segunda fala.'),
              ),
          )
      )

      self.assertEqual(len(generated), 2)
      for path in generated:
        self.assertEqual(
            generate_assets.assets.validate_audio(path).sample_rate, 24000
        )
      manifest = json.loads((root / 'manifest.json').read_text())
      self.assertEqual(manifest['schema_version'], 1)
      self.assertEqual(len(manifest['turns']), 2)
      serialized = json.dumps(manifest)
      self.assertNotIn('Primeira fala', serialized)
      self.assertNotIn('Segunda fala', serialized)
      self.assertEqual(len(manifest['turns'][0]['sha256']), 64)


if __name__ == '__main__':
  unittest.main()
