"""Contract tests for paced Codex microphone audio input."""

import asyncio
from pathlib import Path
import tempfile
import unittest
import wave

from leonidas import codex_app_server
from leonidas.e2e import codex_audio_smoke


class CodexAudioSmokeTest(unittest.TestCase):

  def test_classifies_public_failures_without_provider_payloads(self):
    self.assertEqual(
        codex_audio_smoke.failure_code(
            codex_app_server.CodexProtocolError(
                'realtime conversation requires API key auth'
            )
        ),
        'api_key_required',
    )
    self.assertEqual(
        codex_audio_smoke.failure_code(
            codex_app_server.CodexProtocolError(
                "unknown variant 'v3', expected 'v1' or 'v2'"
            )
        ),
        'protocol_version_unsupported',
    )

  def test_streams_pcm_as_paced_microphone_chunks_with_trailing_silence(self):
    class FakeClient:

      def __init__(self):
        self.frames = []

      async def append_audio(self, data, *, sample_rate, num_channels):
        self.frames.append((data, sample_rate, num_channels))

    async def no_sleep(_seconds):
      return None

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'turn.wav'
      with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b'\x01\x00' * 24000)
      client = FakeClient()
      asyncio.run(
          codex_audio_smoke.stream_microphone_turn(
              client,
              path,
              chunk_ms=100,
              trailing_silence_ms=300,
              sleep=no_sleep,
          )
      )

    self.assertGreater(len(client.frames), 10)
    self.assertTrue(all(rate == 16000 for _, rate, _ in client.frames))
    self.assertTrue(all(channels == 1 for _, _, channels in client.frames))
    self.assertEqual(client.frames[-1][0], bytes(3200))


if __name__ == '__main__':
  unittest.main()
