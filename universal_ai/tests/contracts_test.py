"""Provider-neutral capability and queue policy contract tests."""

import unittest

from universal_ai import contracts


class ContractsTest(unittest.TestCase):

  def setUp(self):
    self.capability = contracts.ProviderCapabilities(
        provider_id='mock',
        input_modalities=frozenset({'audio', 'text', 'image'}),
        output_modalities=frozenset({'audio', 'text'}),
        barge_in=True,
        native_audio=True,
    )

  def test_valid_audio_conversation(self):
    contracts.ConversationNeeds(
        input_modalities=frozenset({'audio', 'image'}),
        output_modalities=frozenset({'audio'}),
        require_barge_in=True,
    ).validate(self.capability)

  def test_unsupported_vision_is_explicit(self):
    without_vision = contracts.ProviderCapabilities(
        provider_id='text-only',
        input_modalities=frozenset({'text'}),
        output_modalities=frozenset({'text'}),
    )
    with self.assertRaisesRegex(contracts.CapabilityError, 'image'):
      contracts.ConversationNeeds(
          input_modalities=frozenset({'text', 'image'})
      ).validate(without_vision)

  def test_unsupported_interruption_is_explicit(self):
    with self.assertRaisesRegex(contracts.CapabilityError, 'barge-in'):
      contracts.ConversationNeeds(require_barge_in=True).validate(
          contracts.ProviderCapabilities(
              provider_id='mock',
              input_modalities=frozenset({'text'}),
              output_modalities=frozenset({'text'}),
          )
      )

  def test_audio_never_drops(self):
    with self.assertRaisesRegex(ValueError, 'must not drop'):
      contracts.SourceSettings('mic', 'audio', overflow='drop_oldest')

  def test_invalid_video_budget(self):
    with self.assertRaises(ValueError):
      contracts.ConversationNeeds(video_max_fps=0)


if __name__ == '__main__':
  unittest.main()
