"""Composition root for implemented Leonidas pipelines."""

from genai_processors import processor

from leonidas import config
from leonidas.pipelines import gemini_live


class PipelineRegistry:
  """Builds only fully implemented allowlisted pipelines."""

  def __init__(self, google_api_key: str):
    if not google_api_key:
      raise ValueError('GOOGLE_API_KEY is required')
    self._google_api_key = google_api_key

  def create(self, agent_config: config.AgentConfig) -> processor.Processor:
    agent_config.validate()
    if agent_config.pipeline_id != 'gemini_live':
      raise ValueError(f'Unsupported pipeline: {agent_config.pipeline_id!r}')
    return gemini_live.create_live_commentator(
        api_key=self._google_api_key,
        agent_config=agent_config,
    )
