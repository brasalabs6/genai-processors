"""Contract tests for the Codex browser WebRTC smoke."""

from pathlib import Path
import tempfile
import unittest
import wave

from leonidas.e2e import codex_webrtc_smoke


def _write_wav(path: Path, seconds: int) -> None:
  with wave.open(str(path), 'wb') as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(24000)
    output.writeframes(b'\x01\x00' * 24000 * seconds)


class CodexWebRtcSmokeTest(unittest.TestCase):

  def test_browser_readiness_requires_rest_and_websocket(self):
    self.assertTrue(
        codex_webrtc_smoke.browser_ready(
            {'rest': 'API online', 'websocket': 'WebSocket online'}
        )
    )
    self.assertFalse(
        codex_webrtc_smoke.browser_ready(
            {'rest': 'API online', 'websocket': 'Conectando'}
        )
    )

  def test_combines_two_turns_with_endpointing_silence(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      first = root / 'first.wav'
      second = root / 'second.wav'
      combined = root / 'combined.wav'
      _write_wav(first, 5)
      _write_wav(second, 5)

      info = codex_webrtc_smoke.combine_microphone_audio(
          (first, second), combined, silence_seconds=2
      )

      self.assertEqual(info.turns, 2)
      self.assertAlmostEqual(info.duration_seconds, 12.0)
      with wave.open(str(combined), 'rb') as source:
        self.assertEqual(source.getframerate(), 24000)
        self.assertEqual(source.getnchannels(), 1)
        self.assertEqual(source.getsampwidth(), 2)

  def test_classifies_browser_entitlement_failure_without_detail(self):
    snapshot = {
        'session': 'Erro',
        'errorHidden': False,
        'errorDetail': (
            'Codex realtime voice access denied by the upstream service; '
            'verify that this Codex account has realtime voice entitlement.'
        ),
        'userMessages': 0,
        'modelMessages': 0,
    }
    result = codex_webrtc_smoke.evaluate_snapshot(snapshot)
    self.assertFalse(result.passed)
    self.assertEqual(result.code, 'voice_entitlement_denied')
    self.assertNotIn('detail', result.__dict__)


if __name__ == '__main__':
  unittest.main()
