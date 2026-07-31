import unittest

from leonidas.cascade import context


class BoundedConversationHistoryTest(unittest.TestCase):

  def test_evicts_oldest_complete_pairs_to_target_budget(self):
    history = context.BoundedConversationHistory(
        max_turns=20, trigger_tokens=40, target_tokens=24
    )
    history.append('primeira pergunta longa', 'primeira resposta longa')
    history.append('segunda pergunta longa', 'segunda resposta longa')
    history.append('terceira pergunta', 'terceira resposta')

    messages, removed = history.for_prompt(
        objective='ajude', prompt='nova pergunta longa'
    )

    self.assertGreaterEqual(removed, 1)
    self.assertEqual(len(messages) % 2, 0)
    self.assertEqual(messages[-2][0], 'user')
    self.assertEqual(messages[-1][0], 'assistant')
    self.assertNotIn(('user', 'primeira pergunta longa'), messages)

  def test_keeps_latest_complete_pair_when_single_pair_exceeds_target(self):
    history = context.BoundedConversationHistory(
        max_turns=20, trigger_tokens=12, target_tokens=8
    )
    history.append('pergunta recente muito longa', 'resposta recente muito longa')

    messages, removed = history.for_prompt(objective='x', prompt='y')

    self.assertEqual(removed, 0)
    self.assertEqual(len(messages), 2)

  def test_hard_turn_cap_never_splits_a_pair(self):
    history = context.BoundedConversationHistory(
        max_turns=2, trigger_tokens=1000, target_tokens=800
    )
    for number in range(4):
      history.append(f'u{number}', f'a{number}')

    self.assertEqual(
        history.snapshot(),
        [('user', 'u2'), ('assistant', 'a2'), ('user', 'u3'), ('assistant', 'a3')],
    )

  def test_rejects_invalid_token_limits(self):
    with self.assertRaises(ValueError):
      context.BoundedConversationHistory(trigger_tokens=10, target_tokens=10)


if __name__ == '__main__':
  unittest.main()
