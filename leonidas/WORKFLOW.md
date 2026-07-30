# Leonidas — Workflows e máquinas de estado

## Componentes

```mermaid
flowchart LR
  UI[Vite WebUI] -->|REST /api/v1| API[Control API]
  UI <-->|ProcessorPart WebSocket| WS[Media Server]
  API --> CFG[Config Store]
  API --> SM[Session Manager]
  API --> LOG[Log Store]
  API --> MET[Metrics]
  WS --> SM
  SM --> REG[Pipeline Registry]
  REG --> G25[Gemini Live 2.5]
  REG --> G31[Gemini Live 3.1]
  G25 --> RATE[RateLimitAudio]
  G31 --> RATE
  RATE --> WS
```

## Fluxo multimídia

```mermaid
flowchart TD
  Mic[Microfone PCM 16 kHz] --> WSIn[ProcessorPart realtime]
  Screen[Tela/câmera JPEG limitada] --> WSIn
  Text[Texto final] --> WSIn
  WSIn --> Detect[Event detection]
  Detect --> Agent[Leonidas state machine]
  Agent --> Live[Gemini Live profile]
  Live --> Transcript[output_transcription]
  Live --> PCM[PCM 24 kHz]
  PCM --> Pace[RateLimitAudio]
  Pace --> Player[Playback com flush]
  Live --> Metrics[TTFA e duração]
```

## Sessão

```mermaid
stateDiagram-v2
  [*] --> stopped
  stopped --> starting: POST /session/start
  starting --> running: pipeline saudável
  starting --> error: falha/timeout
  running --> stopping: POST /session/stop
  running --> stopping: disconnect
  running --> stopping: apply config
  stopping --> stopped: cleanup concluído
  stopping --> error: cleanup forçado falha
  error --> starting: start explícito
  error --> stopped: stop explícito
```

Invariantes:

- há no máximo uma task de pipeline e uma conexão de mídia proprietária;
- toda inicialização cria nova fila e novo stream;
- `stop` pode ser repetido sem erro;
- nenhuma transição automática sai de `error`.

## Aplicar configuração

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant Store
  participant Session
  participant Pipeline
  UI->>API: PUT draft(expected_revision)
  API->>Store: validar + persistir draft
  Store-->>UI: revision + dirty_fields
  UI->>API: POST apply
  API->>Store: validar draft/capabilities
  alt sessão parada
    API->>Store: promover active
    API-->>UI: active atualizado
  else sessão ativa
    API->>Pipeline: construir candidato
    API->>Session: stop com timeout
    API->>Store: promover active
    API->>Session: start candidato
    alt saudável
      API-->>UI: running + nova revisão
    else falhou
      API->>Store: restaurar active anterior
      API->>Session: uma tentativa de rollback
      API-->>UI: erro estruturado
    end
  end
```

## Pipeline por modelo

```mermaid
flowchart LR
  Profile{Model profile}
  Profile -->|2.5| C[client_content + media]
  C --> A[NON_BLOCKING tools]
  Profile -->|3.1| R[realtime_input + typed media]
  R --> S[synchronous tools]
  A --> Common[State machine comum]
  S --> Common
```

O profile decide transports, tools e campos do SDK. A máquina de estados não
contém condicionais baseadas em nomes de modelo.

## Start e Stop

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant WS
  participant Runtime
  UI->>WS: conectar mídia
  WS-->>UI: connected
  UI->>API: POST start
  API->>Runtime: nova fila + processor
  Runtime-->>WS: starting
  Runtime-->>WS: running
  UI->>API: POST stop
  API->>Runtime: fechar entrada e cancelar
  Runtime-->>WS: stopping
  Runtime-->>WS: stopped
  WS-->>UI: flush playback
```

## Interrupção

```mermaid
sequenceDiagram
  participant User
  participant Browser
  participant Model
  participant Runtime
  User->>Browser: começa a falar/evento visual
  Browser->>Model: áudio/frame realtime
  Model->>Runtime: interrupted
  Runtime->>Browser: state interrupted
  Browser->>Browser: descartar fila PCM imediatamente
  Browser->>Runtime: metric playback_flushed
```

## Preview de voz

```mermaid
stateDiagram-v2
  [*] --> idle
  idle --> validating: preview
  validating --> generating: válido e lock adquirido
  validating --> failed: modelo/voz inválidos
  generating --> ready: WAV limitado
  generating --> failed: timeout/provedor
  ready --> idle: resposta entregue
  failed --> idle: erro entregue
```

## Logs

```mermaid
flowchart LR
  Runtime --> Redact1[Redação antes de gravar]
  Redact1 --> Rotate[Rotating files]
  Rotate --> List[GET /logs]
  Rotate --> Read[GET /logs/id]
  Redact1 --> Bus[Bounded subscriber bus]
  Bus --> Redact2[Redação de defesa]
  Redact2 --> SSE[GET /logs/stream]
```

Clientes lentos perdem linhas antigas; nunca bloqueiam o runtime.

## Reconexão e falhas

```mermaid
stateDiagram-v2
  [*] --> disconnected
  disconnected --> connecting: UI carregada
  connecting --> connected: socket aberto
  connecting --> reconnecting: falha
  connected --> reconnecting: fechamento inesperado
  reconnecting --> connecting: backoff 1/2/4/8/15s
  reconnecting --> disconnected: usuário para
  connected --> disconnected: fechamento intencional
```

Perder o WebSocket para a sessão ativa dispara Stop no backend. Reconectar não
reinicia automaticamente a sessão: o usuário escolhe Start.

## E2E empírico

```mermaid
flowchart LR
  Script[Texto PT-BR] --> GeminiTTS[Gemini 3.1 Flash TTS]
  GeminiTTS --> WAV[WAV privado validado]
  Prompt[Prompt visual] --> GeminiImage[Gemini Image]
  GeminiImage -->|quota disponível| PNG[PNG privado]
  GeminiImage -->|quota bloqueada + flag| Pillow[Fixture synthetic rotulada]
  WAV --> Resample[PCM 16 kHz em chunks]
  PNG --> Runner[Runner por model profile]
  Pillow --> Runner
  Resample --> Runner
  Runner --> G25[Gemini Live 2.5]
  Runner --> G31[Gemini Live 3.1]
  G25 --> Eval[Áudio + TTFA + semântica + cleanup]
  G31 --> Eval
  Eval --> Report[JSON/Markdown redigidos]
```
