import unittest

import numpy as np

from leonidas.cascade import vad


class RealisticVadFixtureTest(unittest.TestCase):

  @staticmethod
  def _voiced_frame(index: int, amplitude: float = 0.08) -> bytes:
    """Builds a speech-like frame with harmonics and deterministic room noise."""
    time = (np.arange(480, dtype=np.float64) + index * 480) / 16000
    fundamental = np.sin(2 * np.pi * 145 * time)
    harmonic = 0.45 * np.sin(2 * np.pi * 290 * time + 0.2)
    rng = np.random.default_rng(1000 + index)
    room_noise = rng.normal(0, 0.002, 480)
    samples = np.clip(
        amplitude * (fundamental + harmonic) + room_noise, -1.0, 1.0
    )
    return (samples * 32767).astype('<i2').tobytes()

  @staticmethod
  def _room_frame(index: int, amplitude: float = 0.002) -> bytes:
    rng = np.random.default_rng(index)
    samples = rng.normal(0, amplitude, 480)
    return (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()

  @staticmethod
  def _fan_frame(index: int, amplitude: float = 0.008) -> bytes:
    time = (np.arange(480, dtype=np.float64) + index * 480) / 16000
    hum = amplitude * np.sin(2 * np.pi * 60 * time)
    return (hum * 32767).astype('<i2').tobytes()

  def test_immediate_short_command_survives_initial_calibration(self):
    gate = vad.AdaptiveSpeechGate(
        is_speech=lambda frame: np.max(
            np.abs(np.frombuffer(frame, dtype='<i2'))
        )
        > 500
    )
    detector = vad.EndpointDetector(speech_gate=gate)

    events = []
    for index in range(4):
      events.extend(detector.push(self._voiced_frame(index)))
    for index in range(15):
      events.extend(detector.push(self._room_frame(index)))

    kinds = [event.kind for event in events]
    self.assertEqual(kinds.count('start'), 1)
    self.assertEqual(kinds.count('utterance'), 1)
    utterance = next(event for event in events if event.kind == 'utterance')
    self.assertGreaterEqual(len(utterance.audio), 4 * vad.FRAME_BYTES)

  def test_calibration_records_each_noise_frame_only_once(self):
    gate = vad.AdaptiveSpeechGate(is_speech=lambda _frame: False)

    for index in range(5):
      decision = gate.classify(self._room_frame(index))
      self.assertTrue(decision.calibrating)

    self.assertEqual(len(gate._levels), 5)

  def test_low_energy_harmonic_noise_does_not_start_a_turn(self):
    # Raw WebRTC decisions can occasionally label fans or mains hum as voice.
    gate = vad.AdaptiveSpeechGate(is_speech=lambda _frame: True)
    detector = vad.EndpointDetector(speech_gate=gate)

    events = []
    for index in range(40):
      events.extend(detector.push(self._fan_frame(index)))

    kinds = [event.kind for event in events]
    self.assertNotIn('start', kinds)
    self.assertNotIn('utterance', kinds)


if __name__ == '__main__':
  unittest.main()
