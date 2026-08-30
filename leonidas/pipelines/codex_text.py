"""Turn-based Codex app-server fallback for ChatGPT-authenticated installs."""

from __future__ import annotations

from typing import Any

from genai_processors import content_api
from genai_processors import processor

from leonidas import config
from leonidas.pipelines import codex_realtime


class CodexTextProcessor(processor.Processor):

  def __init__(self, agent_config: config.AgentConfig):
    super().__init__()
    self._config = agent_config

  async def call(self, content: Any):
    client, cleanup = await codex_realtime._open_text_client()
    try:
      await client.start_thread(self._config.objective)
      async for part in content:
        if content_api.is_image(part.mimetype) or content_api.is_audio(
            part.mimetype
        ):
          raise ValueError('codex_text accepts text input only')
        if not content_api.is_text(part.mimetype) or not part.text.strip():
          continue
        yield content_api.ProcessorPart(
            '',
            mimetype='application/x-state',
            metadata={'agent_state': 'thinking'},
        )
        response = await client.respond(part.text.strip())
        if response:
          yield content_api.ProcessorPart(response, role='model')
        yield content_api.ProcessorPart(
            '', metadata={'generation_complete': True, 'turn_complete': True}
        )
    finally:
      await cleanup()


def create(agent_config: config.AgentConfig) -> processor.Processor:
  agent_config.validate()
  if agent_config.pipeline_id != 'codex_text':
    raise ValueError('Codex text pipeline received incompatible configuration')
  return CodexTextProcessor(agent_config)
