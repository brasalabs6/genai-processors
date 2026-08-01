import asyncio
import unittest

from leonidas.cascade import diarization


class DiarizationTest(unittest.IsolatedAsyncioTestCase):

  async def test_null_diarizer_does_not_block_cascade(self):
    result = await diarization.NullDiarizer().diarize(
        b'\x00' * 3200, sample_rate=16000
    )
    self.assertEqual(result, [])

  def test_segment_contract_is_json_safe(self):
    segment = diarization.SpeakerSegment('SPEAKER_00', 0.1, 0.8, 0.92)
    self.assertEqual(
        segment.to_dict(),
        {
            'speaker_id': 'SPEAKER_00',
            'start': 0.1,
            'end': 0.8,
            'confidence': 0.92,
        },
    )


if __name__ == '__main__':
  unittest.main()
