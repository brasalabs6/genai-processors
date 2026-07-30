import './styles.css';

import {controlApi} from './api';
import {PcmPlayer} from './audio';
import {MediaController} from './media';
import {
  parseServerMessage,
  resolveWebSocketUrl,
  textMessage,
} from './protocol';
import type {ProcessorMessage} from './protocol';
import type {
  AgentConfig,
  Capabilities,
  ConfigSnapshot,
  MetricsSnapshot,
  SessionSnapshot,
} from './types';

function element<T extends HTMLElement>(selector: string): T {
  const found = document.querySelector<T>(selector);
  if (!found) throw new Error(`Elemento obrigatório ausente: ${selector}`);
  return found;
}

function numberOrNull(input: HTMLInputElement): number | null {
  return input.value === '' ? null : Number(input.value);
}

class LeonidasApp {
  private capabilities: Capabilities | null = null;
  private config: ConfigSnapshot | null = null;
  private session: SessionSnapshot = {
    state: 'stopped', session_id: null, media_connected: false,
    started_at: null, last_error: null,
  };
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private intentionalClose = false;
  private readonly player = new PcmPlayer();
  private readonly media: MediaController;
  private logLines: string[] = [];
  private logsPaused = false;
  private eventSource: EventSource | null = null;
  private durationTimer: number | null = null;

  private readonly model = element<HTMLSelectElement>('#model');
  private readonly voice = element<HTMLSelectElement>('#voice');
  private readonly preset = element<HTMLSelectElement>('#preset');
  private readonly objective = element<HTMLTextAreaElement>('#objective');
  private readonly chattiness = element<HTMLInputElement>('#chattiness');
  private readonly preview = element<HTMLVideoElement>('#preview');

  constructor() {
    this.media = new MediaController(
      this.preview,
      (message) => this.send(message),
      () => this.session.state === 'running' && this.socket?.readyState === WebSocket.OPEN,
      () => this.config?.draft.media ?? {
        frame_interval_ms: 1000, max_width: 1280, max_height: 720,
        jpeg_quality: 0.75, model_resolution: 'medium',
      },
      (state) => this.renderCapture(state.microphone, state.visual),
    );
    this.bind();
  }

  async init(): Promise<void> {
    try {
      [this.capabilities, this.config, this.session] = await Promise.all([
        controlApi.capabilities(), controlApi.config(), controlApi.session(),
      ]);
      this.setStatus('#rest-status', 'API online', 'ok');
      this.renderCapabilities();
      this.renderConfig();
      this.renderSession();
      this.connectWebSocket();
      this.connectLogs();
      await this.refreshLogFiles();
      await this.refreshMetrics();
      window.setInterval(() => void this.refreshMetrics(), 2000);
    } catch (error) {
      this.setStatus('#rest-status', 'API offline', 'error');
      this.showError('Falha ao iniciar', this.errorText(error));
    }
  }

  private bind(): void {
    element('#dismiss-error').addEventListener('click', () => {
      element('#error-banner').hidden = true;
    });
    element('#start-session').addEventListener('click', () => void this.start());
    element('#stop-session').addEventListener('click', () => void this.stop());
    element('#apply-config').addEventListener('click', () => void this.apply());
    element('#microphone').addEventListener('click', () => this.guard(() => this.media.toggleMicrophone()));
    element('#camera').addEventListener('click', () => this.guard(() => this.media.toggleCamera()));
    element('#screen').addEventListener('click', () => this.guard(() => this.media.toggleScreen()));
    element('#clear-conversation').addEventListener('click', () => {
      element('#conversation').innerHTML = '<div class="empty-copy">Conversa limpa.</div>';
    });
    element<HTMLFormElement>('#message-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const input = element<HTMLTextAreaElement>('#message');
      const text = input.value.trim();
      if (!text || this.session.state !== 'running') return;
      this.send(textMessage(text));
      this.addMessage('user', text);
      input.value = '';
    });
    element<HTMLTextAreaElement>('#message').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        element<HTMLFormElement>('#message-form').requestSubmit();
      }
    });

    this.model.addEventListener('change', () => void this.updateDraft({model_id: this.model.value}));
    this.voice.addEventListener('change', () => void this.updateDraft({voice_name: this.voice.value || null}));
    this.preset.addEventListener('change', () => void this.updateDraft({performance_preset: this.preset.value}));
    this.chattiness.addEventListener('change', () => void this.updateDraft({chattiness: Number(this.chattiness.value)}));
    this.chattiness.addEventListener('input', () => {
      element<HTMLOutputElement>('#chattiness-value').value = `${Math.round(Number(this.chattiness.value) * 100)}%`;
    });
    this.objective.addEventListener('input', () => {
      element('#objective-count').textContent = String(this.objective.value.length);
    });
    this.objective.addEventListener('change', () => void this.updateDraft({objective: this.objective.value}));
    element('#preview-voice').addEventListener('click', () => void this.previewVoice());

    this.bindAdvanced();
    element('#pause-logs').addEventListener('click', () => {
      this.logsPaused = !this.logsPaused;
      element('#pause-logs').textContent = this.logsPaused ? 'Retomar' : 'Pausar';
    });
    element('#clear-logs').addEventListener('click', () => {this.logLines = []; this.renderLogs();});
    element('#log-level').addEventListener('change', () => this.renderLogs());
    element('#log-search').addEventListener('input', () => this.renderLogs());
    element('#log-file').addEventListener('change', () => void this.loadSelectedLog());
    window.addEventListener('beforeunload', () => {
      this.intentionalClose = true;
      this.socket?.close();
      this.eventSource?.close();
      void this.media.close();
      void this.player.close();
    });
  }

  private bindAdvanced(): void {
    const mediaFields: Array<[string, keyof AgentConfig['media'], (input: HTMLInputElement | HTMLSelectElement) => unknown]> = [
      ['#frame-interval', 'frame_interval_ms', (input) => Number(input.value)],
      ['#frame-width', 'max_width', (input) => Number(input.value)],
      ['#frame-height', 'max_height', (input) => Number(input.value)],
      ['#jpeg-quality', 'jpeg_quality', (input) => Number(input.value)],
      ['#model-resolution', 'model_resolution', (input) => input.value],
    ];
    for (const [selector, key, read] of mediaFields) {
      element<HTMLInputElement | HTMLSelectElement>(selector).addEventListener('change', (event) => {
        void this.updateDraft({media: {[key]: read(event.currentTarget as HTMLInputElement)}}).then(() => this.media.refreshFrameSchedule());
      });
    }
    const generation = () => ({
      temperature: numberOrNull(element('#temperature')),
      thinking_level: element<HTMLSelectElement>('#thinking-level').value || null,
      thinking_budget: numberOrNull(element('#thinking-budget')),
    });
    for (const selector of ['#temperature', '#thinking-level', '#thinking-budget']) {
      element(selector).addEventListener('change', () => void this.updateDraft({generation: generation()}));
    }
    const vad = () => ({
      start_sensitivity: element<HTMLSelectElement>('#vad-start').value || null,
      end_sensitivity: element<HTMLSelectElement>('#vad-end').value || null,
      prefix_padding_ms: numberOrNull(element('#vad-padding')),
      silence_duration_ms: numberOrNull(element('#vad-silence')),
    });
    for (const selector of ['#vad-start', '#vad-end', '#vad-padding', '#vad-silence']) {
      element(selector).addEventListener('change', () => void this.updateDraft({vad: vad()}));
    }
  }

  private async updateDraft(updates: Record<string, unknown>): Promise<void> {
    if (!this.config) return;
    try {
      this.config = await controlApi.updateDraft(this.config.revision, updates);
      this.renderConfig();
    } catch (error) {
      if ((error as {code?: string}).code === 'revision_conflict') {
        this.config = await controlApi.config();
        this.renderConfig();
      }
      this.showError('Configuração não salva', this.errorText(error));
    }
  }

  private async apply(): Promise<void> {
    if (!this.config?.dirty_fields.length) return;
    if (this.session.state === 'running' && !window.confirm('Aplicar e reiniciar a sessão agora?')) return;
    try {
      await this.player.unlock();
      this.config = await controlApi.apply();
      this.session = await controlApi.session();
      this.renderConfig();
      this.renderSession();
    } catch (error) { this.showError('Falha ao aplicar', this.errorText(error)); }
  }

  private async start(): Promise<void> {
    try {
      await this.player.unlock();
      this.session = await controlApi.start();
      this.renderSession();
    } catch (error) { this.showError('Sessão não iniciada', this.errorText(error)); }
  }

  private async stop(): Promise<void> {
    try {
      this.session = await controlApi.stop();
      this.player.flush();
      this.renderSession();
    } catch (error) { this.showError('Falha ao parar', this.errorText(error)); }
  }

  private connectWebSocket(): void {
    this.setStatus('#ws-status', 'Conectando', 'neutral');
    const socket = new WebSocket(resolveWebSocketUrl(window.location, window.location.search));
    this.socket = socket;
    socket.addEventListener('open', () => {
      this.reconnectAttempt = 0;
      this.setStatus('#ws-status', 'WebSocket online', 'ok');
      this.renderSession();
    });
    socket.addEventListener('message', (event) => this.handleMessage(String(event.data)));
    socket.addEventListener('error', () => this.setStatus('#ws-status', 'Erro WebSocket', 'error'));
    socket.addEventListener('close', () => {
      this.setStatus('#ws-status', 'WebSocket offline', 'error');
      this.player.flush();
      if (!this.intentionalClose) this.scheduleReconnect();
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    const delays = [1000, 2000, 4000, 8000, 15000];
    const base = delays[Math.min(this.reconnectAttempt, delays.length - 1)] ?? 15000;
    this.reconnectAttempt += 1;
    this.setStatus('#ws-status', `Reconectando em ${Math.round(base / 1000)}s`, 'warn');
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connectWebSocket();
    }, base + Math.random() * 300);
  }

  private handleMessage(raw: string): void {
    try {
      const message = parseServerMessage(raw);
      const metadata = message.metadata ?? {};
      if (message.mimetype === 'application/x-state') {
        const state = metadata.state;
        if (typeof state === 'string') {
          this.session = {...this.session, ...metadata, state} as SessionSnapshot;
          this.renderSession();
        }
        if (metadata.agent_state === 'interrupted' || state === 'stopped') {
          const started = performance.now();
          this.player.flush();
          this.send({mimetype: 'application/x-client-metric', metadata: {name: 'playback_flush_ms', value: performance.now() - started}});
        }
        return;
      }
      const inline = message.part?.inline_data;
      if (inline?.data && inline.mime_type?.startsWith('audio/')) {
        this.player.enqueue(inline.data, inline.mime_type);
        return;
      }
      const text = message.part?.text;
      if (text) this.addMessage(message.role === 'user' ? 'user' : 'model', text);
    } catch (error) { this.showError('Mensagem inválida', this.errorText(error)); }
  }

  private send(message: ProcessorMessage): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify(message));
  }

  private renderCapabilities(): void {
    if (!this.capabilities) return;
    const models = this.capabilities.pipelines.flatMap((pipeline) => pipeline.models);
    this.model.innerHTML = models.map((item) => `<option value="${item.id}">${item.label}</option>`).join('');
    this.voice.innerHTML = '<option value="">Automática</option>' + this.capabilities.voices.map((voice) => `<option>${voice}</option>`).join('');
  }

  private renderConfig(): void {
    if (!this.config || !this.capabilities) return;
    const draft = this.config.draft;
    this.model.value = draft.model_id;
    this.voice.value = draft.voice_name ?? '';
    this.preset.value = draft.performance_preset;
    this.objective.value = draft.objective;
    element('#objective-count').textContent = String(draft.objective.length);
    this.chattiness.value = String(draft.chattiness);
    element<HTMLOutputElement>('#chattiness-value').value = `${Math.round(draft.chattiness * 100)}%`;
    element<HTMLInputElement>('#frame-interval').value = String(draft.media.frame_interval_ms);
    element<HTMLInputElement>('#frame-width').value = String(draft.media.max_width);
    element<HTMLInputElement>('#frame-height').value = String(draft.media.max_height);
    element<HTMLInputElement>('#jpeg-quality').value = String(draft.media.jpeg_quality);
    element<HTMLSelectElement>('#model-resolution').value = draft.media.model_resolution;
    element<HTMLInputElement>('#temperature').value = draft.generation.temperature?.toString() ?? '';
    element<HTMLSelectElement>('#thinking-level').value = draft.generation.thinking_level ?? '';
    element<HTMLInputElement>('#thinking-budget').value = draft.generation.thinking_budget?.toString() ?? '';
    element<HTMLSelectElement>('#vad-start').value = draft.vad.start_sensitivity ?? '';
    element<HTMLSelectElement>('#vad-end').value = draft.vad.end_sensitivity ?? '';
    element<HTMLInputElement>('#vad-padding').value = draft.vad.prefix_padding_ms?.toString() ?? '';
    element<HTMLInputElement>('#vad-silence').value = draft.vad.silence_duration_ms?.toString() ?? '';
    const model = this.capabilities.pipelines.flatMap((pipeline) => pipeline.models).find((item) => item.id === draft.model_id);
    element('#thinking-level-wrap').hidden = model?.thinking_field !== 'thinking_level';
    element('#thinking-budget-wrap').hidden = model?.thinking_field !== 'thinking_budget';
    const dirty = this.config.dirty_fields.length;
    element('#draft-status').textContent = dirty ? `Rascunho · ${dirty} alteração${dirty > 1 ? 'ões' : ''}` : 'Ativa';
    element<HTMLButtonElement>('#apply-config').disabled = dirty === 0;
  }

  private renderSession(): void {
    const labels = {stopped: 'Parado', starting: 'Iniciando', running: 'Em sessão', stopping: 'Parando', error: 'Erro'};
    const tone = this.session.state === 'running' ? 'ok' : this.session.state === 'error' ? 'error' : this.session.state === 'starting' || this.session.state === 'stopping' ? 'warn' : 'neutral';
    this.setStatus('#session-status', labels[this.session.state], tone);
    element<HTMLButtonElement>('#start-session').disabled = this.session.state !== 'stopped' || this.socket?.readyState !== WebSocket.OPEN;
    element<HTMLButtonElement>('#stop-session').disabled = this.session.state === 'stopped' || this.session.state === 'stopping';
    element<HTMLTextAreaElement>('#message').disabled = this.session.state !== 'running';
    if (this.session.state === 'stopped' || this.session.state === 'error') this.player.flush();
    if (this.durationTimer !== null) window.clearInterval(this.durationTimer);
    if (this.session.started_at) {
      this.durationTimer = window.setInterval(() => this.renderDuration(), 1000);
      this.renderDuration();
    } else element('#session-duration').textContent = '00:00';
  }

  private renderDuration(): void {
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - (this.session.started_at ?? Date.now() / 1000)));
    element('#session-duration').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  private renderCapture(microphone: boolean, visual: 'none' | 'camera' | 'screen'): void {
    const mic = element<HTMLButtonElement>('#microphone');
    mic.setAttribute('aria-pressed', String(microphone));
    mic.querySelector('small')!.textContent = microphone ? 'Ouvindo' : 'Desligado';
    for (const [selector, active] of [['#camera', visual === 'camera'], ['#screen', visual === 'screen']] as const) {
      const button = element<HTMLButtonElement>(selector);
      button.setAttribute('aria-pressed', String(active));
      button.querySelector('small')!.textContent = active ? 'Ativa' : 'Desligada';
    }
    element('#preview-empty').hidden = visual !== 'none';
    element('#capture-state').textContent = [microphone ? 'Mic' : '', visual === 'camera' ? 'Câmera' : visual === 'screen' ? 'Tela' : ''].filter(Boolean).join(' + ') || 'Sem captura';
  }

  private async previewVoice(): Promise<void> {
    if (!this.voice.value) return this.showError('Escolha uma voz', 'A voz Automática não possui prévia fixa.');
    const button = element<HTMLButtonElement>('#preview-voice');
    button.disabled = true; button.textContent = 'Gerando…';
    try {
      const blob = await controlApi.previewVoice(this.model.value, this.voice.value);
      await new Audio(URL.createObjectURL(blob)).play();
    } catch (error) { this.showError('Prévia indisponível', this.errorText(error)); }
    finally {button.disabled = false; button.textContent = 'Ouvir';}
  }

  private async refreshMetrics(): Promise<void> {
    try { this.renderMetrics(await controlApi.metrics()); } catch { /* status API covers it */ }
  }

  private renderMetrics(snapshot: MetricsSnapshot): void {
    const ttfa = snapshot.metrics.ttfa_ms;
    const startup = snapshot.metrics.pipeline_startup_ms;
    const format = (value?: number) => value === undefined ? '—' : `${Math.round(value)} ms`;
    element('#metric-current').textContent = format(ttfa?.current);
    element('#metric-p50').textContent = format(ttfa?.p50);
    element('#metric-p95').textContent = format(ttfa?.p95);
    element('#metric-startup').textContent = format(startup?.current);
    element('#frames-count').textContent = String(snapshot.counters.frames_received ?? 0);
    element('#audio-in-count').textContent = String(snapshot.counters.audio_chunks_received ?? 0);
    element('#audio-out-count').textContent = String(snapshot.counters.audio_chunks_sent ?? 0);
  }

  private connectLogs(): void {
    this.eventSource?.close();
    const source = new EventSource('/api/v1/logs/stream');
    this.eventSource = source;
    source.onmessage = (event) => {
      if (this.logsPaused) return;
      const value = JSON.parse(event.data) as {line: string};
      this.logLines.push(value.line);
      if (this.logLines.length > 2000) this.logLines.splice(0, this.logLines.length - 2000);
      this.renderLogs(true);
    };
  }

  private async refreshLogFiles(): Promise<void> {
    const files = await controlApi.logFiles();
    const select = element<HTMLSelectElement>('#log-file');
    select.innerHTML = '<option value="">Tail ao vivo</option>' + files.files.map((file) => `<option value="${file.id}">${file.id}</option>`).join('');
  }

  private async loadSelectedLog(): Promise<void> {
    const id = element<HTMLSelectElement>('#log-file').value;
    if (!id) {this.logLines = []; this.renderLogs(); return;}
    try {
      this.logLines = (await controlApi.logFile(id)).lines;
      this.renderLogs();
    } catch (error) { this.showError('Log não carregado', this.errorText(error)); }
  }

  private renderLogs(autoScroll = false): void {
    const level = element<HTMLSelectElement>('#log-level').value;
    const search = element<HTMLInputElement>('#log-search').value.toLocaleLowerCase();
    const lines = this.logLines.filter((line) => (!level || line.includes(level)) && (!search || line.toLocaleLowerCase().includes(search)));
    const output = element<HTMLPreElement>('#logs');
    output.textContent = lines.join('\n');
    if (autoScroll) output.scrollTop = output.scrollHeight;
  }

  private addMessage(role: 'user' | 'model', text: string): void {
    const conversation = element('#conversation');
    conversation.querySelector('.empty-copy')?.remove();
    const item = document.createElement('article');
    item.className = `message ${role}`;
    const label = document.createElement('strong'); label.textContent = role === 'user' ? 'Você' : 'Leonidas';
    const content = document.createElement('p'); content.textContent = text;
    item.append(label, content); conversation.append(item);
    while (conversation.children.length > 100) conversation.firstElementChild?.remove();
    conversation.scrollTop = conversation.scrollHeight;
  }

  private setStatus(selector: string, text: string, tone: 'ok' | 'warn' | 'error' | 'neutral'): void {
    const target = element(selector); target.textContent = text; target.className = `status ${tone}`;
  }

  private showError(title: string, detail: string): void {
    element('#error-title').textContent = title;
    element('#error-detail').textContent = detail;
    element('#error-banner').hidden = false;
  }

  private errorText(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }

  private guard(action: () => Promise<void>): void {
    void action().catch((error) => this.showError('Dispositivo indisponível', this.errorText(error)));
  }
}

void new LeonidasApp().init();
