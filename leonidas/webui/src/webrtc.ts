import {CODEX_WEBRTC_OFFER_MIMETYPE} from './protocol';
import type {ProcessorMessage} from './protocol';

const ANSWER_TIMEOUT_MS = 15000;

type State = 'idle' | 'connecting' | 'connected' | 'failed';

export class CodexWebRtcController {
  private peer: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private answerResolve: ((sdp: string) => void) | null = null;
  private answerReject: ((error: Error) => void) | null = null;
  private answerTimer: number | null = null;
  private state: State = 'idle';

  constructor(
    private readonly audio: HTMLAudioElement,
    private readonly send: (message: ProcessorMessage) => boolean,
    private readonly changed: (active: boolean, state: State) => void,
  ) {}

  get microphoneActive(): boolean {
    return this.localStream?.getAudioTracks().some((track) => track.enabled) ?? false;
  }

  get active(): boolean {
    return this.peer !== null;
  }

  async start(): Promise<void> {
    if (this.peer) return;
    if (!window.RTCPeerConnection) {
      throw new Error('Este navegador não oferece suporte a WebRTC.');
    }
    this.setState('connecting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      const peer = new RTCPeerConnection();
      stream.getAudioTracks().forEach((track) => peer.addTrack(track, stream));
      peer.createDataChannel('oai-events');
      peer.addEventListener('track', (event) => {
        const remote = event.streams[0] ?? new MediaStream([event.track]);
        this.audio.srcObject = remote;
        this.audio.autoplay = true;
        this.audio.play().catch(() => undefined);
      });
      peer.addEventListener('connectionstatechange', () => {
        if (peer.connectionState === 'connected') this.setState('connected');
        if (['failed', 'closed', 'disconnected'].includes(peer.connectionState)) {
          this.setState('failed');
        }
      });
      this.peer = peer;
      this.localStream = stream;
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const sdp = peer.localDescription?.sdp;
      if (!sdp) throw new Error('O navegador não produziu uma oferta SDP.');
      const answer = new Promise<string>((resolve, reject) => {
        this.answerResolve = resolve;
        this.answerReject = reject;
        this.answerTimer = window.setTimeout(() => {
          reject(new Error('Tempo esgotado aguardando a resposta SDP do Codex.'));
        }, ANSWER_TIMEOUT_MS);
      });
      if (!this.send({
        mimetype: CODEX_WEBRTC_OFFER_MIMETYPE,
        part: {text: sdp},
        role: 'user',
        substream_name: 'realtime',
      })) {
        throw new Error('WebSocket indisponível para sinalização WebRTC.');
      }
      await peer.setRemoteDescription({type: 'answer', sdp: await answer});
      this.setState('connected');
    } catch (error) {
      await this.stop();
      this.setState('failed');
      throw error;
    }
  }

  acceptAnswer(sdp: string): void {
    if (!sdp.trim()) {
      this.reject(new Error('O backend retornou uma resposta SDP vazia.'));
      return;
    }
    this.answerResolve?.(sdp);
    this.clearAnswerWaiter();
  }

  reject(error: Error): void {
    this.answerReject?.(error);
    this.clearAnswerWaiter();
  }

  async toggleMicrophone(): Promise<void> {
    if (!this.peer) return this.start();
    const enabled = !this.microphoneActive;
    this.localStream?.getAudioTracks().forEach((track) => { track.enabled = enabled; });
    this.changed(this.microphoneActive, this.state);
  }

  async stop(): Promise<void> {
    this.reject(new Error('WebRTC session stopped.'));
    this.peer?.close();
    this.localStream?.getTracks().forEach((track) => track.stop());
    this.peer = null;
    this.localStream = null;
    this.audio.pause();
    this.audio.srcObject = null;
    this.setState('idle');
  }

  private clearAnswerWaiter(): void {
    if (this.answerTimer !== null) window.clearTimeout(this.answerTimer);
    this.answerTimer = null;
    this.answerResolve = null;
    this.answerReject = null;
  }

  private setState(state: State): void {
    this.state = state;
    this.changed(this.microphoneActive, state);
  }
}
