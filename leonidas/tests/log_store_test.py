import logging
from pathlib import Path
import tempfile
import unittest

from leonidas import log_store


class LogStoreTest(unittest.TestCase):

  def test_redacts_credentials_and_sensitive_content(self):
    redactor = log_store.SensitiveDataRedactor(['secret-value'])
    line = redactor.redact(
        'x-goog-api-key: secret-value prompt=private transcript=hello '
        'data=AAAA'
    )
    self.assertNotIn('secret-value', line)
    self.assertNotIn('private', line)
    self.assertNotIn('hello', line)
    self.assertIn('[REDACTED]', line)

  def test_list_and_read_are_bounded_to_known_log_files(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'leonidas-test.log').write_text('one\ntwo\n', encoding='utf-8')
      (root / 'other.log').write_text('hidden\n', encoding='utf-8')
      store = log_store.LogStore(root)

      self.assertEqual(
          [item['id'] for item in store.list_files()], ['leonidas-test.log']
      )
      page = store.read('leonidas-test.log', cursor=0, limit=1)
      self.assertEqual(page['lines'], ['one'])
      self.assertEqual(page['next_cursor'], 1)

      with self.assertRaises(log_store.InvalidLogIdError):
        store.read('../other.log')

  def test_handler_publishes_already_redacted_lines(self):
    bus = log_store.LogBus()
    subscription = bus.subscribe()
    handler = log_store.BusHandler(
        bus, log_store.SensitiveDataRedactor(['secret-value'])
    )
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    record = logging.LogRecord(
        'test', logging.INFO, __file__, 1, 'token secret-value', (), None
    )

    handler.emit(record)

    self.assertEqual(subscription.get(timeout=0.1), 'INFO token [REDACTED]')
    bus.unsubscribe(subscription)


if __name__ == '__main__':
  unittest.main()
