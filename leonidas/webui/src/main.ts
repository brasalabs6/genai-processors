import './styles.css';

import {controlApi} from './api';
import {effectiveConfig, modelsForPipeline, visionForPipeline} from './capabilities';
import {PcmPlayer} from './audio';
import {LogBuffer} from './log-buffer';
import {MediaController} from './media';
import {
  connectionClosePolicy,
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
  ResourceComponent,
  ResourceSnapshot,
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
    started_at: null, last_error: null, last_error_detail: null,
  };
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private intentionalClose = false;
  private readonly player = new PcmPlayer();
  private readonly media: MediaController;
  private readonly logBuffer = new LogBuffer(2000);
  private logsPaused = false;
  private logRenderPending = false;
  private eventSource: EventSource | null = null;
  private durationTimer: number | null = null;
  private metricsTimer: number | null = null;
  private metricsRequestPending = false;
  private audioPlaybackFailed = false;
  private resources: ResourceSnapshot = {
    schema_version: 1,
    overall_state: 'unloaded',
    components: [],
  };

  private readonly model = element<HTMLSelectElement>('#model');
  private readonly pipeline = element<HTMLSelectElement>('#pipeline');
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
      () => this.config ? effectiveConfig(this.config, this.session.state).media : {
        frame_interval_ms: 1000, max_width: 1280, max_height: 720,
        jpeg_quality: 0.75, model_resolution: 'medium',
      },
      (state) => this.renderCapture(state.microphone, state.visual),
    );
    this.bind();
  }

  async init(): Promise<void> {
    try {
      [this.capabilities, this.config, this.session, this.resources] = await Promise.all([
        controlApi.capabilities(), controlApi.config(), controlApi.session(),
        controlApi.resources(),
      ]);
      this.setStatus('#rest-status', 'API online', 'ok');
      this.renderCapabilities();
      this.renderConfig();
      this.renderSession();
      this.renderResources();
      this.connectWebSocket();
      this.connectLogs();
      await this.refreshLogFiles();
      await this.refreshMetrics();
      this.scheduleMetrics();
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

    this.pipeline.addEventListener('change', () => void this.changePipeline());
    this.model.addEventListener('change', () => {
      const updates = this.pipeline.value === 'cascade_local'
        ? {model_id: this.model.value, cascade: {llm_model_id: this.model.value}}
        : {model_id: this.model.value};
      void this.updateDraft(updates);
    });
    this.voice.addEventListener('change', () => {
      const updates = this.pipeline.value === 'cascade_local'
        ? {cascade: {voice_id: this.voice.value}}
        : {voice_name: this.voice.value || null};
      void this.updateDraft(updates);
    });
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
    element('#reasoning-effort').addEventListener('change', () => void this.updateDraft({cascade: {reasoning_effort: element<HTMLSelectElement>('#reasoning-effort').value}}));
    element('#cascade-device').addEventListener('change', () => void this.updateDraft({cascade: {device: element<HTMLSelectElement>('#cascade-device').value}}));

    this.bindAdvanced();
    element('#pause-logs').addEventListener('click', () => {
      this.logsPaused = !this.logsPaused;
      element('#pause-logs').textContent = this.logsPaused ? 'Retomar' : 'Pausar';
    });
    element('#clear-logs').addEventListener('click', () => {
      this.logBuffer.clear();
      this.renderLogs();
    });
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
    document.addEventListener('visibilitychange', () => {
      if (this.metricsTimer !== null) window.clearTimeout(this.metricsTimer);
      this.metricsTimer = null;
      this.scheduleMetrics();
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

  private async changePipeline(): Promise<void> {
    if (!this.capabilities || !this.config) return;
    const id = this.pipeline.value as AgentConfig['pipeline_id'];
    const models = modelsForPipeline(this.capabilities, id);
    const modelId = models[0]?.id;
    if (!modelId) return this.showError('Pipeline indisponível', 'Nenhum modelo compatível foi anunciado pelo backend.');
    if (this.session.state === 'stopped' && !visionForPipeline(this.capabilities, id)) {
      await this.media.stopVisual();
    }
    const updates = id === 'cascade_local'
      ? {
          pipeline_id: id, model_id: modelId, voice_name: null,
          cascade: {llm_model_id: modelId},
        }
      : {pipeline_id: id, model_id: modelId, voice_name: null};
    await this.updateDraft(updates);
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
      this.audioPlaybackFailed = false;
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
      this.setStatus('#ws-status', 'WebSocket online', 'ok');
      this.renderSession();
    });
    socket.addEventListener('message', (event) => this.handleMessage(String(event.data)));
    socket.addEventListener('error', () => this.setStatus('#ws-status', 'Erro WebSocket', 'error'));
    socket.addEventListener('close', (event) => {
      const policy = connectionClosePolicy(event.code, event.reason);
      this.setStatus('#ws-status', policy.label, 'error');
      this.player.flush();
      this.renderSession();
      if (!this.intentionalClose && policy.retry) {
        this.scheduleReconnect(
          policy.label === 'WebSocket offline' ? null : policy.label,
        );
      }
    });
  }

  private scheduleReconnect(context: string | null = null): void {
    if (this.reconnectTimer !== null) return;
    const delays = [1000, 2000, 4000, 8000, 15000];
    const base = delays[Math.min(this.reconnectAttempt, delays.length - 1)] ?? 15000;
    this.reconnectAttempt += 1;
    const seconds = Math.round(base / 1000);
    this.setStatus(
      '#ws-status',
      context ? `${context} · nova tentativa em ${seconds}s` : `Reconectando em ${seconds}s`,
      'warn',
    );
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
        this.reconnectAttempt = 0;
        const state = metadata.state;
        if (typeof state === 'string') {
          this.session = {...this.session, ...metadata, state} as SessionSnapshot;
          this.renderSession();
        }
        const agentState = metadata.agent_state;
        if (typeof agentState === 'string' && state === undefined) {
          const labels: Record<string, string> = {
            transcribing: 'Transcrevendo',
            thinking: 'Pensando',
            speaking: 'Falando',
            listening: 'Ouvindo',
            interrupted: 'Interrompido',
          };
          const tone = agentState === 'interrupted' ? 'warn' : 'ok';
          this.setStatus(
            '#session-status',
            labels[agentState] ?? agentState,
            tone,
          );
        }
        if (metadata.agent_state === 'interrupted' || state === 'stopped') {
          const started = performance.now();
          this.player.flush();
          this.send({mimetype: 'application/x-client-metric', metadata: {name: 'playback_flush_ms', value: performance.now() - started}});
        }
        return;
      }
      if (message.mimetype === 'application/x-resource-state') {
        this.resources = metadata as unknown as ResourceSnapshot;
        this.renderResources();
        return;
      }
      const inline = message.part?.inline_data;
      if (inline?.data && inline.mime_type?.startsWith('audio/')) {
        void this.player.enqueue(inline.data, inline.mime_type).catch((error) => {
          if (!this.audioPlaybackFailed) {
            this.audioPlaybackFailed = true;
            this.showError('Áudio indisponível', this.errorText(error));
          }
        });
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
    this.pipeline.innerHTML = this.capabilities.pipelines
      .filter((item) => item.implemented)
      .map((item) => `<option value="${item.id}">${item.label}</option>`).join('');
  }

  private renderConfig(): void {
    if (!this.config || !this.capabilities) return;
    const draft = this.config.draft;
    this.pipeline.value = draft.pipeline_id;
    const models = modelsForPipeline(this.capabilities, draft.pipeline_id);
    this.model.innerHTML = models.map((item) => `<option value="${item.id}">${item.label}</option>`).join('');
    this.model.value = draft.model_id;
    const pipeline = this.capabilities.pipelines.find((item) => item.id === draft.pipeline_id);
    const voices = pipeline?.id === 'cascade_local' ? pipeline.voices : this.capabilities.voices;
    this.voice.innerHTML = (pipeline?.id === 'gemini_live' ? '<option value="">Automática</option>' : '') + voices.map((voice) => `<option>${voice}</option>`).join('');
    this.voice.value = draft.pipeline_id === 'cascade_local' ? draft.cascade.voice_id : draft.voice_name ?? '';
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
    const model = models.find((item) => item.id === draft.model_id);
    element('#thinking-level-wrap').hidden = model?.thinking_field !== 'thinking_level';
    element('#thinking-budget-wrap').hidden = model?.thinking_field !== 'thinking_budget';
    const cascadeDraft = draft.pipeline_id === 'cascade_local';
    element('#cascade-settings').hidden = !cascadeDraft;
    element('#preset-wrap').hidden = cascadeDraft;
    element('#chattiness-wrap').hidden = cascadeDraft;
    element('#advanced-config').hidden = cascadeDraft;
    element<HTMLSelectElement>('#reasoning-effort').value = draft.cascade.reasoning_effort;
    element<HTMLSelectElement>('#cascade-device').value = draft.cascade.device;
    element<HTMLInputElement>('#cascade-stt').value = draft.cascade.stt_model_id;
    element<HTMLInputElement>('#cascade-tts').value = draft.cascade.tts_model_id;
    this.renderCaptureCapabilities();
    const dirty = this.config.dirty_fields.length;
    element('#draft-status').textContent = dirty
      ? `Rascunho · ${dirty} ${dirty === 1 ? 'alteração' : 'alterações'}`
      : 'Ativa';
    element<HTMLButtonElement>('#apply-config').disabled = dirty === 0;
  }

  private renderSession(): void {
    const labels = {stopped: 'Parado', starting: 'Iniciando', running: 'Em sessão', stopping: 'Parando', error: 'Erro'};
    const tone = this.session.state === 'running' ? 'ok' : this.session.state === 'error' ? 'error' : this.session.state === 'starting' || this.session.state === 'stopping' ? 'warn' : 'neutral';
    this.setStatus('#session-status', labels[this.session.state], tone);
    if (this.session.state === 'error' && this.session.last_error_detail) {
      this.showError('Sessão encerrada', this.session.last_error_detail);
    }
    // A preparation failure is retryable: the backend creates a fresh
    // processor/worker request on the next Start. Keeping Start enabled here
    // avoids forcing a full-page reload after a transient CUDA/model error.
    element<HTMLButtonElement>('#start-session').disabled = ['starting', 'running', 'stopping'].includes(this.session.state) || this.socket?.readyState !== WebSocket.OPEN;
    element<HTMLButtonElement>('#stop-session').disabled = this.session.state === 'stopped' || this.session.state === 'stopping';
    element<HTMLTextAreaElement>('#message').disabled = this.session.state !== 'running';
    this.renderCaptureCapabilities();
    if (this.session.state === 'stopped' || this.session.state === 'error') this.player.flush();
    if (this.durationTimer !== null) window.clearInterval(this.durationTimer);
    if (this.session.started_at) {
      this.durationTimer = window.setInterval(() => this.renderDuration(), 1000);
      this.renderDuration();
    } else element('#session-duration').textContent = '00:00';
  }

  private renderCaptureCapabilities(): void {
    if (!this.config || !this.capabilities) return;
    const selected = effectiveConfig(this.config, this.session.state);
    const vision = visionForPipeline(this.capabilities, selected.pipeline_id);
    for (const selector of ['#camera', '#screen']) {
      element<HTMLButtonElement>(selector).disabled = !vision;
    }
    element('#preview-empty').querySelector('p')!.textContent = vision
      ? 'Ative a câmera ou compartilhe a tela'
      : 'A pipeline Local + Groq não aceita câmera ou tela.';
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
    if (this.metricsRequestPending) return;
    this.metricsRequestPending = true;
    try { this.renderMetrics(await controlApi.metrics()); } catch { /* status API covers it */ }
    finally { this.metricsRequestPending = false; }
  }

  private scheduleMetrics(): void {
    if (this.metricsTimer !== null) return;
    const interval = document.hidden
      ? 15000
      : this.session.state === 'running' || this.session.state === 'starting'
        ? 2000
        : 5000;
    this.metricsTimer = window.setTimeout(async () => {
      this.metricsTimer = null;
      await this.refreshMetrics();
      this.scheduleMetrics();
    }, interval);
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
    element('#vad-start-count').textContent = String(snapshot.counters.vad_utterances_started ?? 0);
    element('#vad-rejected-count').textContent = String(snapshot.counters.vad_candidates_rejected ?? 0);
    element('#interruptions-count').textContent = String(snapshot.counters.turn_interruptions ?? 0);
    element('#tts-cancelled-count').textContent = String(snapshot.counters.local_tts_cancelled ?? 0);
  }

  private connectLogs(): void {
    this.eventSource?.close();
    const source = new EventSource('/api/v1/logs/stream');
    this.eventSource = source;
    source.onmessage = (event) => {
      if (this.logsPaused) return;
      const value = JSON.parse(event.data) as {line: string};
      this.logBuffer.enqueue(value.line);
      this.scheduleLogRender();
    };
  }

  private scheduleLogRender(): void {
    if (this.logRenderPending) return;
    this.logRenderPending = true;
    window.setTimeout(() => {
      this.logRenderPending = false;
      this.logBuffer.flush();
      this.renderLogs(true);
    }, 100);
  }

  private async refreshLogFiles(): Promise<void> {
    const files = await controlApi.logFiles();
    const select = element<HTMLSelectElement>('#log-file');
    select.innerHTML = '<option value="">Tail ao vivo</option>' + files.files.map((file) => `<option value="${file.id}">${file.id}</option>`).join('');
  }

  private async loadSelectedLog(): Promise<void> {
    const id = element<HTMLSelectElement>('#log-file').value;
    if (!id) {
      this.logBuffer.clear();
      this.renderLogs();
      return;
    }
    try {
      this.logBuffer.replace((await controlApi.logFile(id)).lines);
      this.renderLogs();
    } catch (error) { this.showError('Log não carregado', this.errorText(error)); }
  }

  private renderLogs(autoScroll = false): void {
    const level = element<HTMLSelectElement>('#log-level').value;
    const search = element<HTMLInputElement>('#log-search').value.toLocaleLowerCase();
    const lines = this.logBuffer.lines.filter((line) => (!level || line.includes(level)) && (!search || line.toLocaleLowerCase().includes(search)));
    const output = element<HTMLPreElement>('#logs');
    output.textContent = lines.join('\n');
    if (autoScroll) output.scrollTop = output.scrollHeight;
  }

  private renderResources(): void {
    const overallLabels = {
      unloaded: 'Não carregados',
      loading: 'Carregando',
      ready: 'Prontos',
      error: 'Erro',
    };
    const overallTone = this.resources.overall_state === 'ready'
      ? 'ok'
      : this.resources.overall_state === 'error'
        ? 'error'
        : this.resources.overall_state === 'loading'
          ? 'warn'
          : 'neutral';
    this.setStatus(
      '#resources-overall',
      overallLabels[this.resources.overall_state],
      overallTone,
    );
    for (const id of ['stt', 'tts'] as const) {
      const component = this.resources.components.find((item) => item.id === id);
      this.renderResource(id, component);
    }
  }

  private renderResource(
    id: 'stt' | 'tts',
    component: ResourceComponent | undefined,
  ): void {
    const card = element<HTMLElement>(`[data-resource="${id}"]`);
    const state = component?.state ?? 'unloaded';
    const labels = {
      unloaded: 'Não carregado',
      validating: 'Validando',
      loading: 'Carregando',
      warming: 'Aquecendo',
      ready: 'Pronto',
      error: 'Erro',
    };
    const phases: Record<string, string> = {
      validating: 'Validando dependências',
      loading: 'Carregando pesos',
      loading_weights: 'Carregando pesos',
      warming: 'Aquecendo inferência',
      ready: 'Pronto',
      error: 'Falha no carregamento',
      unloaded: 'Aguardando Start',
    };
    card.dataset.state = state;
    card.querySelector<HTMLElement>('.resource-state')!.textContent = labels[state];
    const memory = component?.memory_reserved_mib
      ? `${component.memory_reserved_mib} MiB reservados`
      : null;
    const elapsed = component?.load_ms
      ? `${(component.load_ms / 1000).toFixed(1)} s`
      : null;
    const detail = component?.error
      ? `${component.error.message} ${component.error.recovery}`
      : [
          component?.model_id,
          component?.phase ? phases[component.phase] ?? component.phase : null,
          component?.device,
          component?.gpu_name,
          memory,
          elapsed,
        ].filter(Boolean).join(' · ') || 'Será carregado ao iniciar.';
    card.querySelector<HTMLElement>('.resource-detail')!.textContent = detail;
    card.title = detail;
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
