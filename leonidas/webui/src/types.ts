export type SessionState =
  | 'stopped'
  | 'starting'
  | 'running'
  | 'stopping'
  | 'error';

export interface MediaConfig {
  frame_interval_ms: number;
  max_width: number;
  max_height: number;
  jpeg_quality: number;
  model_resolution: 'low' | 'medium' | 'high';
}
export interface VadConfig {
  start_sensitivity: 'high' | 'low' | null;
  end_sensitivity: 'high' | 'low' | null;
  prefix_padding_ms: number | null;
  silence_duration_ms: number | null;
}

export interface GenerationConfig {
  temperature: number | null;
  thinking_level: 'minimal' | 'low' | 'medium' | 'high' | null;
  thinking_budget: number | null;
  context_trigger_tokens: number | null;
  context_target_tokens: number | null;
}

export interface AgentConfig {
  schema_version: 1;
  pipeline_id: 'gemini_live';
  model_id: string;
  voice_name: string | null;
  objective: string;
  chattiness: number;
  performance_preset: 'low_latency' | 'balanced' | 'quality';
  media: MediaConfig;
  vad: VadConfig;
  generation: GenerationConfig;
}

export interface ConfigSnapshot {
  active: AgentConfig;
  draft: AgentConfig;
  revision: number;
  dirty_fields: string[];
}

export interface ModelCapability {
  id: string;
  label: string;
  thinking_field: 'thinking_level' | 'thinking_budget';
}

export interface Capabilities {
  schema_version: number;
  pipelines: Array<{
    id: string;
    label: string;
    models: ModelCapability[];
  }>;
  voices: string[];
  presets: string[];
}

export interface SessionSnapshot {
  state: SessionState;
  session_id: string | null;
  media_connected: boolean;
  started_at: number | null;
  last_error: string | null;
}

export interface MetricSummary {
  count: number;
  current: number;
  mean: number;
  p50: number;
  p95: number;
  samples: number[];
}

export interface MetricsSnapshot {
  timestamp: number;
  metrics: Record<string, MetricSummary>;
  counters: Record<string, number>;
}
