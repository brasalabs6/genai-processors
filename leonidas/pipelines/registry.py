"""Composition root for implemented Leonidas pipelines."""

from collections.abc import Mapping
from pathlib import Path

from genai_processors import processor
from genai_processors.core import rate_limit_audio

from leonidas import capabilities
from leonidas import config
from leonidas.cascade import groq_reasoning
from leonidas.cascade import diarization
from leonidas.cascade import pipeline as cascade_pipeline
from leonidas.cascade import resources
from leonidas.pipelines import gemini_live
from leonidas.pipelines import codex_realtime
from leonidas.pipelines import codex_text
from leonidas import telemetry


class PipelineRegistry:
  """Builds only fully implemented allowlisted pipelines."""

  def __init__(
      self,
      google_api_key: str | None,
      groq_api_key: str | None = None,
      voices: Mapping[str, Path] | None = None,
      cascade_resources: resources.CascadeResources | None = None,
      metrics: telemetry.MetricsStore | None = None,
  ):
    self._google_api_key = google_api_key
    self._groq_api_key = groq_api_key
    self._owns_resources = cascade_resources is None
    self._resources = cascade_resources or resources.CascadeResources(
        voices=dict(voices or {})
    )
    self._metrics = metrics

  def create(self, agent_config: config.AgentConfig) -> processor.Processor:
    agent_config.validate()
    if agent_config.pipeline_id == capabilities.PIPELINE_GEMINI:
      if not self._google_api_key:
        raise ValueError('GOOGLE_API_KEY is required for gemini_live')
      return gemini_live.create_live_commentator(
          api_key=self._google_api_key,
          agent_config=agent_config,
      )
    if agent_config.pipeline_id == capabilities.PIPELINE_CASCADE:
      if not self._groq_api_key:
        raise ValueError('GROQ_API_KEY is required for cascade_local')
      cascade = agent_config.cascade
      generation = agent_config.generation
      context_trigger = generation.context_trigger_tokens or 6000
      context_target = generation.context_target_tokens or min(
          4500, context_trigger - 1
      )
      try:
        transcriber = self._resources.transcriber(
            cascade.stt_model_id, cascade.device
        )
        synthesizer = self._resources.synthesizer(
            cascade.tts_model_id, cascade.device
        )
        diarizer = (
            self._resources.diarizer(cascade.device)
            if cascade.diarization_enabled
            else diarization.NullDiarizer()
        )
        synthesizer.validate_runtime()
        cascade_processor = cascade_pipeline.CascadeProcessor(
            transcriber=transcriber,
            reasoner=groq_reasoning.GroqReasoner(api_key=self._groq_api_key),
            synthesizer=synthesizer,
            objective=agent_config.objective,
            model_id=cascade.llm_model_id,
            reasoning_effort=cascade.reasoning_effort,
            voice_id=cascade.voice_id,
            language=cascade.language,
            context_trigger_tokens=context_trigger,
            context_target_tokens=context_target,
            metrics=self._metrics,
            diarizer=diarizer,
        )
        return cascade_processor + rate_limit_audio.RateLimitAudio(24000)
      except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    if agent_config.pipeline_id == capabilities.PIPELINE_CODEX:
      return codex_realtime.create(agent_config)
    if agent_config.pipeline_id == capabilities.PIPELINE_CODEX_TEXT:
      return codex_text.create(agent_config)
    raise ValueError(f'Unsupported pipeline: {agent_config.pipeline_id!r}')

  def requires_preparation(self, agent_config: config.AgentConfig) -> bool:
    return agent_config.pipeline_id == capabilities.PIPELINE_CASCADE

  async def prepare(self, agent_config: config.AgentConfig) -> None:
    """Loads local resources without affecting native Gemini pipelines."""
    agent_config.validate()
    if not self.requires_preparation(agent_config):
      return
    if not self._groq_api_key:
      raise ValueError('GROQ_API_KEY is required for cascade_local')
    cascade = agent_config.cascade
    await self._resources.ensure_ready(
        cascade.stt_model_id,
        cascade.tts_model_id,
        cascade.device,
        diarization_enabled=cascade.diarization_enabled,
    )

  @property
  def resources(self) -> resources.CascadeResources:
    return self._resources

  async def close(self) -> None:
    if self._owns_resources:
      await self._resources.close()
