import json
import base64
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
      isolated = codex_auth.subprocess_environment(
          path, codex_home=Path(temp_dir) / 'isolated'
      )
      self.assertEqual(
          isolated['CODEX_HOME'], str((Path(temp_dir) / 'isolated').resolve())
      )

  def test_missing_auth_is_actionable(self):
    with self.assertRaisesRegex(codex_auth.CodexAuthError, 'missing'):
      codex_auth.validate_auth_file(Path('/tmp/does-not-exist-leonidas-auth'))

  def test_chatgpt_login_can_build_text_environment_without_api_key(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'auth.json'
      path.write_text(
          json.dumps({'auth_mode': 'chatgpt', 'tokens': {'access_token': 'x'}}),
          encoding='utf-8',
      )
      environment = codex_auth.subprocess_environment(
          path, require_api_key=False
      )
      self.assertNotIn('OPENAI_API_KEY', environment)

  def test_realtime_rejects_empty_api_key(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'auth.json'
      path.write_text(
          json.dumps({'auth_mode': 'apikey', 'OPENAI_API_KEY': '  '}),
          encoding='utf-8',
      )
      with self.assertRaisesRegex(
          codex_auth.CodexAuthError, 'requires an OPENAI_API_KEY'
      ):
        codex_auth.validate_auth_file(path, require_api_key=True)

  def test_expired_jwt_tokens_are_rejected_without_logging_claims(self):
    def jwt(payload):
      encoded = (
          base64.urlsafe_b64encode(json.dumps(payload).encode('utf-8'))
          .rstrip(b'=')
          .decode('ascii')
      )
      return f'header.{encoded}.signature'

    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'auth.json'
      path.write_text(
          json.dumps(
              {
                  'auth_mode': 'chatgpt',
                  'tokens': {
                      'access_token': jwt({'exp': 1}),
                      'id_token': jwt({'exp': 1}),
                      'refresh_token': 'opaque-refresh-token',
                  },
              }
          ),
          encoding='utf-8',
      )
      with self.assertRaisesRegex(codex_auth.CodexAuthError, 'expired'):
        codex_auth.validate_auth_file(path)


if __name__ == '__main__':
  unittest.main()
