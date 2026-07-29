import {describe, expect, it} from 'vitest';

import {
  audioMessage,
  configMessage,
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
    expect(configMessage(0.4)).toEqual({
      mimetype: 'application/x-config',
      metadata: {chattiness: 0.4},
    });
  });
});
