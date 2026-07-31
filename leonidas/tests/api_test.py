import json
from pathlib import Path
import tempfile
import unittest

from leonidas import api
from leonidas import config
from leonidas import log_store
from leonidas import runtime
from leonidas import telemetry


class FakeSession:

  def __init__(self):
    self.state = 'stopped'

  def snapshot(self):
    return {'state': self.state, 'media_connected': False}

  async def start(self):
    raise runtime.MediaNotConnectedError('Connect media')

  async def stop(self):
    self.state = 'stopped'
    return self.snapshot()

  async def apply_config(self):
    return {'applied': True}


class FakePreview:

  async def preview(self, model_id, voice_name, text, *, device='auto'):
    del model_id, voice_name, text, device
    return b'RIFFfake-wave'


class ControlApiTest(unittest.IsolatedAsyncioTestCase):

  async def asyncSetUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    root = Path(self.temp_dir.name)
    self.store = config.ConfigStore(root / 'config.json')
    self.metrics = telemetry.MetricsStore()
    self.log_store = log_store.LogStore(root / 'logs')
    self.control = api.ControlApi(
        config_store=self.store,
        session=FakeSession(),
        metrics=self.metrics,
        logs=self.log_store,
        voice_preview=FakePreview(),
        resources=lambda: {
            'schema_version': 1,
            'overall_state': 'unloaded',
            'components': [],
        },
    )

  async def asyncTearDown(self):
    self.temp_dir.cleanup()

  async def test_capabilities_are_browser_safe(self):
    response = await self.control.dispatch('GET', '/api/v1/capabilities')
    payload = json.loads(response.body)
    self.assertEqual(response.status, 200)
    self.assertEqual(payload['data']['schema_version'], 1)
    self.assertNotIn('api_key', response.body.lower())

  async def test_draft_update_requires_revision(self):
    response = await self.control.dispatch(
        'PUT',
        '/api/v1/config/draft',
        {'expected_revision': 0, 'updates': {'chattiness': 0.25}},
    )
    self.assertEqual(response.status, 200)
    self.assertEqual(json.loads(response.body)['data']['revision'], 1)

    conflict = await self.control.dispatch(
        'PUT',
        '/api/v1/config/draft',
        {'expected_revision': 0, 'updates': {'chattiness': 0.75}},
    )
    self.assertEqual(conflict.status, 409)
    self.assertEqual(
        json.loads(conflict.body)['error']['code'], 'revision_conflict'
    )

  async def test_start_without_media_returns_conflict(self):
    response = await self.control.dispatch('POST', '/api/v1/session/start', {})
    self.assertEqual(response.status, 409)
    self.assertEqual(
        json.loads(response.body)['error']['code'], 'media_not_connected'
    )

  async def test_starting_session_returns_accepted(self):
    self.control._session.start = unittest.mock.AsyncMock(
        return_value={'state': 'starting'}
    )

    response = await self.control.dispatch('POST', '/api/v1/session/start', {})

    self.assertEqual(response.status, 202)

  async def test_resources_returns_local_model_readiness(self):
    response = await self.control.dispatch('GET', '/api/v1/resources')
    payload = json.loads(response.body)

    self.assertEqual(response.status, 200)
    self.assertEqual(payload['data']['overall_state'], 'unloaded')

  async def test_voice_preview_returns_wav_not_json(self):
    response = await self.control.dispatch(
        'POST',
        '/api/v1/voices/preview',
        {
            'model_id': config.AgentConfig.default().model_id,
            'voice_name': 'Kore',
        },
    )
    self.assertEqual(response.status, 200)
    self.assertEqual(response.content_type, 'audio/wav')
    self.assertTrue(response.body.startswith(b'RIFF'))

  async def test_cascade_voice_preview_uses_its_own_allowlist(self):
    response = await self.control.dispatch(
        'POST',
        '/api/v1/voices/preview',
        {
            'model_id': 'openai/gpt-oss-20b',
            'voice_name': 'leonidas',
        },
    )
    self.assertEqual(response.status, 200)
    self.assertEqual(response.content_type, 'audio/wav')

  async def test_unknown_route_is_structured(self):
    response = await self.control.dispatch('GET', '/api/v1/nope')
    self.assertEqual(response.status, 404)
    self.assertEqual(json.loads(response.body)['error']['code'], 'not_found')


if __name__ == '__main__':
  unittest.main()
