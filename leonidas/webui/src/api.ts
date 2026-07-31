import type {
  Capabilities,
  ConfigSnapshot,
  MetricsSnapshot,
  ResourceSnapshot,
  SessionSnapshot,
} from './types';

interface Envelope<T> {
  data: T | null;
  error: {code: string; message: string} | null;
  request_id: string;
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init.body ? {'Content-Type': 'application/json'} : {}),
        ...init.headers,
      },
    });
    const envelope = (await response.json()) as Envelope<T>;
    if (!response.ok || envelope.error) {
      throw new ApiError(
        envelope.error?.code ?? 'request_failed',
        envelope.error?.message ?? `HTTP ${response.status}`,
        response.status,
      );
    }
    return envelope.data as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

export const controlApi = {
  capabilities: () => request<Capabilities>('/api/v1/capabilities'),
  config: () => request<ConfigSnapshot>('/api/v1/config'),
  session: () => request<SessionSnapshot>('/api/v1/session'),
  metrics: () => request<MetricsSnapshot>('/api/v1/metrics'),
  resources: () => request<ResourceSnapshot>('/api/v1/resources'),
  updateDraft: (revision: number, updates: Record<string, unknown>) =>
    request<ConfigSnapshot>('/api/v1/config/draft', {
      method: 'PUT',
      body: JSON.stringify({expected_revision: revision, updates}),
    }),
  apply: () =>
    request<ConfigSnapshot>('/api/v1/config/apply', {
      method: 'POST',
      body: '{}',
    }),
  start: () =>
    request<SessionSnapshot>('/api/v1/session/start', {
      method: 'POST',
      body: '{}',
    }),
  stop: () =>
    request<SessionSnapshot>('/api/v1/session/stop', {
      method: 'POST',
      body: '{}',
    }),
  previewVoice: async (modelId: string, voiceName: string): Promise<Blob> => {
    const response = await fetch('/api/v1/voices/preview', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model_id: modelId, voice_name: voiceName}),
    });
    if (!response.ok) {
      const envelope = (await response.json()) as Envelope<never>;
      throw new ApiError(
        envelope.error?.code ?? 'preview_failed',
        envelope.error?.message ?? 'A prévia falhou.',
        response.status,
      );
    }
    return response.blob();
  },
  logFiles: () =>
    request<{files: Array<{id: string; size: number; modified_ns: number}>}>(
      '/api/v1/logs',
    ),
  logFile: (id: string, cursor = 0) =>
    request<{lines: string[]; next_cursor: number}>(
      `/api/v1/logs/${encodeURIComponent(id)}?cursor=${cursor}&limit=2000`,
    ),
};
