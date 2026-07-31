# Leonidas — Especificação Canônica

## 1. Status e precedência

Este documento é a fonte de verdade de produto e arquitetura do Leonidas. Ele
deve ser lido com `WORKFLOW.md` e `UI_SPECS.md`. Quando houver divergência, a
ordem é: requisitos explícitos atuais, este documento, `WORKFLOW.md`,
`UI_SPECS.md`, testes e implementação.

Leonidas é um aplicativo local construído sobre `genai-processors`. Ele nasce
do comportamento comprovado de `examples/live_commentator`, mas possui código,
configuração e ciclo de vida próprios. O exemplo original não deve importar o
Leonidas e o Leonidas não deve importar o exemplo original.

## 2. Objetivos

- Conversar em tempo real usando microfone, câmera ou compartilhamento de tela.
- Preservar as características distintas dos modelos Gemini Live 2.5 e 3.1.
- Permitir iniciar, parar e reiniciar sessões sem reutilizar streams ou
  coroutines já consumidas.
- Separar objetivo/persona editável das instruções internas protegidas.
- Expor voz, desempenho, VAD, visão e geração somente quando o modelo declarar
  suporte.
- Fornecer métricas e logs úteis sem persistir mídia, transcrições, prompts ou
  credenciais nos logs.
- Suportar uma pipeline cascata com Parakeet v3 local, Groq reasoning e XTTS v2
  local, anunciada somente após smokes reais por estágio e end-to-end.

## 3. Não objetivos desta versão

- Exposição em LAN ou internet, autenticação multiusuário ou TLS próprio.
- Groq Whisper, diarização ou instalação obrigatória de CUDA na biblioteca base.
- Compatibilidade de configuração com versões internas anteriores do exemplo.
- Edição das instruções protegidas de ferramentas e máquina de estados.

## 4. Arquitetura

O código reside no pacote de aplicação `/leonidas` e não é exportado pelo
pacote público `genai_processors`.

Responsabilidades:

- `config`: schema, defaults, validação, revisão e persistência atômica.
- `capabilities`: perfis de pipelines/modelos e catálogo de vozes.
- `prompts`: instruções protegidas e composição com o objetivo editável.
- `pipelines`: fábrica e implementação Gemini Live.
- `runtime`: estado, ciclo de vida, filas, cancelamento e rollback.
- `telemetry`: medições por sessão e agregados móveis.
- `log_store`: escrita redigida, listagem, leitura limitada e tail.
- `api`: HTTP local versionado.
- `server`: composição dos servidores HTTP e WebSocket.
- `webui`: cliente Vite + TypeScript.

O registro de pipelines é explícito. `pipeline_id=gemini_live` usa os profiles
Gemini existentes. `pipeline_id=cascade_local` usa Parakeet, Groq e XTTS. Cada
pipeline implementa o mesmo contrato de construção, capabilities e
cancelamento antes de aparecer na UI.

### Pipeline cascata local

```text
browser PCM 16 kHz -> WebRTC VAD/endpointing -> Parakeet TDT 0.6B v3
                   -> Groq GPT-OSS reasoning -> XTTS v2 -> PCM 24 kHz chunks
```

- STT: `nvidia/parakeet-tdt-0.6b-v3`, via Transformers, detecção automática de
  idioma e português suportado.
- LLM default: `openai/gpt-oss-20b`; `openai/gpt-oss-120b` é opção de maior
  qualidade. `reasoning_effort` é low/medium/high.
- TTS: `tts_models/multilingual/multi-dataset/xtts_v2`, idioma `pt`, referência
  de voz local allowlisted com pelo menos seis segundos.
- Device: `auto`, `cuda` ou `cpu`; `cuda` falha de forma explícita quando não
  disponível. O preflight registra GPU, VRAM e versões, nunca secrets.
- Inferência local bloqueante roda fora do event loop. Cancelar interrompe a
  entrega e limpa playback; uma chamada XTTS já iniciada termina no worker antes
  da próxima síntese.
- XTTS roda em subprocesso persistente criado por `.venv-xtts`. O isolamento é
  obrigatório porque Parakeet usa Transformers 5 e Coqui TTS 0.27.5 ainda usa
  Transformers 4.57.x. O protocolo privado é JSON Lines em stdin/stdout com
  áudio base64; morte do worker falha a sessão e nunca troca silenciosamente de
  engine.
- VAD aceita somente PCM mono 16-bit/16 kHz, frames de 30 ms, pre-roll de 300 ms,
  início após 90 ms de fala e fim após 450 ms de silêncio.
- Utterances são limitadas a 30 s. Histórico é limitado a 20 turnos e não é
  persistido.
- A pipeline cascata v0.2 declara `vision=false`: o catálogo Groq disponível
  nesta conta não oferece modelo visual. A UI desabilita câmera/tela e explica
  a limitação; visão nunca é descartada silenciosamente.

### Lifecycle e readiness dos modelos locais

- Parakeet e XTTS rodam em subprocessos persistentes separados. Parakeet usa
  a `.venv` principal/Transformers 5; XTTS usa `.venv-xtts`/Transformers 4.
- Estados por componente: `unloaded`, `validating`, `loading`, `warming`,
  `ready` e `error`. O estado inclui fase, modelo, device solicitado/resolvido,
  GPU, tempos, memória PyTorch alocada/reservada e erro seguro.
- Start da cascata retorna `starting` sem aguardar inferência bloqueante. A
  carga ocorre sequencialmente Parakeet → XTTS para limitar pico de VRAM.
- Warm-up executa inferência local real e só então marca `ready`. Pesos já
  instalados usam cache local sem sondagens repetidas ao Hugging Face.
- A sessão entra em `running` somente com os dois componentes `ready`. Stop
  invalida o start pendente; readiness concluída depois não inicia sessão.
- Modelos prontos são reutilizados entre sessões e fechados somente no shutdown.
- Gemini Live não cria, carrega ou consulta os workers locais.

## 5. Modelos e capabilities

Perfis iniciais:

| ID | Transporte default | Mídia realtime | Function calls |
|---|---|---|---|
| `gemini-2.5-flash-native-audio-preview-12-2025` | `client_content` | `media` | assíncronas/agendadas |
| `gemini-3.1-flash-live-preview` | `realtime_input` | `typed` | síncronas |

O perfil é a autoridade para voz, thinking, VAD, resolução e transports. Um
campo incompatível deve produzir erro `422 unsupported_configuration`; não é
permitido remover comportamento silenciosamente.

As vozes permitidas são: Zephyr, Puck, Charon, Kore, Fenrir, Leda, Orus,
Aoede, Callirrhoe, Autonoe, Enceladus, Iapetus, Umbriel, Algieba, Despina,
Erinome, Algenib, Rasalgethi, Laomedeia, Achernar, Alnilam, Schedar, Gacrux,
Pulcherrima, Achird, Zubenelgenubi, Vindemiatrix, Sadachbia, Sadaltager e
Sulafat. `null` significa voz automática do provedor.

## 6. Configuração

O contrato serializado é `AgentConfig`:

```json
{
  "schema_version": 1,
  "pipeline_id": "gemini_live",
  "model_id": "gemini-2.5-flash-native-audio-preview-12-2025",
  "voice_name": null,
  "objective": "Converse em português e ajude o usuário sobre o que vê.",
  "chattiness": 0.5,
  "performance_preset": "balanced",
  "media": {
    "frame_interval_ms": 1000,
    "max_width": 1280,
    "max_height": 720,
    "jpeg_quality": 0.75,
    "model_resolution": "medium"
  },
  "vad": {
    "start_sensitivity": null,
    "end_sensitivity": null,
    "prefix_padding_ms": null,
    "silence_duration_ms": null
  },
  "generation": {
    "temperature": null,
    "thinking_level": null,
    "thinking_budget": null,
    "context_trigger_tokens": null,
    "context_target_tokens": null
  },
  "cascade": {
    "stt_model_id": "nvidia/parakeet-tdt-0.6b-v3",
    "llm_model_id": "openai/gpt-oss-20b",
    "tts_model_id": "tts_models/multilingual/multi-dataset/xtts_v2",
    "reasoning_effort": "medium",
    "language": "pt",
    "device": "auto",
    "voice_id": "leonidas-reference"
  }
}
```

Limites:

- objetivo: 1–12.000 caracteres;
- chattiness: 0–1;
- frame interval: 250–10.000 ms;
- largura/altura: 160–1920 / 120–1080;
- JPEG: 0,30–0,95;
- temperatura: 0–2;
- paddings e silêncio: 0–10.000 ms;
- tokens: inteiros positivos e target menor que trigger.

Presets fornecem valores iniciais e overrides permanecem explícitos:

| Preset | Frame | Dimensão | JPEG | Resolução | Thinking | VAD end |
|---|---:|---|---:|---|---|---:|
| `low_latency` | 500 ms | 960×540 | 0,60 | low | 3.1 minimal / 2.5 budget 0 | 350 ms |
| `balanced` | 1000 ms | 1280×720 | 0,75 | medium | provedor | provedor |
| `quality` | 1000 ms | 1280×720 | 0,85 | high | 3.1 medium / 2.5 budget 512 | 700 ms |

O backend mantém `active`, `draft`, `revision` e `dirty_fields`. O cliente
envia `expected_revision`; conflitos retornam `409 revision_conflict`.
Defaults ficam versionados em código. O estado local é salvo atomicamente em
`leonidas/.runtime/config.json`, sem credenciais.

## 7. Sessão e aplicação transacional

Estados canônicos: `stopped`, `starting`, `running`, `stopping`, `error`.

- Start exige WebSocket de mídia conectado, configuração ativa válida,
  credenciais da pipeline e preflight local aprovado.
- Stop é idempotente, encerra entrada, cancela tasks, fecha processadores e
  publica `stopped`; após timeout deve cancelar forçadamente sem deixar tasks.
- Cada Start ou Apply cria novas filas, streams e processor instances.
- Apply parado apenas promove o draft.
- Apply rodando valida e constrói, para a sessão, promove e reinicia.
- Falha no novo runtime restaura a configuração anterior uma única vez. Falha
  também no rollback deixa a sessão em `error`; nunca inicia loop de reset.
- Apenas uma sessão multimídia pode estar ativa. Conexões adicionais recebem
  fechamento WebSocket por violação de política.

## 8. APIs

UI e REST: `http://127.0.0.1:8000`. WebSocket:
`ws://127.0.0.1:8765/api/v1/live`. Somente origens locais e a origem Vite de
desenvolvimento são aceitas.

Envelope REST:

```json
{"data": {}, "error": null, "request_id": "..."}
```

Erros usam `{code, message, details}` sem traceback ou conteúdo sensível.

Endpoints:

- `GET /api/v1/capabilities`
- `GET /api/v1/config`
- `PUT /api/v1/config/draft`
- `POST /api/v1/config/apply`
- `GET /api/v1/session`
- `POST /api/v1/session/start`
- `POST /api/v1/session/stop`
- `POST /api/v1/voices/preview` → `audio/wav`
- `GET /api/v1/metrics`
- `GET /api/v1/resources`
- `GET /api/v1/logs`
- `GET /api/v1/logs/{id}?cursor=&limit=`
- `GET /api/v1/logs/stream?level=&logger=` → SSE

`GET /api/v1/resources` retorna `schema_version`, `overall_state` e componentes
com `id`, `model_id`, `state`, `phase`, `device`, `gpu_name`, `load_ms`,
`memory_allocated_mib`, `memory_reserved_mib` e `error`. Campos de GPU/memória
são `null` em CPU. Erros possuem `stage`, `code`, `message` e `recovery`,
nunca traceback, prompt ou credencial. Os identificadores de componente são
sempre `stt` e `tts`; campos privados do worker, como request `id` e `type`,
nunca entram nesse contrato.

`POST /api/v1/session/start` preserva `200/running` para Gemini. Para cascata
fria retorna `202/starting`; readiness e transições posteriores chegam pelo
WebSocket.

O preview usa uma sessão efêmera, tem timeout de 15 segundos, áudio máximo de
10 segundos e concorrência máxima de um. Gemini usa uma sessão efêmera; XTTS
usa o engine local e a voz allowlisted. Ele nunca altera a sessão principal.

## 9. Protocolo WebSocket

O envelope continua sendo `ProcessorPart`. Configuração e reset não trafegam
mais como metadados genéricos. Entradas aceitas: PCM 16-bit mono 16 kHz,
JPEG, texto, fim do microfone e métricas do cliente. O limite é 2 MiB.

Estados e métricas saem como partes `application/x-state` e
`application/x-metric`. Seus metadados incluem `session_id`, `sequence` e
`timestamp`. `interrupted` e `stopped` obrigam o cliente a zerar o playback.

Readiness usa `application/x-resource-state`, com o mesmo snapshot de
`GET /api/v1/resources`. Estados de turno da cascata usam `agent_state`:
`listening`, `transcribing`, `thinking`, `synthesizing`, `speaking`,
`interrupted` ou `error`.

## 10. Métricas

Por sessão:

- conexão e startup da pipeline;
- fim da fala até primeiro áudio (TTFA);
- duração de resposta;
- interrupção até flush confirmado pelo cliente;
- frames enviados, descartados e bytes;
- chunks de áudio enviados/recebidos.
- carga local, STT, Groq e TTS (`local_model_load_ms`, `local_stt_ms`,
  `groq_reasoning_ms`, `local_tts_ms`).

O backend mantém no máximo 100 amostras por métrica e calcula valor atual,
média, p50 e p95. Métricas são memória-volátil e não incluem conteúdo.

## 11. Logs, privacidade e segurança

Logs são rotacionados em `/logs`, 10 MiB por arquivo e cinco backups. Nomes
começam por `leonidas-`. A redação ocorre antes da gravação e novamente antes
da API. Chaves, headers, query strings sensíveis, objetivo, transcrições,
payloads e base64 nunca são gravados.

A API de logs opera somente sobre IDs retornados pela listagem, limita cada
leitura a 2.000 linhas/512 KiB e rejeita traversal, symlinks externos, edição e
exclusão.

Credenciais existem somente no ambiente do backend. O aplicativo não deve
vincular em interfaces diferentes de `127.0.0.1` nesta versão.

## 12. Critérios de aceitação

- Os dois modelos iniciam, param e alternam sem pipeline presa ou tasks órfãs.
- Voz, objetivo, presets e overrides são validados e aplicados explicitamente.
- A UI nunca reinicia uma sessão durante a edição do draft.
- Stop e interrupção limpam o áudio imediatamente.
- Métricas e logs são visíveis sem expor conteúdo sensível.
- Reload restaura a última configuração válida, mas nunca uma credencial.
- Testes Python e TypeScript, typecheck, build, Pyink e Flake8 relevantes passam.

## 13. Validação empírica

`leonidas/e2e` mantém cenários versionados e assets/resultados privados em
`.runtime/e2e`. O áudio de usuário é produzido pelo Gemini TTS, validado como
WAV mono 16-bit/24 kHz e convertido para PCM 16 kHz antes do envio. A imagem
tenta Gemini Image; quando a conta não possui quota, a opção explícita
`--synthetic-image` cria uma fixture Pillow determinística e rotulada.

O runner envia imagem e áudio em chunks de 100 ms, mantém o stream bidirecional
aberto, coleta áudio/transcription em memória e encerra em
`generation_complete`. Relatórios persistem somente métricas e termos
semânticos encontrados, nunca o conteúdo integral. Sucesso exige áudio PCM
24 kHz com pelo menos 0,25 s, TTFA de até 20 s, ausência de erro e cancelamento
limpo. Testes reais são opt-in e a suíte offline não substitui sua evidência.
