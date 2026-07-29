export interface BrowserLocation {
  protocol: string;
  hostname: string;
}

export interface ProcessorMessage {
  mimetype?: string;
  part?: {
    text?: string;
    inline_data?: {
      data?: string;
      mime_type?: string;
    };
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
  const explicitUrl = params.get('ws');
  if (explicitUrl) {
    if (!/^wss?:\/\//i.test(explicitUrl)) {
      throw new Error('The explicit WebSocket URL must start with ws:// or wss://.');
    }
    return explicitUrl;
  }

  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const port = params.get('wsPort') || '8765';
  if (!/^\d{1,5}$/.test(port) || Number(port) > 65535) {
    throw new Error('The WebSocket port is invalid.');
  }
  return `${scheme}://${location.hostname || '127.0.0.1'}:${port}`;
}

export function textMessage(text: string): ProcessorMessage {
  return {
    part: {text},
    role: 'user',
  };
}

export function audioMessage(
  base64Data: string,
  sampleRate: number,
): ProcessorMessage {
  return {
    part: {
      inline_data: {
        data: base64Data,
        mime_type: `audio/pcm;rate=${sampleRate}`,
      },
    },
    role: 'user',
    substream_name: 'realtime',
  };
}

export function imageMessage(base64Data: string): ProcessorMessage {
  return {
    part: {
      inline_data: {
        data: base64Data,
        mime_type: 'image/jpeg',
      },
    },
    role: 'user',
    substream_name: 'realtime',
  };
}

export function configMessage(chattiness: number): ProcessorMessage {
  return {
    mimetype: 'application/x-config',
    metadata: {chattiness},
  };
}

export function resetMessage(): ProcessorMessage {
  return {
    mimetype: 'application/x-command',
    metadata: {command: 'reset'},
  };
}

export function micOffMessage(): ProcessorMessage {
  return {
    mimetype: 'application/x-state',
    metadata: {mic: 'off'},
  };
}

export function parseServerMessage(raw: string): ProcessorMessage {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('The server returned an invalid ProcessorPart envelope.');
  }
  return value as ProcessorMessage;
}
