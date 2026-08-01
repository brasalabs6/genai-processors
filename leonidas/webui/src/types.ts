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

export interface CascadeConfig {
  stt_model_id: string;
  llm_model_id: string;
  tts_model_id: string;
  reasoning_effort: 'low' | 'medium' | 'high';
  language: 'pt';
  device: 'auto' | 'cuda' | 'cpu';
  voice_id: string;
  diarization_enabled: boolean;
}

export interface AgentConfig {
  schema_version: 1;
  pipeline_id: 'gemini_live' | 'cascade_local' | 'codex_realtime' | 'codex_text';
  model_id: string;
  voice_name: string | null;
  objective: string;
  chattiness: number;
  performance_preset: 'low_latency' | 'balanced' | 'quality';
  media: MediaConfig;
  vad: VadConfig;
  generation: GenerationConfig;
  cascade: CascadeConfig;
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
  thinking_field?: 'thinking_level' | 'thinking_budget';
}

export interface GeminiPipelineCapability {
  id: 'gemini_live';
  label: string;
  implemented: boolean;
  vision: boolean;
  models: ModelCapability[];
}

export interface CascadePipelineCapability {
  id: 'cascade_local';
  label: string;
  implemented: boolean;
  vision: false;
  input_modalities: string[];
  output_modalities: string[];
  stt_models: string[];
  llm_models: string[];
  tts_models: string[];
  voices: string[];
  reasoning_efforts: Array<'low' | 'medium' | 'high'>;
  devices: Array<'auto' | 'cuda' | 'cpu'>;
}

export interface CodexPipelineCapability {
  id: 'codex_realtime';
  label: string;
  implemented: boolean;
  vision: false;
  input_modalities: string[];
  output_modalities: string[];
  native_audio: boolean;
  voices: string[];
  models: ModelCapability[];
  realtime_versions: string[];
  requires_local_codex: boolean;
}

export interface CodexTextPipelineCapability {
  id: 'codex_text';
  label: string;
  implemented: boolean;
  vision: false;
  input_modalities: string[];
  output_modalities: string[];
  native_audio: false;
  voices: [];
  models: ModelCapability[];
  requires_local_codex: boolean;
}

export interface Capabilities {
  schema_version: number;
  pipelines: Array<GeminiPipelineCapability | CascadePipelineCapability | CodexPipelineCapability | CodexTextPipelineCapability>;
  voices: string[];
  presets: string[];
  diarization?: {
    id: string;
    state: string;
    model_id: string;
    device: string | null;
    weights_loaded: boolean;
    optional_dependency: string;
    runtime_path?: string;
    setup_command?: string;
    model_access_required?: boolean;
  };
}

export interface SessionSnapshot {
  state: SessionState;
  session_id: string | null;
  media_connected: boolean;
  started_at: number | null;
  last_error: string | null;
  last_error_detail: string | null;
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

export type ResourceState =
  | 'unloaded'
  | 'unavailable'
  | 'validating'
  | 'loading'
  | 'warming'
  | 'ready'
  | 'error';

export interface ResourceComponent {
  id: 'stt' | 'tts' | 'diarization';
  model_id: string | null;
  state: ResourceState;
  phase: string;
  device: string | null;
  gpu_name: string | null;
  load_ms: number | null;
  memory_allocated_mib: number | null;
  memory_reserved_mib: number | null;
  error: {
    stage: string;
    code: string;
    message: string;
    recovery: string;
  } | null;
}

export interface ResourceSnapshot {
  schema_version: 1;
  overall_state: 'unloaded' | 'loading' | 'ready' | 'error';
  components: ResourceComponent[];
}
