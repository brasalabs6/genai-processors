import {describe, expect, it} from 'vitest';

import {
  PcmPlayer,
  StreamingResampler,
  bytesToBase64,
  floatToPcm16,
  parseSampleRate,
  pcm16BytesToFloat,
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

  it('rejects truncated PCM16 payloads', () => {
    expect(() => pcm16BytesToFloat(new Uint8Array([1]))).toThrow('even');
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

  it('resumes a suspended context before scheduling PCM output', async () => {
    const starts: number[] = [];
    const context = {
      state: 'suspended',
      currentTime: 1,
      destination: {},
      async resume() { this.state = 'running'; },
      createBuffer: (_channels: number, samples: number, rate: number) => ({
        duration: samples / rate,
        copyToChannel: () => undefined,
      }),
      createBufferSource: () => ({
        buffer: null,
        connect: () => undefined,
        disconnect: () => undefined,
        addEventListener: () => undefined,
        start: (at: number) => starts.push(at),
        stop: () => undefined,
      }),
    };
    const player = new PcmPlayer(
      () => context as unknown as AudioContext,
    );

    await player.enqueue('AQI=', 'audio/pcm;rate=24000');

    expect(context.state).toBe('running');
    expect(starts).toEqual([1.08]);
  });

  it('keeps later chunks contiguous instead of reapplying the reservoir', async () => {
    const starts: number[] = [];
    const context = {
      state: 'running',
      currentTime: 1,
      destination: {},
      createBuffer: (_channels: number, samples: number, rate: number) => ({
        duration: samples / rate,
        copyToChannel: () => undefined,
      }),
      createBufferSource: () => ({
        buffer: null,
        connect: () => undefined,
        disconnect: () => undefined,
        addEventListener: () => undefined,
        start: (at: number) => starts.push(at),
        stop: () => undefined,
      }),
    };
    const player = new PcmPlayer(() => context as unknown as AudioContext);

    await player.enqueue('AQI=', 'audio/pcm;rate=24000');
    context.currentTime = 1.05;
    await player.enqueue('AQI=', 'audio/pcm;rate=24000');

    expect(starts).toHaveLength(2);
    expect(starts[1]).toBeCloseTo((starts[0] ?? 0) + 1 / 24000, 8);
    expect(starts[1]).toBeLessThan(1.13);
  });

  it('surfaces a browser refusal to resume audio', async () => {
    const context = {
      state: 'suspended',
      currentTime: 0,
      async resume() { throw new Error('resume blocked'); },
    };
    const player = new PcmPlayer(
      () => context as unknown as AudioContext,
    );

    await expect(
      player.enqueue('AQI=', 'audio/pcm;rate=24000'),
    ).rejects.toThrow('resume blocked');
  });

  it('lets a flushed generation bypass an old pending resume', async () => {
    let releaseResume!: () => void;
    const resumeGate = new Promise<void>((resolve) => { releaseResume = resolve; });
    const starts: number[] = [];
    const context = {
      state: 'suspended',
      currentTime: 0,
      destination: {},
      async resume() { await resumeGate; this.state = 'running'; },
      createBuffer: (_channels: number, samples: number, rate: number) => ({
        duration: samples / rate,
        copyToChannel: () => undefined,
      }),
      createBufferSource: () => ({
        buffer: null,
        connect: () => undefined,
        disconnect: () => undefined,
        addEventListener: () => undefined,
        start: (at: number) => starts.push(at),
        stop: () => undefined,
      }),
    };
    const player = new PcmPlayer(() => context as unknown as AudioContext);
    const stale = player.enqueue('AQI=', 'audio/pcm;rate=24000');
    await Promise.resolve();
    player.flush();
    context.state = 'running';
    const current = player.enqueue('AQI=', 'audio/pcm;rate=24000');
    await current;
    releaseResume();
    await stale;

    expect(starts).toHaveLength(1);
  });
});
