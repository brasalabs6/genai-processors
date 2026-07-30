import json
from pathlib import Path
import tempfile
import unittest

from leonidas.e2e import report
from leonidas.e2e import runner


class ReportTest(unittest.TestCase):

  def test_report_contains_evidence_without_transcript_or_credentials(self):
    result = runner.EmpiricalResult(
        model_id='model',
        scenario_id='scenario',
        passed=True,
        audio_seconds=1.0,
        ttfa_ms=120,
        transcription_received=True,
        semantic_matches=('mesa',),
        output_parts=4,
        error_code=None,
        elapsed_seconds=2.0,
    )
    with tempfile.TemporaryDirectory() as temp_dir:
      json_path, markdown_path = report.write(
          Path(temp_dir), [result], run_id='test-run'
      )
      payload = json.loads(json_path.read_text(encoding='utf-8'))
      markdown = markdown_path.read_text(encoding='utf-8')
      self.assertTrue(payload['passed'])
      self.assertNotIn('transcript', markdown.casefold())
      self.assertNotIn(
          'api_key', json_path.read_text(encoding='utf-8').casefold()
      )


if __name__ == '__main__':
  unittest.main()
