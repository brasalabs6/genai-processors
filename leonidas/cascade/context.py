"""Token-budgeted conversation history for the local cascade."""

from collections.abc import Sequence


Message = tuple[str, str]


def estimate_tokens(text: str) -> int:
  """Returns a deterministic conservative approximation for prompt budgeting.

  The Groq-compatible endpoint does not expose a tokenizer locally. Four
  Unicode characters per token plus one token of framing overhead is stable,
  cheap, and intentionally conservative for Portuguese prose.
  """
  return max(1, (len(text) + 3) // 4) + 1


class BoundedConversationHistory:
  """Stores complete user/assistant pairs within turn and token limits."""

  def __init__(
      self,
      *,
      max_turns: int = 20,
      trigger_tokens: int = 6000,
      target_tokens: int = 4500,
  ):
    if max_turns <= 0:
      raise ValueError('max_turns must be positive')
    if target_tokens <= 0 or trigger_tokens <= target_tokens:
      raise ValueError('context token limits are invalid')
    self._max_turns = max_turns
    self._trigger_tokens = trigger_tokens
    self._target_tokens = target_tokens
    self._messages: list[Message] = []

  @staticmethod
  def _cost(objective: str, prompt: str, messages: Sequence[Message]) -> int:
    return (
        estimate_tokens(objective)
        + estimate_tokens(prompt)
        + sum(estimate_tokens(text) + 2 for _role, text in messages)
    )

  def for_prompt(
      self, *, objective: str, prompt: str
  ) -> tuple[list[Message], int]:
    """Returns history for inference and evicts oldest complete pairs if needed."""
    removed_turns = 0
    if self._cost(objective, prompt, self._messages) > self._trigger_tokens:
      # Keep the newest complete pair even when it alone exceeds the target.
      while (
          len(self._messages) > 2
          and self._cost(objective, prompt, self._messages)
          > self._target_tokens
      ):
        del self._messages[:2]
        removed_turns += 1
    return list(self._messages), removed_turns

  def append(self, user: str, assistant: str) -> int:
    """Appends one complete turn and enforces the independent hard turn cap."""
    self._messages.extend((('user', user), ('assistant', assistant)))
    overflow = max(0, len(self._messages) // 2 - self._max_turns)
    if overflow:
      del self._messages[: overflow * 2]
    return overflow

  def snapshot(self) -> list[Message]:
    return list(self._messages)
