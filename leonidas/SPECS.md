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
- Preparar contratos para pipelines futuras sem entregar adapters falsos para
  Whisper, LLMs turn-based ou TTS local.

## 3. Não objetivos desta versão

- Exposição em LAN ou internet, autenticação multiusuário ou TLS próprio.
- Implementação da pipeline Groq Whisper → LLM → TTS.
- Diarização, Parakeet, XTTS ou instalação obrigatória de CUDA.
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

O registro de pipelines é explícito. `pipeline_id=gemini_live` é a única
implementação desta versão. Uma pipeline futura deverá implementar o mesmo
contrato de construção, capabilities e cancelamento antes de aparecer na UI.

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

- Start exige WebSocket de mídia conectado e configuração ativa válida.
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
- `GET /api/v1/logs`
- `GET /api/v1/logs/{id}?cursor=&limit=`
- `GET /api/v1/logs/stream?level=&logger=` → SSE

O preview usa uma sessão efêmera, tem timeout de 15 segundos, áudio máximo de
10 segundos e concorrência máxima de um. Ele nunca altera a sessão principal.

## 9. Protocolo WebSocket

O envelope continua sendo `ProcessorPart`. Configuração e reset não trafegam
mais como metadados genéricos. Entradas aceitas: PCM 16-bit mono 16 kHz,
JPEG, texto, fim do microfone e métricas do cliente. O limite é 2 MiB.

Estados e métricas saem como partes `application/x-state` e
`application/x-metric`. Seus metadados incluem `session_id`, `sequence` e
`timestamp`. `interrupted` e `stopped` obrigam o cliente a zerar o playback.

## 10. Métricas

Por sessão:

- conexão e startup da pipeline;
- fim da fala até primeiro áudio (TTFA);
- duração de resposta;
- interrupção até flush confirmado pelo cliente;
- frames enviados, descartados e bytes;
- chunks de áudio enviados/recebidos.

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
