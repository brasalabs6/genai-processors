import unittest

from leonidas import capabilities


class CapabilitiesTest(unittest.TestCase):

  def test_profiles_preserve_distinct_live_transports(self):
    model_2_5 = capabilities.resolve_model(capabilities.MODEL_LIVE_2_5)
    model_3_1 = capabilities.resolve_model(capabilities.MODEL_LIVE_3_1)

    self.assertEqual(model_2_5.default_input_transport, 'client_content')
    self.assertEqual(model_2_5.realtime_media_transport, 'media')
    self.assertEqual(model_2_5.function_call_mode, 'async_scheduled')
    self.assertEqual(model_3_1.default_input_transport, 'realtime_input')
    self.assertEqual(model_3_1.realtime_media_transport, 'typed')
    self.assertEqual(model_3_1.function_call_mode, 'synchronous')

  def test_public_capabilities_do_not_include_provider_credentials(self):
    public = capabilities.public_capabilities()
    self.assertEqual(public['pipelines'][0]['id'], 'gemini_live')
    self.assertEqual(len(public['voices']), 30)
    self.assertNotIn('api_key', str(public).lower())


if __name__ == '__main__':
  unittest.main()
