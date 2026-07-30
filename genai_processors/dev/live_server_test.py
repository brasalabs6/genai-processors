import json
import unittest
from unittest import mock

from genai_processors import processor
from genai_processors.dev import live_server
from websockets.exceptions import ConnectionClosedOK


class _DrainProcessor(processor.Processor):

  async def call(self, content):
    async for part in content:
      yield part


class LiveServerTest(unittest.IsolatedAsyncioTestCase):

  async def test_config_reset_reports_health_check_as_state_message(self):
    websocket = mock.AsyncMock()
    websocket.__aiter__.return_value = iter(
        [
            json.dumps(
                {
                    'mimetype': 'application/x-config',
                    'metadata': {'chattiness': 0.5},
                }
            )
        ]
    )
    processor_factory = mock.Mock(
        side_effect=[
            _DrainProcessor(),
            ConnectionClosedOK(None, None),
        ]
    )

    await live_server.live_server(
        processor_factory,
        trace_dir=None,
        max_size_bytes=None,
        ais_websocket=websocket,
    )

    health_check = json.loads(websocket.send.call_args_list[0].args[0])
    self.assertEqual(health_check['mimetype'], 'application/x-state')
    self.assertTrue(health_check['metadata']['health_check'])

  async def test_pipeline_error_is_reported_without_exposing_exception(self):
    websocket = mock.AsyncMock()
    websocket.send.side_effect = [
        None,
        ConnectionClosedOK(None, None),
    ]

    def fail_factory(_):
      raise RuntimeError('private-provider-error')

    await live_server.live_server(
        fail_factory,
        trace_dir=None,
        max_size_bytes=None,
        ais_websocket=websocket,
    )

    error_message = json.loads(websocket.send.call_args_list[0].args[0])
    self.assertEqual(error_message['mimetype'], 'application/x-state')
    self.assertEqual(
        error_message['metadata']['error'],
        'pipeline_configuration_failed',
    )
    self.assertNotIn(
        'private-provider-error', websocket.send.call_args_list[0].args[0]
    )


if __name__ == '__main__':
  unittest.main()
