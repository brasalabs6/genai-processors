import './styles.css';

import {
  MICROPHONE_SAMPLE_RATE,
  PcmPlayer,
  StreamingResampler,
  bytesToBase64,
  floatToPcm16,
} from './audio';
import {
  DEFAULT_LIVE_MODEL,
  LiveModelId,
  ProcessorMessage,
  audioMessage,
  configMessage,
  imageMessage,
  isLiveModelId,
  micOffMessage,
  parseServerMessage,
  resetMessage,
  resolveWebSocketUrl,
  textMessage,
} from './protocol';

type ConnectionState =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected';
type AgentState =
  | 'ready'
  | 'listening'
  | 'observing'
  | 'thinking'
  | 'speaking'
  | 'interrupted'
  | 'resetting'
  | 'error';
type VisualSource = 'none' | 'camera' | 'screen';
type MessageRole = 'user' | 'model' | 'event';

const MAX_MESSAGES = 80;
const FRAME_INTERVAL_MS = 1000;
const MAX_FRAME_WIDTH = 1280;
const MAX_FRAME_HEIGHT = 720;
const JPEG_QUALITY = 0.75;

function element<T extends HTMLElement>(selector: string): T {
  const value = document.querySelector<T>(selector);
  if (!value) throw new Error(`Missing required element: ${selector}`);
  return value;
}

class LiveCommentatorApp {
  private readonly connectionStatus =
    element<HTMLSpanElement>('#connection-status');
  private readonly agentStatus = element<HTMLSpanElement>('#agent-status');
  private readonly visualBadge = element<HTMLSpanElement>('#visual-badge');
  private readonly previewVideo = element<HTMLVideoElement>('#preview-video');
  private readonly previewEmpty = element<HTMLDivElement>('#preview-empty');
  private readonly captureOverlay =
    element<HTMLDivElement>('#capture-overlay');
  private readonly captureLabel = element<HTMLSpanElement>('#capture-label');
  private readonly messages = element<HTMLDivElement>('#messages');
  private readonly conversationEmpty =
    element<HTMLDivElement>('#conversation-empty');
  private readonly messageForm = element<HTMLFormElement>('#message-form');
  private readonly messageInput =
    element<HTMLTextAreaElement>('#message-input');
  private readonly sendButton = element<HTMLButtonElement>('#send-message');
  private readonly microphoneButton =
    element<HTMLButtonElement>('#microphone-toggle');
  private readonly microphoneDetail =
    element<HTMLElement>('#microphone-detail');
  private readonly cameraButton =
    element<HTMLButtonElement>('#camera-toggle');
  private readonly cameraDetail = element<HTMLElement>('#camera-detail');
  private readonly screenButton =
    element<HTMLButtonElement>('#screen-toggle');
  private readonly screenDetail = element<HTMLElement>('#screen-detail');
  private readonly chattiness =
    element<HTMLInputElement>('#chattiness');
  private readonly chattinessValue =
    element<HTMLOutputElement>('#chattiness-value');
  private readonly liveModel = element<HTMLSelectElement>('#live-model');
  private readonly applySettings =
    element<HTMLButtonElement>('#apply-settings');
  private readonly resetButton =
    element<HTMLButtonElement>('#reset-session');
  private readonly frameCanvas =
    element<HTMLCanvasElement>('#frame-canvas');
  private readonly errorBanner = element<HTMLDivElement>('#error-banner');
  private readonly errorTitle = element<HTMLElement>('#error-title');
  private readonly errorMessage = element<HTMLElement>('#error-message');

  private readonly player = new PcmPlayer();
  private readonly websocketUrl: string;
  private socket: WebSocket | null = null;
  private intentionalClose = false;
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private connectionState: ConnectionState = 'connecting';
  private agentState: AgentState = 'ready';
  private microphoneStream: MediaStream | null = null;
  private microphoneContext: AudioContext | null = null;
  private microphoneSource: MediaStreamAudioSourceNode | null = null;
  private microphoneWorklet: AudioWorkletNode | null = null;
  private visualStream: MediaStream | null = null;
  private visualSource: VisualSource = 'none';
  private frameTimer: number | null = null;
  private frameCapturePending = false;
  private modelMessage: HTMLDivElement | null = null;
  private modelTranscript = '';
  private resetConfirmTimer: number | null = null;
  private appliedLiveModel: LiveModelId = DEFAULT_LIVE_MODEL;
  private pendingLiveModel: LiveModelId | null = null;

  constructor() {
    this.websocketUrl = resolveWebSocketUrl(window.location, window.location.search);
    this.bindEvents();
    this.renderConnectionState();
    this.renderAgentState();
    this.connect();
  }

  private bindEvents(): void {
    this.messageForm.addEventListener('submit', (event) => {
      event.preventDefault();
      this.sendText();
    });
    this.messageInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        this.sendText();
      }
    });
    this.messageInput.addEventListener('input', () => {
      this.messageInput.style.height = 'auto';
      this.messageInput.style.height =
        `${Math.min(this.messageInput.scrollHeight, 136)}px`;
    });

    this.microphoneButton.addEventListener('click', () => {
      void this.player.unlock();
      void (this.microphoneStream ? this.stopMicrophone() : this.startMicrophone());
    });
    this.cameraButton.addEventListener('click', () => {
      void this.player.unlock();
      void (this.visualSource === 'camera'
        ? this.stopVisualCapture()
        : this.startCamera());
    });
    this.screenButton.addEventListener('click', () => {
      void this.player.unlock();
      void (this.visualSource === 'screen'
        ? this.stopVisualCapture()
        : this.startScreen());
    });
    element<HTMLButtonElement>('#empty-camera').addEventListener('click', () => {
      void this.startCamera();
    });
    element<HTMLButtonElement>('#empty-screen').addEventListener('click', () => {
      void this.startScreen();
    });

    this.chattiness.addEventListener('input', () => {
      this.chattinessValue.value = Number(this.chattiness.value).toLocaleString(
        'pt-BR',
        {minimumFractionDigits: 1, maximumFractionDigits: 1},
      );
    });
    this.applySettings.addEventListener('click', () => {
      const value = Number(this.chattiness.value);
      const selectedModel = this.selectedLiveModel();
      const modelChanged = selectedModel !== this.appliedLiveModel;
      if (this.send(configMessage(value, selectedModel))) {
        this.pendingLiveModel = selectedModel;
        this.player.flush();
        this.finalizeModelMessage();
        this.setAgentState('resetting');
        if (modelChanged) {
          this.clearConversation();
          this.addMessage(
            'event',
            `Modelo alterado para ${this.liveModel.selectedOptions[0]?.text ?? selectedModel}.`,
          );
        } else {
          this.addMessage(
            'event',
            `Proatividade alterada para ${value.toFixed(1)}.`,
          );
        }
      }
    });
    this.resetButton.addEventListener('click', () => this.confirmOrReset());
    element<HTMLButtonElement>('#clear-conversation').addEventListener(
      'click',
      () => this.clearConversation(),
    );
    element<HTMLButtonElement>('#dismiss-error').addEventListener('click', () => {
      this.errorBanner.hidden = true;
    });

    window.addEventListener('beforeunload', () => this.cleanup());
    document.addEventListener(
      'pointerdown',
      () => {
        void this.player.unlock();
      },
      {once: true},
    );
  }

  private connect(): void {
    if (this.intentionalClose) return;
    this.setConnectionState(this.reconnectAttempt ? 'reconnecting' : 'connecting');
    try {
      this.socket = new WebSocket(this.websocketUrl);
    } catch (error) {
      this.showError('WebSocket inválido', this.errorText(error));
      this.scheduleReconnect();
      return;
    }

    this.socket.addEventListener('open', () => {
      this.reconnectAttempt = 0;
      this.setConnectionState('connected');
      this.setAgentState(this.derivedIdleState());
      const selectedModel = this.selectedLiveModel();
      this.pendingLiveModel = selectedModel;
      this.send(configMessage(Number(this.chattiness.value), selectedModel));
    });
    this.socket.addEventListener('message', (event) => {
      if (typeof event.data !== 'string') return;
      this.handleServerMessage(event.data);
    });
    this.socket.addEventListener('error', () => {
      this.showError(
        'Falha de conexão',
        `Não foi possível conversar com ${this.websocketUrl}. O app tentará novamente.`,
      );
    });
    this.socket.addEventListener('close', () => {
      this.player.flush();
      this.finalizeModelMessage();
      this.socket = null;
      if (!this.intentionalClose) this.scheduleReconnect();
    });
  }

  private scheduleReconnect(): void {
    if (this.intentionalClose || this.reconnectTimer !== null) return;
    this.setConnectionState('reconnecting');
    const baseDelay = Math.min(10000, 500 * 2 ** this.reconnectAttempt);
    const jitter = Math.round(Math.random() * 250);
    this.reconnectAttempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, baseDelay + jitter);
  }

  private handleServerMessage(raw: string): void {
    let message: ProcessorMessage;
    try {
      message = parseServerMessage(raw);
    } catch (error) {
      this.showError('Mensagem inválida do servidor', this.errorText(error));
      return;
    }

    const mimetype =
      message.mimetype ?? message.part?.inline_data?.mime_type ?? '';
    if (mimetype.startsWith('audio/')) {
      const data = message.part?.inline_data?.data;
      if (!data) return;
      try {
        this.player.enqueue(data, mimetype);
        this.setAgentState('speaking');
      } catch (error) {
        this.showError('Áudio inválido', this.errorText(error));
      }
      return;
    }

    if (
      mimetype.startsWith('text/') &&
      message.substream_name === 'output_transcription'
    ) {
      const text = message.part?.text ?? '';
      if (text) this.appendModelTranscript(text);
      return;
    }

    if (mimetype === 'application/x-state') {
      const metadata = message.metadata ?? {};
      if (metadata.interrupted === true) {
        this.player.flush();
        this.finalizeModelMessage();
        this.addMessage('event', 'O comentário foi interrompido.');
        this.setAgentState('interrupted');
        window.setTimeout(
          () => this.setAgentState(this.derivedIdleState()),
          260,
        );
      }
      if (metadata.generation_complete === true) {
        this.finalizeModelMessage();
        this.setAgentState(this.derivedIdleState());
      }
      if (metadata.health_check === true) {
        if (this.pendingLiveModel) {
          this.appliedLiveModel = this.pendingLiveModel;
          this.pendingLiveModel = null;
        }
        this.setConnectionState('connected');
        if (this.agentState === 'resetting') {
          this.setAgentState(this.derivedIdleState());
        }
      }
      if (metadata.error === 'pipeline_configuration_failed') {
        this.pendingLiveModel = null;
        this.liveModel.value = this.appliedLiveModel;
        this.player.flush();
        this.finalizeModelMessage();
        this.showError(
          'Falha ao iniciar o modelo',
          'A configuração anterior foi restaurada. Consulte o arquivo mais recente na pasta logs para ver os detalhes técnicos.',
        );
      }
    }
  }

  private selectedLiveModel(): LiveModelId {
    if (!isLiveModelId(this.liveModel.value)) {
      this.liveModel.value = this.appliedLiveModel;
      return this.appliedLiveModel;
    }
    return this.liveModel.value;
  }

  private async startMicrophone(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: false,
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const context = new AudioContext({latencyHint: 'interactive'});
      await context.audioWorklet.addModule('/pcm-capture-worklet.js');
      const source = context.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(context, 'pcm-capture');
      const silentGain = context.createGain();
      silentGain.gain.value = 0;
      source.connect(worklet);
      worklet.connect(silentGain);
      silentGain.connect(context.destination);

      const resampler = new StreamingResampler(
        context.sampleRate,
        MICROPHONE_SAMPLE_RATE,
      );
      worklet.port.addEventListener('message', (event: MessageEvent<unknown>) => {
        if (!(event.data instanceof Float32Array)) return;
        const samples = resampler.process(event.data);
        if (samples.length === 0) return;
        const pcm = floatToPcm16(samples);
        const bytes = new Uint8Array(
          pcm.buffer,
          pcm.byteOffset,
          pcm.byteLength,
        );
        this.send(
          audioMessage(bytesToBase64(bytes), MICROPHONE_SAMPLE_RATE),
          false,
        );
      });
      worklet.port.start();

      this.microphoneStream = stream;
      this.microphoneContext = context;
      this.microphoneSource = source;
      this.microphoneWorklet = worklet;
      stream.getAudioTracks()[0]?.addEventListener(
        'ended',
        () => void this.stopMicrophone(),
        {once: true},
      );
      this.microphoneButton.setAttribute('aria-pressed', 'true');
      this.microphoneDetail.textContent = 'Ouvindo';
      this.setAgentState('listening');
    } catch (error) {
      await this.stopMicrophone(false);
      this.showError(
        'Microfone indisponível',
        `${this.errorText(error)} Verifique a permissão do navegador e tente novamente.`,
      );
    }
  }

  private async stopMicrophone(sendSignal = true): Promise<void> {
    this.microphoneWorklet?.disconnect();
    this.microphoneSource?.disconnect();
    this.microphoneStream?.getTracks().forEach((track) => track.stop());
    if (this.microphoneContext && this.microphoneContext.state !== 'closed') {
      await this.microphoneContext.close();
    }
    this.microphoneWorklet = null;
    this.microphoneSource = null;
    this.microphoneStream = null;
    this.microphoneContext = null;
    this.microphoneButton.setAttribute('aria-pressed', 'false');
    this.microphoneDetail.textContent = 'Desligado';
    if (sendSignal) this.send(micOffMessage(), false);
    this.setAgentState(this.derivedIdleState());
  }

  private async startCamera(): Promise<void> {
    await this.stopVisualCapture();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          width: {ideal: 1280},
          height: {ideal: 720},
        },
      });
      this.activateVisualStream(stream, 'camera');
    } catch (error) {
      this.showError(
        'Câmera indisponível',
        `${this.errorText(error)} Verifique a permissão e o dispositivo.`,
      );
    }
  }

  private async startScreen(): Promise<void> {
    await this.stopVisualCapture();
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        audio: false,
        video: true,
      });
      this.activateVisualStream(stream, 'screen');
    } catch (error) {
      this.showError(
        'Tela não compartilhada',
        `${this.errorText(error)} Selecione uma janela ou tela para continuar.`,
      );
    }
  }

  private activateVisualStream(
    stream: MediaStream,
    source: Exclude<VisualSource, 'none'>,
  ): void {
    this.visualStream = stream;
    this.visualSource = source;
    this.previewVideo.srcObject = stream;
    this.previewVideo.classList.add('visible');
    this.previewVideo.classList.toggle('camera-preview', source === 'camera');
    this.previewEmpty.hidden = true;
    this.captureOverlay.hidden = false;
    this.captureLabel.textContent = source === 'camera' ? 'Câmera ativa' : 'Tela ativa';
    this.visualBadge.textContent = source === 'camera' ? 'Câmera' : 'Tela';
    this.cameraButton.setAttribute(
      'aria-pressed',
      source === 'camera' ? 'true' : 'false',
    );
    this.screenButton.setAttribute(
      'aria-pressed',
      source === 'screen' ? 'true' : 'false',
    );
    this.cameraDetail.textContent = source === 'camera' ? 'Capturando' : 'Desligada';
    this.screenDetail.textContent =
      source === 'screen' ? 'Compartilhando' : 'Não compartilhada';
    stream.getVideoTracks()[0]?.addEventListener(
      'ended',
      () => void this.stopVisualCapture(),
      {once: true},
    );
    this.frameTimer = window.setInterval(
      () => void this.captureFrame(),
      FRAME_INTERVAL_MS,
    );
    void this.captureFrame();
    this.setAgentState('observing');
  }

  private async stopVisualCapture(): Promise<void> {
    if (this.frameTimer !== null) {
      window.clearInterval(this.frameTimer);
      this.frameTimer = null;
    }
    this.visualStream?.getTracks().forEach((track) => track.stop());
    this.visualStream = null;
    this.visualSource = 'none';
    this.previewVideo.srcObject = null;
    this.previewVideo.classList.remove('visible', 'camera-preview');
    this.previewEmpty.hidden = false;
    this.captureOverlay.hidden = true;
    this.visualBadge.textContent = 'Sem captura';
    this.cameraButton.setAttribute('aria-pressed', 'false');
    this.screenButton.setAttribute('aria-pressed', 'false');
    this.cameraDetail.textContent = 'Desligada';
    this.screenDetail.textContent = 'Não compartilhada';
    this.setAgentState(this.derivedIdleState());
  }

  private async captureFrame(): Promise<void> {
    if (
      this.frameCapturePending ||
      !this.visualStream ||
      !this.isSocketOpen() ||
      this.previewVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
    ) {
      return;
    }
    this.frameCapturePending = true;
    try {
      const sourceWidth = this.previewVideo.videoWidth;
      const sourceHeight = this.previewVideo.videoHeight;
      if (!sourceWidth || !sourceHeight) return;
      const scale = Math.min(
        1,
        MAX_FRAME_WIDTH / sourceWidth,
        MAX_FRAME_HEIGHT / sourceHeight,
      );
      this.frameCanvas.width = Math.round(sourceWidth * scale);
      this.frameCanvas.height = Math.round(sourceHeight * scale);
      const context = this.frameCanvas.getContext('2d');
      if (!context) throw new Error('Canvas 2D is not available.');
      context.drawImage(
        this.previewVideo,
        0,
        0,
        this.frameCanvas.width,
        this.frameCanvas.height,
      );
      const blob = await new Promise<Blob | null>((resolve) => {
        this.frameCanvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY);
      });
      if (!blob || !this.isSocketOpen()) return;
      const bytes = new Uint8Array(await blob.arrayBuffer());
      this.send(imageMessage(bytesToBase64(bytes)), false);
    } catch (error) {
      this.showError('Falha ao capturar frame', this.errorText(error));
    } finally {
      this.frameCapturePending = false;
    }
  }

  private sendText(): void {
    const text = this.messageInput.value.trim();
    if (!text) return;
    if (!this.send(textMessage(text))) return;
    this.addMessage('user', text);
    this.messageInput.value = '';
    this.messageInput.style.height = 'auto';
    this.setAgentState('thinking');
  }

  private send(message: ProcessorMessage, showDisconnectedError = true): boolean {
    if (!this.isSocketOpen()) {
      if (showDisconnectedError) {
        this.showError(
          'Servidor desconectado',
          'Aguarde a reconexão antes de enviar uma nova mensagem.',
        );
      }
      return false;
    }
    this.socket?.send(JSON.stringify(message));
    return true;
  }

  private isSocketOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  private appendModelTranscript(text: string): void {
    this.modelTranscript += text;
    if (!this.modelMessage) {
      this.modelMessage = this.addMessage('model', '', true);
    }
    this.modelMessage.textContent = this.modelTranscript;
    this.scrollConversation();
  }

  private finalizeModelMessage(): void {
    this.modelMessage?.classList.remove('pending');
    this.modelMessage = null;
    this.modelTranscript = '';
  }

  private addMessage(
    role: MessageRole,
    text: string,
    pending = false,
  ): HTMLDivElement {
    this.conversationEmpty.hidden = true;
    const message = document.createElement('div');
    message.className = `message${pending ? ' pending' : ''}`;
    message.dataset.role = role;
    message.textContent = text;
    this.messages.append(message);
    while (this.messages.querySelectorAll('.message').length > MAX_MESSAGES) {
      this.messages.querySelector('.message')?.remove();
    }
    this.scrollConversation();
    return message;
  }

  private scrollConversation(): void {
    const distanceFromBottom =
      this.messages.scrollHeight -
      this.messages.scrollTop -
      this.messages.clientHeight;
    if (distanceFromBottom < 160) {
      this.messages.scrollTop = this.messages.scrollHeight;
    }
  }

  private clearConversation(): void {
    this.messages.querySelectorAll('.message').forEach((message) => message.remove());
    this.finalizeModelMessage();
    this.conversationEmpty.hidden = false;
  }

  private confirmOrReset(): void {
    if (this.resetButton.dataset.confirming !== 'true') {
      this.resetButton.dataset.confirming = 'true';
      this.resetButton.textContent = 'Confirmar reset';
      this.resetConfirmTimer = window.setTimeout(
        () => this.clearResetConfirmation(),
        3500,
      );
      return;
    }
    this.clearResetConfirmation();
    if (!this.send(resetMessage())) return;
    this.player.flush();
    this.clearConversation();
    this.addMessage('event', 'Sessão reiniciada.');
    this.setAgentState('resetting');
  }

  private clearResetConfirmation(): void {
    if (this.resetConfirmTimer !== null) {
      window.clearTimeout(this.resetConfirmTimer);
      this.resetConfirmTimer = null;
    }
    delete this.resetButton.dataset.confirming;
    this.resetButton.textContent = 'Resetar sessão';
  }

  private setConnectionState(state: ConnectionState): void {
    this.connectionState = state;
    this.renderConnectionState();
  }

  private renderConnectionState(): void {
    const labels: Record<ConnectionState, string> = {
      connecting: 'Conectando',
      connected: 'Conectado',
      reconnecting: 'Reconectando',
      disconnected: 'Desconectado',
    };
    const tones: Record<ConnectionState, string> = {
      connecting: 'pending',
      connected: 'success',
      reconnecting: 'pending',
      disconnected: 'danger',
    };
    this.connectionStatus.lastChild!.textContent = ` ${labels[this.connectionState]}`;
    this.connectionStatus.dataset.tone = tones[this.connectionState];
    this.connectionStatus.dataset.pulse =
      this.connectionState === 'connecting' ||
      this.connectionState === 'reconnecting'
        ? 'true'
        : 'false';
    const connected = this.connectionState === 'connected';
    this.messageInput.disabled = !connected;
    this.sendButton.disabled = !connected;
    this.applySettings.disabled = !connected;
    this.liveModel.disabled = !connected;
  }

  private setAgentState(state: AgentState): void {
    this.agentState = state;
    this.renderAgentState();
  }

  private renderAgentState(): void {
    const labels: Record<AgentState, string> = {
      ready: 'Pronto',
      listening: 'Ouvindo',
      observing: 'Observando',
      thinking: 'Pensando',
      speaking: 'Falando',
      interrupted: 'Interrompido',
      resetting: 'Reiniciando',
      error: 'Erro',
    };
    const tone =
      this.agentState === 'error'
        ? 'danger'
        : this.agentState === 'ready'
          ? 'neutral'
          : 'active';
    this.agentStatus.lastChild!.textContent = ` ${labels[this.agentState]}`;
    this.agentStatus.dataset.tone = tone;
    this.agentStatus.dataset.pulse =
      ['listening', 'thinking', 'speaking', 'resetting'].includes(this.agentState)
        ? 'true'
        : 'false';
  }

  private derivedIdleState(): AgentState {
    if (this.microphoneStream) return 'listening';
    if (this.visualSource !== 'none') return 'observing';
    return 'ready';
  }

  private showError(title: string, message: string): void {
    this.errorTitle.textContent = title;
    this.errorMessage.textContent = message;
    this.errorBanner.hidden = false;
    if (this.connectionState === 'connected') this.setAgentState('error');
  }

  private errorText(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }

  private cleanup(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    if (this.frameTimer !== null) window.clearInterval(this.frameTimer);
    this.visualStream?.getTracks().forEach((track) => track.stop());
    this.microphoneStream?.getTracks().forEach((track) => track.stop());
    this.socket?.close();
    this.player.flush();
    void this.microphoneContext?.close();
    void this.player.close();
    this.setConnectionState('disconnected');
  }
}

new LiveCommentatorApp();
