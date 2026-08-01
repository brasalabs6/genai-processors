import type {
  AgentConfig,
  Capabilities,
  ConfigSnapshot,
  ModelCapability,
  SessionState,
} from './types';

export function effectiveConfig(
  snapshot: ConfigSnapshot,
  state: SessionState,
): AgentConfig {
  return state === 'stopped' ? snapshot.draft : snapshot.active;
}

export function modelsForPipeline(
  capabilities: Capabilities,
  pipelineId: string,
): ModelCapability[] {
  const pipeline = capabilities.pipelines.find((item) => item.id === pipelineId);
  if (!pipeline) return [];
  if (pipeline.id === 'gemini_live' || pipeline.id === 'codex_realtime' || pipeline.id === 'codex_text') return pipeline.models;
  return pipeline.llm_models.map((id) => ({id, label: id}));
}

export function visionForPipeline(
  capabilities: Capabilities,
  pipelineId: string,
): boolean {
  return capabilities.pipelines.find((item) => item.id === pipelineId)?.vision === true;
}
