import unittest

from leonidas import api
from leonidas import config
from leonidas import telemetry


class _Session:

  def __init__(self):
    self.state = 'stopped'

  def snapshot(self):
    return {'state': self.state}

  async def start(self):
    self.state = 'running'
    return self.snapshot()

  async def stop(self):
    self.state = 'stopped'
    return self.snapshot()

  async def apply_config(self):
    return {'active': {}, 'draft': {}, 'revision': 1, 'dirty_fields': []}


class _Logs:

  def list_files(self):
    return []

  def read(self, *_args, **_kwargs):
    return {'lines': []}


class _Preview:

  async def preview(self, *_args, **_kwargs):
    return b''


class MetricScopeTest(unittest.IsolatedAsyncioTestCase):

  async def asyncSetUp(self):
    self.metrics = telemetry.MetricsStore()
    self.session = _Session()
    self.control = api.ControlApi(
        config_store=unittest.mock.Mock(spec=config.ConfigStore),
        session=self.session,
        metrics=self.metrics,
        logs=_Logs(),
        voice_preview=_Preview(),
    )

  async def test_new_start_resets_previous_session_metrics_once(self):
    self.metrics.observe('ttfa_ms', 500)
    self.metrics.increment('audio_chunks_sent', 3)

    response = await self.control.dispatch('POST', '/api/v1/session/start')

    self.assertEqual(response.status, 200)
    snapshot = self.metrics.snapshot()
    self.assertEqual(snapshot['session_sequence'], 1)
    self.assertEqual(snapshot['metrics'], {})
    self.assertEqual(snapshot['counters'], {})

    self.metrics.increment('audio_chunks_sent')
    await self.control.dispatch('POST', '/api/v1/session/start')
    self.assertEqual(self.metrics.snapshot()['session_sequence'], 1)
    self.assertEqual(
        self.metrics.snapshot()['counters']['audio_chunks_sent'], 1
    )

  async def test_running_apply_starts_a_new_metric_scope(self):
    self.session.state = 'running'
    self.metrics.observe('ttfa_ms', 500)

    response = await self.control.dispatch('POST', '/api/v1/config/apply')

    self.assertEqual(response.status, 200)
    self.assertEqual(self.metrics.snapshot()['session_sequence'], 1)
    self.assertEqual(self.metrics.snapshot()['metrics'], {})


if __name__ == '__main__':
  unittest.main()
