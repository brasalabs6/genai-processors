export const MICROPHONE_SAMPLE_RATE = 16000;

const INITIAL_RESERVOIR_SECONDS = 0.08;
const UNDERRUN_RECOVERY_SECONDS = 0.02;
const CONTIGUOUS_EPSILON_SECONDS = 0.005;

export function parseSampleRate(mimetype: string): number | null {
  const match = /(?:^|;)\s*rate=(\d+)/i.exec(mimetype);
  return match ? Number(match[1]) : null;
}

export function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[index] ?? 0));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

export function pcm16BytesToFloat(bytes: Uint8Array): Float32Array {
  if (bytes.byteLength % 2 !== 0) {
    throw new Error('PCM16 payload must contain an even number of bytes.');
  }
  const sampleCount = bytes.byteLength / 2;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const output = new Float32Array(sampleCount);
  for (let index = 0; index < sampleCount; index += 1) {
    const sample = view.getInt16(index * 2, true);
    output[index] = sample < 0 ? sample / 0x8000 : sample / 0x7fff;
  }
  return output;
}

export class StreamingResampler {
  private readonly ratio: number;
  private buffered = new Float32Array(0);
  private position = 0;

  constructor(
    sourceRate: number,
    targetRate: number,
  ) {
    if (sourceRate <= 0 || targetRate <= 0) {
      throw new Error('Sample rates must be positive.');
    }
    this.ratio = sourceRate / targetRate;
  }

  process(input: Float32Array): Float32Array {
    if (input.length === 0) return new Float32Array(0);

    const combined = new Float32Array(this.buffered.length + input.length);
    combined.set(this.buffered);
    combined.set(input, this.buffered.length);

    const output: number[] = [];
    while (this.position + 1 < combined.length) {
      const leftIndex = Math.floor(this.position);
      const fraction = this.position - leftIndex;
      const left = combined[leftIndex] ?? 0;
      const right = combined[leftIndex + 1] ?? left;
      output.push(left + (right - left) * fraction);
      this.position += this.ratio;
    }

    const consumed = Math.floor(this.position);
    this.buffered = combined.slice(consumed);
    this.position -= consumed;
    return Float32Array.from(output);
  }
}

export class PcmPlayer {
  private context: AudioContext | null = null;
  private nextPlaybackTime = 0;
  private readonly scheduled = new Set<AudioBufferSourceNode>();
  private queue: Promise<void> = Promise.resolve();
  private generation = 0;
  private closed = false;

  constructor(
    private readonly contextFactory: () => AudioContext = () =>
      new AudioContext({latencyHint: 'interactive'}),
  ) {}

  async unlock(): Promise<void> {
    if (this.closed) throw new Error('PCM player is closed.');
    const context = this.getContext();
    if (context.state === 'suspended') {
      await context.resume();
    }
    if (context.state !== 'running') {
      throw new Error(`AudioContext não está ativo: ${context.state}.`);
    }
  }

  enqueue(base64Data: string, mimetype: string): Promise<void> {
    if (this.closed) return Promise.reject(new Error('PCM player is closed.'));
    const generation = this.generation;
    const operation = this.queue.then(() =>
      this.enqueueNow(base64Data, mimetype, generation),
    );
    this.queue = operation.catch(() => undefined);
    return operation;
  }

  private async enqueueNow(
    base64Data: string,
    mimetype: string,
    generation: number,
  ): Promise<void> {
    if (generation !== this.generation || this.closed) return;
    const sampleRate = parseSampleRate(mimetype);
    if (!sampleRate) {
      throw new Error(`Missing PCM sample rate in ${mimetype}.`);
    }
    const samples = pcm16BytesToFloat(base64ToBytes(base64Data));
    if (samples.length === 0) return;

    const context = this.getContext();
    if (context.state === 'suspended') {
      await context.resume();
    }
    if (context.state !== 'running') {
      throw new Error(`AudioContext não está ativo: ${context.state}.`);
    }
    if (generation !== this.generation || this.closed) return;
    const buffer = context.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(new Float32Array(samples), 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    source.addEventListener('ended', () => {
      this.scheduled.delete(source);
      source.disconnect();
    }, {once: true});

    // Only the first chunk receives the full reservoir. Once a continuous
    // timeline exists, every following chunk starts at the exact prior end.
    // The previous `max(currentTime + 80 ms, nextPlaybackTime)` applied the
    // reservoir repeatedly and inserted audible micro-gaps whenever the main
    // thread advanced between WebSocket chunks.
    const continuous =
      this.nextPlaybackTime > context.currentTime + CONTIGUOUS_EPSILON_SECONDS;
    const startAt = continuous
      ? this.nextPlaybackTime
      : context.currentTime + (
          this.scheduled.size === 0
            ? INITIAL_RESERVOIR_SECONDS
            : UNDERRUN_RECOVERY_SECONDS
        );
    source.start(startAt);
    this.nextPlaybackTime = startAt + buffer.duration;
    this.scheduled.add(source);
  }

  flush(): void {
    this.generation += 1;
    // A new generation must not wait behind an old resume/decode promise.
    this.queue = Promise.resolve();
    for (const source of this.scheduled) {
      try {
        source.stop();
      } catch {
        // A source may already have ended between iteration and stop().
      }
    }
    this.scheduled.clear();
    this.nextPlaybackTime = this.context?.currentTime ?? 0;
  }

  async close(): Promise<void> {
    this.closed = true;
    this.flush();
    if (this.context) {
      await this.context.close();
      this.context = null;
    }
  }

  private getContext(): AudioContext {
    if (this.closed) throw new Error('PCM player is closed.');
    if (!this.context || this.context.state === 'closed') {
      this.context = this.contextFactory();
      this.nextPlaybackTime = this.context.currentTime;
    }
    return this.context;
  }
}
