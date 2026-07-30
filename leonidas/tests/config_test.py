import json
from pathlib import Path
import tempfile
import unittest

from leonidas import capabilities
from leonidas import config


class AgentConfigTest(unittest.TestCase):

  def test_default_preserves_live_commentator_behavior(self):
    value = config.AgentConfig.default()

    self.assertEqual(value.model_id, capabilities.MODEL_LIVE_2_5)
    self.assertEqual(value.performance_preset, 'balanced')
    self.assertEqual(value.media.frame_interval_ms, 1000)
    self.assertEqual(value.media.model_resolution, 'medium')
    self.assertIsNone(value.voice_name)

  def test_low_latency_preset_uses_model_specific_thinking(self):
    value = config.AgentConfig.default().with_preset('low_latency')
    self.assertEqual(value.media.frame_interval_ms, 500)
    self.assertEqual(value.generation.thinking_budget, 0)

    value = value.with_updates({'model_id': capabilities.MODEL_LIVE_3_1})
    value = value.with_preset('low_latency')
    self.assertEqual(value.generation.thinking_level, 'minimal')
    self.assertIsNone(value.generation.thinking_budget)

  def test_rejects_model_specific_thinking_field(self):
    value = config.AgentConfig.default().to_dict()
    value['generation']['thinking_level'] = 'minimal'

    with self.assertRaisesRegex(config.ConfigValidationError, 'thinking_level'):
      config.AgentConfig.from_dict(value)

  def test_unknown_voice_is_rejected(self):
    value = config.AgentConfig.default().to_dict()
    value['voice_name'] = 'NotAVoice'

    with self.assertRaisesRegex(config.ConfigValidationError, 'voice_name'):
      config.AgentConfig.from_dict(value)


class ConfigStoreTest(unittest.TestCase):

  def test_updates_draft_with_optimistic_revision_and_persists(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / 'config.json'
      store = config.ConfigStore(path)

      snapshot = store.update_draft(
          {'objective': 'Ajude com programação.'}, expected_revision=0
      )
      self.assertEqual(snapshot.revision, 1)
      self.assertEqual(snapshot.dirty_fields, ('objective',))

      reloaded = config.ConfigStore(path).snapshot()
      self.assertEqual(reloaded.draft.objective, 'Ajude com programação.')
      self.assertEqual(reloaded.active, config.AgentConfig.default())
      self.assertNotIn('GOOGLE_API_KEY', json.dumps(reloaded.to_dict()))

  def test_revision_conflict_does_not_change_store(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      store.update_draft({'chattiness': 0.25}, expected_revision=0)

      with self.assertRaises(config.RevisionConflictError):
        store.update_draft({'chattiness': 0.75}, expected_revision=0)

      self.assertEqual(store.snapshot().draft.chattiness, 0.25)

  def test_updating_preset_materializes_its_effective_values(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      snapshot = store.update_draft(
          {'performance_preset': 'low_latency'}, expected_revision=0
      )

      self.assertEqual(snapshot.draft.performance_preset, 'low_latency')
      self.assertEqual(snapshot.draft.media.frame_interval_ms, 500)
      self.assertEqual(snapshot.draft.generation.thinking_budget, 0)

  def test_promote_and_restore_active_are_transactional(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      store = config.ConfigStore(Path(temp_dir) / 'config.json')
      store.update_draft({'chattiness': 0.25}, expected_revision=0)
      previous, current = store.promote_draft()
      self.assertEqual(previous.chattiness, 0.5)
      self.assertEqual(current.chattiness, 0.25)

      store.restore_active(previous)
      snapshot = store.snapshot()
      self.assertEqual(snapshot.active.chattiness, 0.5)
      self.assertEqual(snapshot.draft.chattiness, 0.5)


if __name__ == '__main__':
  unittest.main()
