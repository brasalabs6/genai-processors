import {
  MICROPHONE_SAMPLE_RATE,
  StreamingResampler,
  bytesToBase64,
  floatToPcm16,
} from './audio';
import {audioMessage, imageMessage, micOffMessage} from './protocol';
import type {ProcessorMessage} from './protocol';
import type {MediaConfig} from './types';

type VisualSource = 'none' | 'camera' | 'screen';

export class MediaController {
  private microphoneStream: MediaStream | null = null;
  private microphoneContext: AudioContext | null = null;
  private microphoneSource: MediaStreamAudioSourceNode | null = null;
  private microphoneWorklet: AudioWorkletNode | null = null;
  private visualStream: MediaStream | null = null;
  private visualSource: VisualSource = 'none';
  private frameTimer: number | null = null;
  private framePending = false;
  private readonly canvas = document.createElement('canvas');

  constructor(
    private readonly preview: HTMLVideoElement,
    private readonly send: (message: ProcessorMessage) => void,
    private readonly canSend: () => boolean,
    private readonly mediaConfig: () => MediaConfig,
    private readonly changed: (detail: {
      microphone: boolean;
      visual: VisualSource;
    }) => void,
  ) {}

  get microphoneActive(): boolean {
    return this.microphoneStream !== null;
  }

  get activeVisual(): VisualSource {
    return this.visualSource;
  }

  async toggleMicrophone(): Promise<void> {
    if (this.microphoneStream) await this.stopMicrophone();
    else await this.startMicrophone();
  }

  private async startMicrophone(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
      video: false,
    });
    const context = new AudioContext({latencyHint: 'interactive'});
    await context.audioWorklet.addModule('/pcm-capture-worklet.js');
    const source = context.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(context, 'pcm-capture');
    const silent = context.createGain();
    silent.gain.value = 0;
    source.connect(worklet);
    worklet.connect(silent);
    silent.connect(context.destination);
    const resampler = new StreamingResampler(context.sampleRate, MICROPHONE_SAMPLE_RATE);
    worklet.port.onmessage = (event: MessageEvent<unknown>) => {
      if (!(event.data instanceof Float32Array) || !this.canSend()) return;
      const samples = resampler.process(event.data);
      if (!samples.length) return;
      const pcm = floatToPcm16(samples);
      this.send(
        audioMessage(
          bytesToBase64(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength)),
          MICROPHONE_SAMPLE_RATE,
        ),
      );
    };
    worklet.port.start();
    this.microphoneStream = stream;
    this.microphoneContext = context;
    this.microphoneSource = source;
    this.microphoneWorklet = worklet;
    stream.getAudioTracks()[0]?.addEventListener('ended', () => void this.stopMicrophone());
    this.emitChanged();
  }

  async stopMicrophone(): Promise<void> {
    this.microphoneWorklet?.disconnect();
    this.microphoneSource?.disconnect();
    this.microphoneStream?.getTracks().forEach((track) => track.stop());
    if (this.microphoneContext?.state !== 'closed') await this.microphoneContext?.close();
    this.microphoneStream = null;
    this.microphoneContext = null;
    this.microphoneSource = null;
    this.microphoneWorklet = null;
    if (this.canSend()) this.send(micOffMessage());
    this.emitChanged();
  }

  async toggleCamera(): Promise<void> {
    if (this.visualSource === 'camera') return this.stopVisual();
    await this.stopVisual();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {width: {ideal: 1280}, height: {ideal: 720}},
    });
    this.activateVisual(stream, 'camera');
  }

  async toggleScreen(): Promise<void> {
    if (this.visualSource === 'screen') return this.stopVisual();
    await this.stopVisual();
    const stream = await navigator.mediaDevices.getDisplayMedia({
      audio: false,
      video: true,
    });
    this.activateVisual(stream, 'screen');
  }

  private activateVisual(stream: MediaStream, source: Exclude<VisualSource, 'none'>): void {
    this.visualStream = stream;
    this.visualSource = source;
    this.preview.srcObject = stream;
    this.preview.hidden = false;
    stream.getVideoTracks()[0]?.addEventListener('ended', () => void this.stopVisual());
    this.scheduleFrames();
    this.emitChanged();
  }

  refreshFrameSchedule(): void {
    if (this.visualStream) this.scheduleFrames();
  }

  private scheduleFrames(): void {
    if (this.frameTimer !== null) window.clearInterval(this.frameTimer);
    const interval = this.mediaConfig().frame_interval_ms;
    this.frameTimer = window.setInterval(() => void this.captureFrame(), interval);
    void this.captureFrame();
  }

  async stopVisual(): Promise<void> {
    if (this.frameTimer !== null) window.clearInterval(this.frameTimer);
    this.frameTimer = null;
    this.visualStream?.getTracks().forEach((track) => track.stop());
    this.visualStream = null;
    this.visualSource = 'none';
    this.preview.srcObject = null;
    this.preview.hidden = true;
    this.emitChanged();
  }

  private async captureFrame(): Promise<void> {
    if (
      !this.canSend() ||
      !this.visualStream ||
      this.framePending ||
      this.preview.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
    ) return;
    this.framePending = true;
    try {
      const config = this.mediaConfig();
      const scale = Math.min(
        1,
        config.max_width / this.preview.videoWidth,
        config.max_height / this.preview.videoHeight,
      );
      this.canvas.width = Math.max(1, Math.round(this.preview.videoWidth * scale));
      this.canvas.height = Math.max(1, Math.round(this.preview.videoHeight * scale));
      this.canvas.getContext('2d')?.drawImage(
        this.preview,
        0,
        0,
        this.canvas.width,
        this.canvas.height,
      );
      const blob = await new Promise<Blob | null>((resolve) =>
        this.canvas.toBlob(resolve, 'image/jpeg', config.jpeg_quality),
      );
      if (!blob) return;
      this.send(imageMessage(bytesToBase64(new Uint8Array(await blob.arrayBuffer()))));
    } finally {
      this.framePending = false;
    }
  }

  async close(): Promise<void> {
    await this.stopMicrophone();
    await this.stopVisual();
  }

  private emitChanged(): void {
    this.changed({microphone: this.microphoneActive, visual: this.visualSource});
  }
}
