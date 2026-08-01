import json
import unittest

from genai_processors import content_api

from leonidas import telemetry
from leonidas import websocket_server


class WebSocketProtocolTest(unittest.TestCase):

  def test_decodes_bounded_codex_webrtc_offer_control_part(self):
    part = websocket_server._decode(
        json.dumps(
            {
                'mimetype': websocket_server.CODEX_WEBRTC_OFFER_MIMETYPE,
                'part': {'text': 'v=0\r\n'},
            }
        )
    )
    self.assertEqual(
        part.mimetype, websocket_server.CODEX_WEBRTC_OFFER_MIMETYPE
    )
    self.assertEqual(part.part.text, 'v=0\r\n')
    self.assertEqual(part.substream_name, 'realtime')

  def test_rejects_oversized_codex_webrtc_offer(self):
    oversized = 'x' * (websocket_server.CODEX_WEBRTC_SDP_MAX_BYTES + 1)
    with self.assertRaisesRegex(ValueError, 'SDP payload is too large'):
      websocket_server._decode(
          json.dumps(
              {
                  'mimetype': websocket_server.CODEX_WEBRTC_OFFER_MIMETYPE,
                  'part': {'text': oversized},
              }
          )
      )

  def test_text_becomes_complete_user_turn(self):
    message = json.dumps(
        content_api.ProcessorPart('olá').to_dict(mode='python')
    )
    part = websocket_server._decode(message)
    self.assertEqual(part.role, 'user')
    self.assertTrue(part.metadata['turn_complete'])

  def test_audio_is_normalized_to_realtime_substream(self):
    message = json.dumps(
        content_api.ProcessorPart(
            b'\x00\x01', mimetype='audio/pcm;rate=16000'
        ).to_dict(mode='json')
    )
    part = websocket_server._decode(message)
    self.assertEqual(part.role, 'user')
    self.assertEqual(part.substream_name, 'realtime')
    self.assertTrue(content_api.is_audio(part.mimetype))

  def test_state_envelope_has_sequence_and_timestamp(self):
    part = websocket_server._state_part(
        {'state': 'running', 'session_id': 'session'}, 4
    )
    self.assertEqual(part.mimetype, 'application/x-state')
    self.assertEqual(part.metadata['sequence'], 4)
    self.assertEqual(part.metadata['session_id'], 'session')
    self.assertIn('timestamp', part.metadata)

  def test_resource_envelope_preserves_component_status(self):
    part = websocket_server._resource_part(
        {
            'schema_version': 1,
            'overall_state': 'loading',
            'components': [{'id': 'stt', 'state': 'warming'}],
        },
        7,
    )

    self.assertEqual(part.mimetype, 'application/x-resource-state')
    self.assertEqual(part.metadata['sequence'], 7)
    self.assertEqual(part.metadata['components'][0]['state'], 'warming')

  def test_local_origins_follow_configured_web_port(self):
    origins = websocket_server.local_origins(18000)
    self.assertIn('http://127.0.0.1:18000', origins)
    self.assertIn('http://localhost:18000', origins)
    self.assertIn('http://127.0.0.1:5173', origins)

  def test_client_metrics_are_allowlisted_and_range_checked(self):
    metrics = telemetry.MetricsStore()
    accepted = content_api.ProcessorPart(
        '',
        mimetype='application/x-client-metric',
        metadata={'name': 'playback_flush_ms', 'value': 2.5},
    )
    injected = content_api.ProcessorPart(
        '',
        mimetype='application/x-client-metric',
        metadata={'name': 'attacker_series', 'value': 1},
    )
    invalid = content_api.ProcessorPart(
        '',
        mimetype='application/x-client-metric',
        metadata={'name': 'playback_flush_ms', 'value': float('inf')},
    )

    self.assertTrue(websocket_server._record_client_metric(accepted, metrics))
    self.assertFalse(websocket_server._record_client_metric(injected, metrics))
    self.assertFalse(websocket_server._record_client_metric(invalid, metrics))

    snapshot = metrics.snapshot()
    self.assertEqual(snapshot['metrics']['playback_flush_ms']['current'], 2.5)
    self.assertEqual(snapshot['counters']['client_metrics_rejected'], 2)
    self.assertNotIn('attacker_series', snapshot['metrics'])


if __name__ == '__main__':
  unittest.main()
