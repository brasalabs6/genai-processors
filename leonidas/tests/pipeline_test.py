import unittest

from leonidas import capabilities
from leonidas import config
from leonidas import prompts


class PromptTest(unittest.TestCase):

  def test_objective_is_appended_without_replacing_protected_instructions(self):
    parts = prompts.system_instruction(
        'Ajude a revisar código.', synchronous=True
    )

    self.assertIn('wait_for_user', ' '.join(parts))
    self.assertEqual(
        parts[-1], 'Objetivo e persona configurados: Ajude a revisar código.'
    )

  def test_objective_cannot_inject_empty_instruction(self):
    with self.assertRaisesRegex(ValueError, 'objective'):
      prompts.system_instruction('   ', synchronous=False)


class GeminiLiveConfigurationTest(unittest.TestCase):

  def test_voice_and_vad_are_translated_to_live_connect_config(self):
    from leonidas.pipelines import gemini_live

    agent_config = config.AgentConfig.default().with_updates(
        {
            'voice_name': 'Kore',
            'vad': {
                'start_sensitivity': 'high',
                'end_sensitivity': 'low',
                'prefix_padding_ms': 120,
                'silence_duration_ms': 450,
            },
        }
    )
    profile = gemini_live.resolve_live_model_profile(agent_config.model_id)

    live_config = gemini_live.create_live_connect_config(agent_config, profile)

    self.assertEqual(
        live_config.speech_config.voice_config.prebuilt_voice_config.voice_name,
        'Kore',
    )
    vad = live_config.realtime_input_config.automatic_activity_detection
    self.assertEqual(vad.prefix_padding_ms, 120)
    self.assertEqual(vad.silence_duration_ms, 450)
    self.assertEqual(vad.start_of_speech_sensitivity, 'START_SENSITIVITY_HIGH')
    self.assertEqual(vad.end_of_speech_sensitivity, 'END_SENSITIVITY_LOW')

  def test_model_specific_thinking_is_translated(self):
    from leonidas.pipelines import gemini_live

    value = config.AgentConfig.default().with_preset('quality')
    live_config = gemini_live.create_live_connect_config(
        value, gemini_live.resolve_live_model_profile(value.model_id)
    )
    self.assertEqual(live_config.thinking_config.thinking_budget, 512)

    value = value.with_updates({'model_id': capabilities.MODEL_LIVE_3_1})
    value = value.with_preset('quality')
    live_config = gemini_live.create_live_connect_config(
        value, gemini_live.resolve_live_model_profile(value.model_id)
    )
    self.assertEqual(live_config.thinking_config.thinking_level, 'MEDIUM')


if __name__ == '__main__':
  unittest.main()
