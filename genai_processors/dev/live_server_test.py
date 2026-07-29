import json
import unittest
from unittest import mock

from genai_processors.dev import live_server
from websockets.exceptions import ConnectionClosedOK


class LiveServerTest(unittest.IsolatedAsyncioTestCase):

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
