import os
from pathlib import Path
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
        mock.patch.multiple(
            commentator_web,
            _DEBUG=mock.Mock(value=False),
            _HOST=mock.Mock(value='127.0.0.1'),
            _WEB_PORT=mock.Mock(value=8000),
            _WEBSOCKET_PORT=mock.Mock(value=8765),
            _WEB_ROOT=mock.Mock(value=None),
            _TRACE_DIR=mock.Mock(value=None),
        ),
    ):
      commentator_web.main(['commentator_web.py'])


if __name__ == '__main__':
  unittest.main()
