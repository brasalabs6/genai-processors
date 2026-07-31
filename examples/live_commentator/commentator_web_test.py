import os
from pathlib import Path
import logging as std_logging
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.request

from examples.live_commentator import commentator_web


class CommentatorWebTest(unittest.TestCase):

  def test_live_commentator_uses_compatible_live_model(self):
    self.assertEqual(
        commentator_web.commentator.MODEL_LIVE,
        'gemini-2.5-flash-native-audio-preview-12-2025',
    )

  @mock.patch.dict(os.environ, {'GOOGLE_API_KEY': 'test-key'})
  @mock.patch.object(commentator_web.commentator, 'create_live_commentator')
  def test_pipeline_factory_forwards_selected_live_model(self, create_pipeline):
    commentator_web.create_live_commentator(
        {
            'chattiness': 0.25,
            'live_model': commentator_web.commentator.MODEL_LIVE_3_1,
        }
    )

    create_pipeline.assert_called_once_with(
        api_key='test-key',
        chattiness=0.25,
        unsafe_string_list=None,
        live_model_name=commentator_web.commentator.MODEL_LIVE_3_1,
    )

  def test_pipeline_factory_rejects_unknown_live_model(self):
    with self.assertRaisesRegex(ValueError, 'Unsupported live model'):
      commentator_web.create_live_commentator(
          {'live_model': 'gemini-unknown-live'}
      )

  def test_tentative_trigger_time_falls_back_when_generation_has_no_audio(self):
    state_machine = commentator_web.commentator.CommentatorStateMachine(
        state=commentator_web.commentator.State.WAITING_FOR_USER,
        generation_request_info=(
            commentator_web.commentator.GenerationRequestInfo(
                generation_start_sec=time.perf_counter(),
                generation_type=commentator_web.commentator.GenerationType.COMMENT,
            )
        ),
    )

    before = time.perf_counter()
    trigger_time = state_machine.tentative_trigger_time()
    after = time.perf_counter()

    self.assertIsNotNone(trigger_time)
    self.assertGreaterEqual(trigger_time, before)
    self.assertLessEqual(trigger_time, after)

  def test_validate_runtime_requires_api_key(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      web_root = Path(temp_dir)
      (web_root / 'index.html').write_text('ok', encoding='utf-8')

      with self.assertRaisesRegex(ValueError, 'GOOGLE_API_KEY'):
        commentator_web.validate_runtime(web_root, environ={})

  def test_validate_runtime_requires_vite_build(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      web_root = Path(temp_dir)

      with self.assertRaisesRegex(FileNotFoundError, 'npm run build'):
        commentator_web.validate_runtime(
            web_root, environ={'GOOGLE_API_KEY': 'test-key'}
        )

  def test_static_server_serves_web_root(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      web_root = Path(temp_dir)
      (web_root / 'index.html').write_text(
          '<h1>Standalone commentator</h1>', encoding='utf-8'
      )
      server = commentator_web.create_static_server(
          web_root=web_root,
          host='127.0.0.1',
          port=0,
      )
      server_thread = threading.Thread(target=server.serve_forever)
      server_thread.start()
      try:
        host, port = server.server_address
        with urllib.request.urlopen(
            f'http://{host}:{port}/', timeout=2
        ) as response:
          self.assertEqual(response.status, 200)
          self.assertIn(
              b'Standalone commentator',
              response.read(),
          )
      finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

  def test_default_web_root_points_to_vite_dist(self):
    expected = (
        Path(commentator_web.__file__).parent / 'webui' / 'dist'
    ).resolve()
    self.assertEqual(commentator_web.default_web_root(), expected)

  def test_default_log_dir_points_to_repository_logs(self):
    expected = Path(commentator_web.__file__).parents[2] / 'logs'
    self.assertEqual(commentator_web.default_log_dir(), expected)

  def test_install_file_logging_captures_absl_errors(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path, handler = commentator_web.install_file_logging(
          Path(temp_dir),
          debug=True,
      )
      try:
        commentator_web.logging.error('diagnostic-marker')
        handler.flush()
      finally:
        std_logging.getLogger().removeHandler(handler)
        handler.close()

      contents = log_path.read_text(encoding='utf-8')
      self.assertIn('ERROR', contents)
      self.assertIn('diagnostic-marker', contents)
      self.assertNotIn('GOOGLE_API_KEY', contents)

  def test_install_file_logging_redacts_secrets_and_protocol_payloads(self):
    secret = 'test-google-api-key-value'
    with (
        tempfile.TemporaryDirectory() as temp_dir,
        mock.patch.dict(os.environ, {'GOOGLE_API_KEY': secret}),
    ):
      log_path, handler = commentator_web.install_file_logging(
          Path(temp_dir),
          debug=True,
      )
      websocket_logger = std_logging.getLogger('websockets.client')
      previous_level = websocket_logger.level
      websocket_logger.setLevel(std_logging.DEBUG)
      try:
        commentator_web.logging.error('x-goog-api-key: %s', secret)
        websocket_logger.debug('raw-frame-payload-marker')
        handler.handle(
            std_logging.LogRecord(
                name='absl',
                level=std_logging.DEBUG,
                pathname='/tmp/commentator.py',
                lineno=1,
                msg='non media part: private-content-marker',
                args=(),
                exc_info=None,
            )
        )
        handler.flush()
      finally:
        websocket_logger.setLevel(previous_level)
        std_logging.getLogger().removeHandler(handler)
        handler.close()

      contents = log_path.read_text(encoding='utf-8')
      self.assertNotIn(secret, contents)
      self.assertIn('[REDACTED]', contents)
      self.assertNotIn('raw-frame-payload-marker', contents)
      self.assertNotIn('private-content-marker', contents)

  def test_main_handles_keyboard_interrupt(self):
    def interrupt_and_close(coroutine):
      coroutine.close()
      raise KeyboardInterrupt

    with (
        mock.patch.object(
            commentator_web.asyncio,
            'run',
            side_effect=interrupt_and_close,
        ),
        mock.patch.object(
            commentator_web,
            'install_file_logging',
            return_value=(Path('/tmp/test.log'), mock.Mock()),
        ),
        mock.patch.multiple(
            commentator_web,
            _DEBUG=mock.Mock(value=False),
            _HOST=mock.Mock(value='127.0.0.1'),
            _WEB_PORT=mock.Mock(value=8000),
            _WEBSOCKET_PORT=mock.Mock(value=8765),
            _WEB_ROOT=mock.Mock(value=None),
            _TRACE_DIR=mock.Mock(value=None),
            _LOG_DIR=mock.Mock(value=None),
        ),
    ):
      commentator_web.main(['commentator_web.py'])

  def test_main_logs_unhandled_exception_with_traceback(self):
    def fail_and_close(coroutine):
      coroutine.close()
      raise RuntimeError('pipeline-failure-marker')

    with tempfile.TemporaryDirectory() as temp_dir:
      with (
          mock.patch.object(
              commentator_web.asyncio,
              'run',
              side_effect=fail_and_close,
          ),
          mock.patch.multiple(
              commentator_web,
              _DEBUG=mock.Mock(value=False),
              _HOST=mock.Mock(value='127.0.0.1'),
              _WEB_PORT=mock.Mock(value=8000),
              _WEBSOCKET_PORT=mock.Mock(value=8765),
              _WEB_ROOT=mock.Mock(value=None),
              _TRACE_DIR=mock.Mock(value=None),
              _LOG_DIR=mock.Mock(value=temp_dir),
          ),
      ):
        with self.assertRaisesRegex(
            RuntimeError,
            'pipeline-failure-marker',
        ):
          commentator_web.main(['commentator_web.py'])

      log_paths = list(Path(temp_dir).glob('live-commentator-*.log'))
      self.assertEqual(len(log_paths), 1)
      contents = log_paths[0].read_text(encoding='utf-8')
      self.assertIn(
          'Live Commentator terminated with an unhandled error', contents
      )
      self.assertIn('RuntimeError: pipeline-failure-marker', contents)


if __name__ == '__main__':
  unittest.main()
