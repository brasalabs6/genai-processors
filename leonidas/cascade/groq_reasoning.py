"""Groq OpenAI-compatible reasoning adapter."""

from collections.abc import Sequence
from typing import Any

import httpx

from leonidas import capabilities


class GroqReasoner:

  def __init__(
      self,
      *,
      api_key: str,
      client: httpx.AsyncClient | None = None,
      base_url: str = 'https://api.groq.com/openai/v1',
      timeout: float = 60.0,
  ):
    if not api_key:
      raise ValueError('GROQ_API_KEY is required for cascade_local')
    self._owns_client = client is None
    self._client = client or httpx.AsyncClient(
        base_url=base_url,
        headers={'Authorization': f'Bearer {api_key}'},
        timeout=timeout,
    )
    self._authorization = f'Bearer {api_key}'
    self._endpoint = f'{base_url.rstrip("/")}/chat/completions'

  async def respond(
      self,
      *,
      objective: str,
      history: Sequence[tuple[str, str]],
      prompt: str,
      model_id: str,
      reasoning_effort: str,
  ) -> str:
    if model_id not in (
        capabilities.GROQ_GPT_OSS_20B,
        capabilities.GROQ_GPT_OSS_120B,
    ):
      raise ValueError(f'Unsupported Groq reasoning model: {model_id!r}')
    if reasoning_effort not in ('low', 'medium', 'high'):
      raise ValueError('reasoning_effort must be low, medium, or high')
    messages: list[dict[str, Any]] = [{'role': 'system', 'content': objective}]
    messages.extend({'role': role, 'content': text} for role, text in history)
    messages.append({'role': 'user', 'content': prompt})
    response = await self._client.post(
        self._endpoint,
        headers={'Authorization': self._authorization},
        json={
            'model': model_id,
            'messages': messages,
            'reasoning_effort': reasoning_effort,
            'max_completion_tokens': 1024,
        },
    )
    response.raise_for_status()
    content = response.json()['choices'][0]['message']['content']
    if not isinstance(content, str) or not content.strip():
      raise RuntimeError('Groq returned an empty response')
    return content.strip()

  async def close(self) -> None:
    if self._owns_client:
      await self._client.aclose()
