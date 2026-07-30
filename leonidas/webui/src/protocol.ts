export interface BrowserLocation {
  protocol: string;
  hostname: string;
}
export interface ProcessorMessage {
  mimetype?: string;
  part?: {
    text?: string;
    inline_data?: {data?: string; mime_type?: string};
  };
  role?: string;
  substream_name?: string;
  metadata?: Record<string, unknown>;
}

export function resolveWebSocketUrl(
  location: BrowserLocation,
  search: string,
): string {
  const params = new URLSearchParams(search);
  const explicit = params.get('ws');
  if (explicit) {
    if (!/^wss?:\/\//i.test(explicit)) {
      throw new Error('A URL WebSocket deve começar com ws:// ou wss://.');
    }
    return explicit;
  }
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const port = params.get('wsPort') || '8765';
  if (!/^\d{1,5}$/.test(port) || Number(port) > 65535) {
    throw new Error('Porta WebSocket inválida.');
  }
  return `${scheme}://${location.hostname || '127.0.0.1'}:${port}/api/v1/live`;
}

export function textMessage(text: string): ProcessorMessage {
  return {part: {text}, role: 'user'};
}

export function audioMessage(data: string, rate: number): ProcessorMessage {
  return {
    part: {inline_data: {data, mime_type: `audio/pcm;rate=${rate}`}},
    role: 'user',
    substream_name: 'realtime',
  };
}

export function imageMessage(data: string): ProcessorMessage {
  return {
    part: {inline_data: {data, mime_type: 'image/jpeg'}},
    role: 'user',
    substream_name: 'realtime',
  };
}

export function micOffMessage(): ProcessorMessage {
  return {mimetype: 'application/x-mic-off', metadata: {mic: 'off'}};
}

export function clientMetricMessage(
  name: string,
  value: number,
): ProcessorMessage {
  return {mimetype: 'application/x-client-metric', metadata: {name, value}};
}

export function parseServerMessage(raw: string): ProcessorMessage {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Envelope ProcessorPart inválido.');
  }
  return value as ProcessorMessage;
}
