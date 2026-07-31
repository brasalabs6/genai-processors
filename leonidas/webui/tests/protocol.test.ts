import {describe, expect, it} from 'vitest';

import {
  audioMessage,
  clientMetricMessage,
  connectionClosePolicy,
  imageMessage,
  micOffMessage,
  resolveWebSocketUrl,
  textMessage,
} from '../src/protocol';

describe('Leonidas ProcessorPart protocol', () => {
  const location = {protocol: 'http:', hostname: '127.0.0.1'};

  it('uses the versioned standalone websocket path', () => {
    expect(resolveWebSocketUrl(location, '')).toBe(
      'ws://127.0.0.1:8765/api/v1/live',
    );
    expect(resolveWebSocketUrl(location, '?wsPort=9999')).toBe(
      'ws://127.0.0.1:9999/api/v1/live',
    );
  });

  it('rejects explicit non-websocket URLs', () => {
    expect(() =>
      resolveWebSocketUrl(location, '?ws=https%3A%2F%2Fexample.com'),
    ).toThrow(/ws:\/\//);
  });

  it('does not reconnect when another tab owns the media session', () => {
    expect(
      connectionClosePolicy(1008, 'Another media client owns the session'),
    ).toEqual({
      retry: true,
      label: 'Sessão em uso em outra aba',
    });
    expect(connectionClosePolicy(1006, '')).toEqual({
      retry: true,
      label: 'WebSocket offline',
    });
  });

  it('builds multimodal ProcessorPart messages', () => {
    expect(textMessage('hello')).toEqual({part: {text: 'hello'}, role: 'user'});
    expect(audioMessage('AQI=', 16000).part?.inline_data?.mime_type).toBe(
      'audio/pcm;rate=16000',
    );
    expect(imageMessage('image').part?.inline_data?.mime_type).toBe(
      'image/jpeg',
    );
    expect(micOffMessage().mimetype).toBe('application/x-mic-off');
    expect(clientMetricMessage('flush', 2).metadata).toEqual({
      name: 'flush',
      value: 2,
    });
  });

  it('does not expose config or reset commands over media websocket', async () => {
    const protocol = await import('../src/protocol');
    expect('configMessage' in protocol).toBe(false);
    expect('resetMessage' in protocol).toBe(false);
  });
});
