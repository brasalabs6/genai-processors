import {describe, expect, it} from 'vitest';

import {
  DEFAULT_LIVE_MODEL,
  LIVE_MODELS,
  audioMessage,
  configMessage,
  isLiveModelId,
  resolveWebSocketUrl,
  textMessage,
} from '../src/protocol';

describe('WebSocket protocol', () => {
  const location = {
    protocol: 'http:',
    hostname: '127.0.0.1',
  };

  it('uses the standalone websocket default', () => {
    expect(resolveWebSocketUrl(location, '')).toBe('ws://127.0.0.1:8765');
  });

  it('accepts an explicit websocket port', () => {
    expect(resolveWebSocketUrl(location, '?wsPort=9999')).toBe(
      'ws://127.0.0.1:9999',
    );
  });

  it('requires an explicit websocket URL to use ws or wss', () => {
    expect(() =>
      resolveWebSocketUrl(location, '?ws=https%3A%2F%2Fexample.com'),
    ).toThrow(/ws:\/\//);
  });

  it('builds text, audio, and config messages', () => {
    expect(textMessage('hello')).toEqual({
      part: {text: 'hello'},
      role: 'user',
    });
    expect(audioMessage('AQI=', 16000)).toEqual({
      part: {
        inline_data: {
          data: 'AQI=',
          mime_type: 'audio/pcm;rate=16000',
        },
      },
      role: 'user',
      substream_name: 'realtime',
    });
    expect(configMessage(0.4, LIVE_MODELS.GEMINI_3_1)).toEqual({
      mimetype: 'application/x-config',
      metadata: {
        chattiness: 0.4,
        live_model: 'gemini-3.1-flash-live-preview',
      },
    });
  });

  it('allowlists the two supported live models and defaults to 2.5', () => {
    expect(DEFAULT_LIVE_MODEL).toBe(
      'gemini-2.5-flash-native-audio-preview-12-2025',
    );
    expect(isLiveModelId(LIVE_MODELS.GEMINI_2_5)).toBe(true);
    expect(isLiveModelId(LIVE_MODELS.GEMINI_3_1)).toBe(true);
    expect(isLiveModelId('gemini-arbitrary-live')).toBe(false);
  });
});
