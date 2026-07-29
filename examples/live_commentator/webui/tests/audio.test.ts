import {describe, expect, it} from 'vitest';

import {
  StreamingResampler,
  bytesToBase64,
  floatToPcm16,
  parseSampleRate,
} from '../src/audio';

describe('audio helpers', () => {
  it('parses sample rates from PCM mimetypes', () => {
    expect(parseSampleRate('audio/pcm;rate=24000')).toBe(24000);
    expect(parseSampleRate('audio/l16; rate=16000')).toBe(16000);
    expect(parseSampleRate('audio/wav')).toBeNull();
  });

  it('converts normalized float audio to signed 16-bit PCM', () => {
    const pcm = floatToPcm16(new Float32Array([-1, -0.5, 0, 0.5, 1]));
    expect(Array.from(pcm)).toEqual([-32768, -16384, 0, 16383, 32767]);
  });

  it('encodes bytes with standard base64', () => {
    expect(bytesToBase64(new Uint8Array([72, 101, 108, 108, 111]))).toBe(
      'SGVsbG8=',
    );
  });

  it('resamples a continuous stream without resetting chunk position', () => {
    const resampler = new StreamingResampler(48000, 16000);
    const first = resampler.process(
      Float32Array.from({length: 480}, (_, index) => index / 480),
    );
    const second = resampler.process(
      Float32Array.from({length: 480}, (_, index) => (480 + index) / 480),
    );

    expect(first.length + second.length).toBeGreaterThanOrEqual(319);
    expect(first.length + second.length).toBeLessThanOrEqual(320);
    expect(second[0]).toBeGreaterThan(first[first.length - 1] ?? 0);
  });
});
