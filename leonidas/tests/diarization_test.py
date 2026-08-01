import asyncio
import unittest
from unittest import mock

from leonidas.cascade import diarization
from leonidas.cascade import diarization_worker


class DiarizationTest(unittest.IsolatedAsyncioTestCase):

  def test_availability_exposes_safe_setup_metadata(self):
    with mock.patch.dict(
        'os.environ', {'LEONIDAS_DIARIZATION_PYTHON': '/missing/python'}
    ):
      status = diarization.availability()

    self.assertEqual(status['state'], 'unavailable')
    self.assertIn('install_diarization.sh', status['setup_command'])
    self.assertTrue(status['model_access_required'])

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

  def test_worker_rejects_missing_pipeline_with_actionable_error(self):
    with self.assertRaisesRegex(
        RuntimeError, 'unavailable or access is not authorized'
    ):
      diarization_worker._require_pipeline(None)


if __name__ == '__main__':
  unittest.main()
