import json
from pathlib import Path
import tempfile
import unittest

from leonidas import codex_auth


class CodexAuthTest(unittest.TestCase):

  def test_validates_shape_without_returning_secret_values(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'auth.json'
      path.write_text(
          json.dumps({'OPENAI_API_KEY': 'do-not-leak'}),
          encoding='utf-8',
      )
      self.assertEqual(codex_auth.validate_auth_file(path), path.resolve())
      environment = codex_auth.subprocess_environment(path)
      self.assertEqual(environment['CODEX_HOME'], str(path.parent.resolve()))
      self.assertEqual(environment['OPENAI_API_KEY'], 'do-not-leak')

  def test_missing_auth_is_actionable(self):
    with self.assertRaisesRegex(codex_auth.CodexAuthError, 'missing'):
      codex_auth.validate_auth_file(Path('/tmp/does-not-exist-leonidas-auth'))


if __name__ == '__main__':
  unittest.main()
