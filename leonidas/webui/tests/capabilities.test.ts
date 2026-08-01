import {describe, expect, it} from 'vitest';

import {effectiveConfig, modelsForPipeline, visionForPipeline} from '../src/capabilities';
import type {AgentConfig, Capabilities, ConfigSnapshot} from '../src/types';

const capabilities: Capabilities = {
  schema_version: 1,
  voices: ['Kore'],
  presets: ['balanced'],
  pipelines: [
    {
      id: 'gemini_live', label: 'Gemini', implemented: true, vision: true,
      models: [{id: 'gemini', label: 'Gemini', thinking_field: 'thinking_budget'}],
    },
    {
      id: 'cascade_local', label: 'Local', implemented: true, vision: false,
      input_modalities: ['audio', 'text'], output_modalities: ['audio'],
      stt_models: ['parakeet'], llm_models: ['gpt-oss'],
      tts_models: ['xtts'], voices: ['leonidas'],
      reasoning_efforts: ['low', 'medium', 'high'], devices: ['auto', 'cuda', 'cpu'],
    },
  ],
};

describe('pipeline capabilities', () => {
  it('selects models from the explicit pipeline contract', () => {
    expect(modelsForPipeline(capabilities, 'gemini_live')).toEqual([
      {id: 'gemini', label: 'Gemini', thinking_field: 'thinking_budget'},
    ]);
    expect(modelsForPipeline(capabilities, 'cascade_local')).toEqual([
      {id: 'gpt-oss', label: 'gpt-oss'},
    ]);
  });

  it('never silently enables vision for the cascade', () => {
    expect(visionForPipeline(capabilities, 'cascade_local')).toBe(false);
    expect(visionForPipeline(capabilities, 'gemini_live')).toBe(true);
  });

  it('uses active media capabilities while a session is running', () => {
    const base = {
      schema_version: 1, model_id: 'model', voice_name: null,
      objective: 'objective', chattiness: 0.5, performance_preset: 'balanced',
      media: {frame_interval_ms: 1000, max_width: 1280, max_height: 720, jpeg_quality: 0.75, model_resolution: 'medium'},
      vad: {start_sensitivity: null, end_sensitivity: null, prefix_padding_ms: null, silence_duration_ms: null},
      generation: {temperature: null, thinking_level: null, thinking_budget: null, context_trigger_tokens: null, context_target_tokens: null},
      cascade: {stt_model_id: 'stt', llm_model_id: 'llm', tts_model_id: 'tts', reasoning_effort: 'medium', language: 'pt', device: 'auto', voice_id: 'leonidas', diarization_enabled: false},
    } satisfies Omit<AgentConfig, 'pipeline_id'>;
    const snapshot = {
      active: {...base, pipeline_id: 'cascade_local'},
      draft: {...base, pipeline_id: 'gemini_live'},
      revision: 1, dirty_fields: ['pipeline_id'],
    } as ConfigSnapshot;

    expect(effectiveConfig(snapshot, 'running').pipeline_id).toBe('cascade_local');
    expect(effectiveConfig(snapshot, 'stopped').pipeline_id).toBe('gemini_live');
  });
});
