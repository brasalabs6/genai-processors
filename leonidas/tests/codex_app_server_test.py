"""Contract tests for the server-side Codex app-server adapter."""

import asyncio
import os
import unittest
from unittest import mock

from genai_processors import content_api

from leonidas import codex_app_server
from leonidas import capabilities
from leonidas import config
from leonidas.pipelines import codex_realtime


class JsonRpcClientTest(unittest.IsolatedAsyncioTestCase):

  async def test_realtime_voice_discovery_preserves_version_sets(self):
    client, _sent, server = codex_app_server.testing_pair()
    discovery = asyncio.create_task(client.list_voices())
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/listVoices')
    await server.respond(
        request,
        {
            'voices': {
                'v1': ['juniper', 'cove'],
                'v2': ['marin', 'cedar'],
                'defaultV1': 'cove',
                'defaultV2': 'marin',
            }
        },
    )
    voices = await discovery
    self.assertEqual(voices['v1'], ('juniper', 'cove'))
    self.assertEqual(voices['v2'], ('marin', 'cedar'))
    self.assertEqual(voices['default_v1'], 'cove')
    self.assertEqual(voices['default_v2'], 'marin')
    await client.close()

  async def test_realtime_rejects_voice_outside_selected_protocol(self):
    client, _sent, server = codex_app_server.testing_pair()
    discovery = asyncio.create_task(client.list_voices())
    request = await server.next_request()
    await server.respond(
        request,
        {
            'voices': {
                'v1': ['cove'],
                'v2': ['marin'],
                'defaultV1': 'cove',
                'defaultV2': 'marin',
            }
        },
    )
    await discovery

    with self.assertRaisesRegex(
        codex_app_server.CodexProtocolError, 'voice.*v2'
    ):
      await client.start_realtime(
          objective='Ajude o usuário.', voice='cove', version='v2'
      )
    await client.close()

  async def test_realtime_rejects_unknown_protocol_before_creating_thread(self):
    client, _sent, _server = codex_app_server.testing_pair()
    with self.assertRaisesRegex(ValueError, 'version'):
      await client.start_realtime(objective='Ajude o usuário.', version='v4')
    await client.close()

  def test_provider_access_errors_are_redacted_for_public_diagnostics(self):
    error = codex_app_server.CodexProtocolError(
        'unexpected status 403 Forbidden: Voice session access denied., '
        'url: https://chatgpt.com/backend-api/codex/realtime/calls, '
        'cf-ray: secret, request id: secret'
    )
    self.assertIn('access denied', str(error).lower())
    self.assertNotIn('https://', str(error))
    self.assertNotIn('cf-ray', str(error).lower())
    self.assertNotIn('request id', str(error).lower())

  async def test_text_turn_lifecycle_collects_only_matching_turn_deltas(self):
    rpc, _sent, server = codex_app_server.testing_rpc_pair()
    client = codex_app_server.CodexTurnClient(rpc)

    initialize = asyncio.create_task(
        client.initialize(client_name='leonidas', client_version='test')
    )
    request = await server.next_request()
    self.assertEqual(request['method'], 'initialize')
    await server.respond(request, {'userAgent': 'codex-test'})
    await initialize

    start = asyncio.create_task(client.start_thread('Ajude o usuário.'))
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/start')
    await server.respond(request, {'thread': {'id': 'thread-text'}})
    await start

    response = asyncio.create_task(
        client.respond('Qual é o status?', model='gpt-realtime-1.5')
    )
    request = await server.next_request()
    self.assertEqual(request['method'], 'turn/start')
    self.assertEqual(request['params']['threadId'], 'thread-text')
    self.assertEqual(
        request['params']['input'],
        [{'type': 'text', 'text': 'Qual é o status?'}],
    )
    await server.respond(request, {'turn': {'id': 'turn-text'}})
    await server.notify(
        'item/agentMessage/delta',
        {'turnId': 'other-turn', 'delta': 'ignorar'},
    )
    await server.notify(
        'item/agentMessage/delta',
        {'turnId': 'turn-text', 'delta': 'Tudo '},
    )
    await server.notify(
        'item/agentMessage/delta',
        {'turnId': 'turn-text', 'delta': 'certo.'},
    )
    await server.notify('turn/completed', {'turn': {'id': 'turn-text'}})
    self.assertEqual(await response, 'Tudo certo.')

    second_response = asyncio.create_task(client.respond('E agora?'))
    request = await server.next_request()
    self.assertEqual(request['method'], 'turn/start')
    self.assertEqual(request['params']['threadId'], 'thread-text')
    await server.respond(request, {'turn': {'id': 'turn-text-2'}})
    await server.notify(
        'item/agentMessage/delta',
        {'turnId': 'turn-text-2', 'delta': 'Continuo '},
    )
    await server.notify('turn/completed', {'turn': {'id': 'turn-text-2'}})
    self.assertEqual(await second_response, 'Continuo ')
    await client.close()

  async def test_handshake_and_realtime_lifecycle_use_confirmed_methods(self):
    client, sent, server = codex_app_server.testing_pair()

    initialize = asyncio.create_task(
        client.initialize(client_name='leonidas', client_version='test')
    )
    request = await server.next_request()
    self.assertEqual(request['method'], 'initialize')
    self.assertEqual(request['params']['capabilities']['experimentalApi'], True)
    await server.respond(request, {'userAgent': 'codex-test'})
    await initialize

    thread = asyncio.create_task(
        client.start_realtime(
            objective='Ajude o usuário.', model='gpt-realtime-1.5', version='v2'
        )
    )
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/start')
    await server.respond(request, {'thread': {'id': 'thread-1'}})
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/start')
    self.assertEqual(request['params']['threadId'], 'thread-1')
    self.assertEqual(request['params']['outputModality'], 'audio')
    await server.respond(request, {})
    await server.notify(
        'thread/realtime/started',
        {'threadId': 'thread-1', 'version': 'v2'},
    )
    await thread

    append = asyncio.create_task(client.append_text('olá'))
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/appendText')
    self.assertEqual(
        request['params'],
        {'threadId': 'thread-1', 'text': 'olá', 'role': 'user'},
    )
    await server.respond(request, {})
    await append

    stop = asyncio.create_task(client.stop_realtime())
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/stop')
    await server.respond(request, {})
    await stop
    await client.close()
    self.assertTrue(sent)

  async def test_realtime_start_fails_when_transport_closes_before_started(
      self,
  ):
    client, _sent, server = codex_app_server.testing_pair()
    start = asyncio.create_task(
        client.start_realtime(objective='Ajude o usuário.', version='v2')
    )
    request = await server.next_request()
    await server.respond(request, {'thread': {'id': 'thread-closed'}})
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/start')
    await server.respond(request, {})
    await server.notify(
        'thread/realtime/closed',
        {'threadId': 'thread-closed', 'reason': 'upstream disconnected'},
    )

    with self.assertRaisesRegex(
        codex_app_server.CodexProtocolError, 'upstream disconnected'
    ):
      await asyncio.wait_for(start, timeout=1)
    await client.close()

  async def test_server_request_is_rejected_without_deadlocking_pending_call(
      self,
  ):
    client, _sent, server = codex_app_server.testing_pair()
    pending = asyncio.create_task(client.request('thread/start', {}))
    request = await server.next_request()
    await server.request_from_server(
        'item/commandExecution/requestApproval', {'command': 'unsafe'}
    )
    with self.assertRaises(codex_app_server.CodexProtocolError):
      await pending

  async def test_realtime_webrtc_returns_remote_sdp_notification(self):
    client, _sent, server = codex_app_server.testing_pair()
    start = asyncio.create_task(
        client.start_realtime(
            objective='Ajude o usuário.',
            version='v1',
            sdp_offer='v=0\\r\\n',
        )
    )
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/start')
    await server.respond(request, {'thread': {'id': 'thread-webrtc'}})
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/start')
    self.assertEqual(
        request['params']['transport'],
        {'type': 'webrtc', 'sdp': 'v=0\\r\\n'},
    )
    await server.respond(request, {})
    await server.notify(
        'thread/realtime/sdp',
        {'threadId': 'thread-webrtc', 'sdp': 'v=0\\r\\nanswer'},
    )
    await server.notify(
        'thread/realtime/started',
        {'threadId': 'thread-webrtc', 'version': 'v1'},
    )
    self.assertEqual(await start, 'v=0\\r\\nanswer')
    await client.close()

  async def test_realtime_webrtc_accepts_frameless_v3(self):
    client, _sent, server = codex_app_server.testing_pair()
    start = asyncio.create_task(
        client.start_realtime(
            objective='Ajude o usuário.',
            version='v3',
            sdp_offer='v=0\\r\\n',
        )
    )
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/start')
    await server.respond(request, {'thread': {'id': 'thread-webrtc-v3'}})
    request = await server.next_request()
    self.assertEqual(request['method'], 'thread/realtime/start')
    self.assertEqual(request['params']['version'], 'v3')
    self.assertEqual(request['params']['transport']['type'], 'webrtc')
    await server.respond(request, {})
    await server.notify(
        'thread/realtime/sdp',
        {'threadId': 'thread-webrtc-v3', 'sdp': 'v=answer\\r\\n'},
    )
    await server.notify(
        'thread/realtime/started',
        {'threadId': 'thread-webrtc-v3', 'version': 'v3'},
    )
    self.assertEqual(await start, 'v=answer\\r\\n')
    await client.close()


class CodexEventMappingTest(unittest.TestCase):

  def test_v3_composition_uses_runtime_default_frameless_model(self):
    agent_config = config.AgentConfig.from_dict(
        {
            'pipeline_id': capabilities.PIPELINE_CODEX,
            'model_id': capabilities.CODEX_REALTIME_MODEL,
            'voice_name': 'cove',
        }
    )
    with mock.patch.dict(os.environ, {'LEONIDAS_CODEX_REALTIME_VERSION': 'v3'}):
      live = codex_realtime.create(agent_config)
    self.assertEqual(live._version, 'v3')
    self.assertIsNone(live._model)

  def test_notifications_become_processor_parts(self):
    parts = list(
        codex_app_server.notification_parts(
            {
                'method': 'thread/realtime/outputAudio/delta',
                'params': {
                    'threadId': 'thread-1',
                    'audio': {
                        'data': 'AQI=',
                        'sampleRate': 24000,
                        'numChannels': 1,
                    },
                },
            }
        )
    )
    self.assertEqual(len(parts), 1)
    self.assertEqual(parts[0].bytes, b'\x01\x02')
    self.assertEqual(parts[0].substream_name, 'realtime')
    self.assertEqual(parts[0].get_metadata('sample_rate'), 24000)
    self.assertEqual(parts[0].get_metadata('num_channels'), 1)

  def test_webrtc_sideband_does_not_duplicate_remote_audio(self):
    parts = list(
        codex_app_server.notification_parts(
            {
                'method': 'thread/realtime/outputAudio/delta',
                'params': {
                    'audio': {
                        'data': 'AQI=',
                        'sampleRate': 24000,
                        'numChannels': 1,
                    }
                },
            },
            include_audio=False,
        )
    )
    self.assertEqual(parts, [])

  def test_unknown_notifications_are_not_silently_treated_as_audio(self):
    parts = list(
        codex_app_server.notification_parts(
            {'method': 'thread/realtime/itemAdded', 'params': {'item': {}}}
        )
    )
    self.assertEqual(parts, [])


class CodexProcessorWebRtcTest(unittest.IsolatedAsyncioTestCase):

  async def test_runtime_error_notification_terminates_active_processor(self):
    class FakeRpc:

      async def next_notification(self):
        return {
            'method': 'thread/realtime/error',
            'params': {'threadId': 'thread-1', 'message': 'upstream failed'},
        }

    class FakeClient:

      def __init__(self):
        self._rpc = FakeRpc()
        self.stopped = False

      async def start_realtime(self, **kwargs):
        del kwargs
        return None

      async def append_text(self, value):
        del value

      async def append_audio(self, data, *, sample_rate, num_channels):
        del data, sample_rate, num_channels

      async def stop_realtime(self):
        self.stopped = True

      def terminal_notification_error(self, notification):
        params = notification.get('params') or {}
        if notification.get('method') == 'thread/realtime/error':
          return codex_app_server.CodexProtocolError(
              str(params.get('message', 'realtime error'))
          )
        return None

    client = FakeClient()
    live = codex_app_server.CodexRealtimeProcessor(
        client, objective='Ajude o usuário.', version='v2'
    )

    async def content():
      yield content_api.ProcessorPart('olá')
      await asyncio.Future()

    with self.assertRaisesRegex(
        codex_app_server.CodexProtocolError, 'upstream failed'
    ):
      await asyncio.wait_for(
          anext(aiter(live(content()))),
          timeout=1,
      )
    self.assertTrue(client.stopped)

  async def test_offer_is_consumed_and_answer_is_emitted_without_pcm_forwarding(
      self,
  ):
    class FakeRpc:

      async def next_notification(self):
        await asyncio.Future()

    class FakeClient:

      def __init__(self):
        self._rpc = FakeRpc()
        self.offer = None
        self.text = []
        self.stopped = False

      async def start_realtime(self, **kwargs):
        self.offer = kwargs.get('sdp_offer')
        return 'v=0\\r\\nanswer'

      async def append_text(self, value):
        self.text.append(value)

      async def append_audio(self, **kwargs):
        raise AssertionError('WebRTC input must not be forwarded as PCM')

      async def stop_realtime(self):
        self.stopped = True

    client = FakeClient()
    live = codex_app_server.CodexRealtimeProcessor(
        client,
        objective='Ajude o usuário.',
        version='v1',
    )

    async def content():
      yield content_api.ProcessorPart(
          'v=0\\r\\noffer',
          mimetype=codex_app_server.CODEX_WEBRTC_OFFER_MIMETYPE,
      )
      yield content_api.ProcessorPart('olá')

    outputs = [part async for part in live(content())]
    self.assertEqual(client.offer, 'v=0\\r\\noffer')
    self.assertEqual(client.text, ['olá'])
    self.assertTrue(client.stopped)
    self.assertEqual(len(outputs), 1)
    self.assertEqual(
        outputs[0].mimetype, codex_app_server.CODEX_WEBRTC_ANSWER_MIMETYPE
    )
    self.assertEqual(outputs[0].part.text, 'v=0\\r\\nanswer')


if __name__ == '__main__':
  unittest.main()
