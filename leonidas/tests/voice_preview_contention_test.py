import json
from pathlib import Path
import tempfile
import unittest

from leonidas import api
from leonidas import capabilities
from leonidas import config
from leonidas import telemetry


class VoicePreviewContentionTest(unittest.IsolatedAsyncioTestCase):

  async def asyncSetUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    self.store = config.ConfigStore(Path(self.temp_dir.name) / 'config.json')
    self.preview_calls = 0

    class Preview:

      async def preview(inner_self, *_args, **_kwargs):
        del inner_self
        self.preview_calls += 1
        return b'RIFF-preview'

    class Logs:

      def list_files(self):
        return []

      def read(self, *_args, **_kwargs):
        return {'lines': []}

    self.preview = Preview()
    self.logs = Logs()

  async def asyncTearDown(self):
    self.temp_dir.cleanup()

  def _control(self, state):
    class Session:

      def snapshot(self):
        return {'state': state}

    return api.ControlApi(
        config_store=self.store,
        session=Session(),
        metrics=telemetry.MetricsStore(),
        logs=self.logs,
        voice_preview=self.preview,
    )

  async def test_local_preview_is_rejected_while_session_owns_xtts(self):
    control = self._control('running')

    response = await control.dispatch(
        'POST',
        '/api/v1/voices/preview',
        {
            'model_id': capabilities.GROQ_GPT_OSS_20B,
            'voice_name': capabilities.CASCADE_VOICES[0],
        },
    )

    self.assertEqual(response.status, 409)
    self.assertEqual(json.loads(response.body)['error']['code'], 'session_busy')
    self.assertEqual(self.preview_calls, 0)

  async def test_local_preview_is_allowed_when_session_is_stopped(self):
    control = self._control('stopped')

    response = await control.dispatch(
        'POST',
        '/api/v1/voices/preview',
        {
            'model_id': capabilities.GROQ_GPT_OSS_20B,
            'voice_name': capabilities.CASCADE_VOICES[0],
        },
    )

    self.assertEqual(response.status, 200)
    self.assertEqual(response.content_type, 'audio/wav')
    self.assertEqual(self.preview_calls, 1)


if __name__ == '__main__':
  unittest.main()
