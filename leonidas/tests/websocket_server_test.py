import json
import unittest

from genai_processors import content_api

from leonidas import websocket_server


class WebSocketProtocolTest(unittest.TestCase):

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


if __name__ == '__main__':
  unittest.main()
