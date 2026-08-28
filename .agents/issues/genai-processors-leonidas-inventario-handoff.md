# Inventário de Handoff — Família genai-processors / leonidas / nexus-processors

**Data:** 2026-07-29
**Autor:** Inventário automático (read-only) a pedido do Guilherme
**Escopo:** Localizar e classificar todas as versões/cópias do projeto genai-processors na máquina, incluindo as variantes "leonidas" (agente conversacional em tempo real) e "nexus-processors" (renomeação do genai-processors).

---

## TL;DR — O que existe

Existem **18 diretórios** espalhados pela máquina que correspondem a três linhagens:

1. **genai-processors** — a biblioteca base do Google DeepMind, usada como fundação.
2. **leonidas** — o agente "autoconsciente e reativo" que conversa em tempo real (áudio/vídeo) construído **em cima** do genai-processors. É o foco principal do Guilherme.
3. **nexus-processors** — um fork do genai-processors apenas renomeado (mesmo código, `genai_processors` → `nexus_processors`).

Há também cópias do leonidas espalhadas como `resources/leonidas`, `resources/leonidas2`, e workspaces swarm (stacks Docker/Traefik para hospedar o leonidas).

---

## Mapa rápido (tabela-resumo)

| # | Caminho | Linhagem | Git? | Branch | Remote | Último commit | Dirty | Tamanho |
|---|--------|----------|------|--------|--------|---------------|-------|---------|
| 1 | `/home/guilherme/genai-processors` | genai-processors | sim | main | brasalabs6/genai-processors | 4227541 (2026-05-05) | 0 | 15M |
| 2 | `/home/guilherme/brainstorm/genai-processors` | genai-processors (+experiments) | sim | docs/llms-reference-genai-processors | brasalabs6/genai-processors | 4227541 (2026-05-05) | 5 | 12M |
| 3 | `/home/guilherme/Workdir/genai-processors` | genai-processors (fork upstream + leonidas) | sim | leonidas | google-gemini/genai-processors | 82a76d7 (2025-11-10) | 19 | 508M |
| 4 | `/home/guilherme/Workdir/genai-processors/leonidas` | leonidas (subpasta do #3) | não | — | — | — | — | 228M |
| 5 | `/home/guilherme/Workdir/leonidas` | leonidas (repo independente) | sim | dev | noneagi/leonidas | 035aa33 (2025-11-11) | 147 | 229M |
| 6 | `/home/guilherme/Workdir/leonidas/src/leonidas` | leonidas (código-fonte do #5) | não | — | — | — | — | 1,8M |
| 7 | `/home/guilherme/leonidas` | leonidas (missão/memory root) | sim | master | (sem remote) | a46443c (2026-06-26) | 16 | 40M |
| 8 | `/home/guilherme/workspace/nexus-os-dev/packages/genai-processors` | genai-processors (pacote nexus-os) | não | — | — | — | — | 1,2M |
| 9 | `/home/guilherme/workspace/nexus-os-dev/resources/leonidas` | leonidas (vazio) | não | — | — | — | — | 9K |
| 10 | `/home/guilherme/workspace/nexus-os-dev/resources/leonidas2` | leonidas (cópia + relatório) | não | — | — | — | — | 426K |
| 11 | `/home/guilherme/Workdir/nexus-os-dash/packages/genai-processors` | genai-processors (cópia dash) | não | — | — | — | — | 1,2M |
| 12 | `/home/guilherme/Workdir/nexus-os-dash/resources/leonidas2` | leonidas (cópia dash) | não | — | — | — | — | 242K |
| 13 | `/home/guilherme/Workdir/noneagi/nexus-processors` | nexus-processors (fork renomeado) | sim | main | noneagi/nexus-processors | 4d32687 (2025-08-20) | 1 | 2,0M |
| 14 | `/home/guilherme/Workdir/noneagi/leonidas-claude-telegram` | leonidas (telegram, vazio de src) | sim | HEAD | noneagi/leonidas-claude-telegram | (sem commits) | 1 | 263K |
| 15 | `/home/guilherme/Workdir/noneagi/swarm/workspace-leonidas` | swarm stack (Docker) | não | — | — | — | — | 29K |
| 16 | `/home/guilherme/Workdir/swarm/workspace-leonidas` | swarm stack (cópia) | não | — | — | — | — | 29K |
| 17 | `/home/guilherme/run/swarm/workspace-leonidas` | swarm stack (cópia) | não | — | — | — | — | 29K |
| 18 | `/home/guilherme/.grok/sessions/...genai-processors` | sessões Grok (metadados) | — | — | — | — | — | — |

---

## Detalhe por linhagem

### A) genai-processors (biblioteca base)

Três working trees, todas derivadas do mesmo histórico (commit `4227541` = "docs: refine live commentator blueprint" é a cabeça comum em duas delas).

**A1. `/home/guilherme/genai-processors`** — **working tree ativa / atual**
- Branch `main`, remote `brasalabs6/genai-processors`, **limpo** (0 alterações).
- Último commit `4227541` (2026-05-05).
- Estrutura padrão: `genai_processors/` (core, contrib, tests), `examples/` (incl. `live_commentator`, `realtime_simple_cli.py`, `chat.py`), `notebooks/`, `.llms/`, `llms.txt`.
- Tem `.venv` instalado (15M). É o diretório de trabalho atual do Guilherme.

**A2. `/home/guilherme/brainstorm/genai-processors`** — **ramo de documentação + experimentos**
- Branch `docs/llms-reference-genai-processors`, mesmo remote `brasalabs6/genai-processors`.
- **Dirty: 5 entradas não-versionadas** — `AGENTS.md`, `changes/`, `experiments/`, `.llms/docs/`, `.llms/urgent/`.
- Diferencial importante: contém `experiments/` com três subprojetos:
  - `live_multimodal_observer/` — **experimento WebRTC-first de observação local (mic + tela/câmera)**. V1 só responde em texto (ASR via Codex-LB, vision via gpt-5.4-mini, reasoning via gpt-5.5). V2 reserva diarização pyannote, XTTS 2, Whisper local, NVIDIA NeMo. Tem testes (pipeline, store, audio, asr, vision, fusion, tts, ui) e `runs/` com timelines JSONL.
  - `codex_api/` — CLI + responses_processor.
  - `parallel_reasoning/` — CLI de raciocínio paralelo.
- `AGENTS.md` aqui é o contrato "NO HACKS" rigoroso da organização.
- Última modificação 2026-06-12. É provavelmente o local mais rico em trabalho experimental recente sobre o "agente em tempo real".

**A3. `/home/guilherme/Workdir/genai-processors`** — **fork do upstream Google + leonidas embutido**
- Branch `leonidas`, remote `google-gemini/genai-processors` (upstream oficial).
- Último commit `82a76d7` "init leonidas" (2025-11-10).
- **Dirty: 19 arquivos** — staging de `.roomodes`, `docs/ARCHITECTURE.md`, `docs/PROJECT_STATUS.md`, `leonidas/leonidas.py`, modificações em `leonidas/README.md`, `commentator_ais.py`, `commentator_cli.py`, além de não-rastreados `leonidas/AGENTS.md`, `config.py`, `pyproject.toml`, `src/`, `relatorio_analise_leonidas.md`.
- 508M (inclui `.venv` do leonidas). É o ponto onde o leonidas nasceu **dentro** do fork do genai-processors antes de ser extraído para repo próprio.

### B) leonidas (o agente conversacional em tempo real)

Definição (do próprio README): *"Self-Aware Reactive AI Assistant — assistente autoconsciente e reativo para colaboração em tempo real via áudio e vídeo"*. Baseado no genai-processors. Ferramentas de autocontrole: `pause_and_think`, `set_priority`, `propose_action`, `wait_for_user`. Arquitetura: input (vídeo/áudio/tela) → event detection (Gemini Flash Lite) → pipeline de processors → resposta.

Há **várias cópias**, refletindo a evolução "nasceu dentro do fork → extraído para repo próprio → cópias em resources/ e dash/":

**B1. `/home/guilherme/Workdir/leonidas`** — **repo leonidas independente (mais desenvolvido)**
- Branch `dev`, remote `noneagi/leonidas`, último commit `035aa33` "init" (2025-11-11).
- **Dirty: 147 arquivos** — muita documentação nova em `docs/` (MVP_ROADMAP, MVP_CHAT_SPECIFICATION, MVP_VOICE_SPECIFICATION, MVP_TELEGRAM_SPECIFICATION, MVP_AUTHENTICATION_SPECIFICATION, HIERARCHICAL_ORCHESTRATOR_SYSTEM, DEPLOYMENT_GUIDE_SUPER_MEGA_TASK_PROMPT, etc.), remoções em `ui/` e `logs/`, `.roomodes`, `archive/`, `README_TESTING.md`.
- Código-fonte em `src/leonidas/`: `core.py` (39KB), `ais.py`, `cli.py`, `config.py`, `websocket_server.py`, `logging_config.py`, e pacotes `api/`, `connections/` (websocket client/controller/handler, google_live_manager, session_manager, auth, quota), `orchestrator/` (state_machine, workflow_manager, context_manager, event_system, processing_pipeline, monitoring, super_mega_task_prompt), `processors/` (event_detection, live_model, window, connection_pool, base, streams), `websocket/`.
- Também há `src/commentator/` (commentator.py, commentator_ais.py, commentator_cli.py, config.py).
- Tem `tests/`, `ui/`, `uv.lock`, `.venv`. É a versão mais completa e "real" do leonidas como software.

**B2. `/home/guilherme/Workdir/genai-processors/leonidas`** — **cópia do leonidas dentro do fork (origem)**
- Sem `.git` próprio (faz parte do repo genai-processors #A3).
- Mesmo conteúdo do leonidas "monoarquivo" (leonidas.py 41KB, commentator.py 40KB, commentator_ais.py, commentator_cli.py, config.py, AGENTS.md 21KB, relatorio_analise_leonidas.md 22KB, README.md).
- 228M por causa do `.venv`. Data 2025-11-10.

**B3. `/home/guilherme/leonidas`** — **memory root / missão (não é o código do agente)**
- Branch `master`, **sem remote**, último commit `a46443c` (2026-06-26).
- **Dirty: 16 arquivos** — alterações em `.llms/forge/` (forge-agent, forge-bus-mcp, contratos _shared), não-rastreados `.agents/skills/grok-agent-orchestration/`, `.llms/issues/`, `.llms/reviews/`, `data/recovery/`, `workspace/scheduled-tasks-research.md`.
- **Atenção:** este **não** é o código do agente leonidas. É a "memória durável / raiz de missão" do Guilherme (estado, handoff, skills, forge). O `.archived/state/HANDOFF.md` documenta a "missão leonidas" 2026-05-09→05-16 (relacionada a PRs do `goblins`, não ao agente em si). Contém `data/USER.md`, recovery de episódios/sessões, e a árvore `.llms/forge/` (forge-api, forge-agent, forge-bus-mcp).

**B4. `/home/guilherme/workspace/nexus-os-dev/resources/leonidas2`** — **cópia de referência + relatório de análise**
- Sem git. 426K. Data 2026-01-19.
- Mesmo conjunto de arquivos do leonidas monoarquivo (leonidas.py, commentator.py, etc.) **mais** `relatorio_analise_leonidas.md` (22KB) — documento "Transformação do Leonidas em Repositório Git Independente", que descreve a extração do leonidas de dentro do genai-processors para repo próprio. Inclui também `docs/`, `ais_app/`, `commentator_adk/`, `src/`.

**B5. `/home/guilherme/workspace/nexus-os-dev/resources/leonidas`** — **vazio** (apenas placeholder, 9K).

**B6. `/home/guilherme/Workdir/nexus-os-dash/resources/leonidas2`** — **cópia dash** (242K, 2026-02-15), mesmo conjunto monoarquivo do leonidas, sem o relatório de análise.

**B7. `/home/guilherme/Workdir/noneagi/leonidas-claude-telegram`** — **variante Telegram (vazia de código)**
- Git sim, branch HEAD, remote `noneagi/leonidas-claude-telegram`, **sem nenhum commit**.
- Apenas `.llms/urgent/` com notas de orientação do `orchestrator-beloto` (2026-05-13). Nenhum código-fonte do agente. Aparentemente um intento de portar o leonidas para Telegram que não saiu do papel.

### C) nexus-processors (genai-processors renomeado)

**C1. `/home/guilherme/Workdir/noneagi/nexus-processors`** — **fork renomeado**
- Branch `main`, remote `noneagi/nexus-processors`, último commit `4d32687` "add analysis files" (2025-08-20).
- Commit anterior: `4654b4b` "renamed to nexus-processors" — confirma que é o genai-processors com `genai_processors` → `nexus_processors`.
- **Dirty: 1** (`.llms/` não-rastreado).
- Estrutura completa: `nexus_processors/` (core, contrib com openrouter/langchain, tests extensos), `examples/`, `notebooks/`, `playground/`. 2,0M.
- É o genai-processors "com outro nome", mantido no GitHub noneagi.

### D) genai-processors como pacote dentro de nexus-os

**D1. `/home/guilherme/workspace/nexus-os-dev/packages/genai-processors`** — pacote dentro do monorepo nexus-os-dev (sem git próprio, 1,2M, 2026-01-19). Tem `architecture.md` (56KB), `README-HUMAN.md` (28KB), `docs/`, `examples/`, `genai_processors/`.

**D2. `/home/guilherme/Workdir/nexus-os-dash/packages/genai-processors`** — cópia do pacote no dash (sem git, 1,2M, 2026-02-15). Tem `issues/` além do padrão.

### E) Swarm / deploy do leonidas

Três cópias idênticas (29K cada) de uma stack Docker Swarm para hospedar o leonidas:
- `/home/guilherme/Workdir/noneagi/swarm/workspace-leonidas`
- `/home/guilherme/Workdir/swarm/workspace-leonidas`
- `/home/guilherme/run/swarm/workspace-leonidas`

Conteúdo: `.env.example`, `.env.leonidas`, `Makefile`, `stack.yaml` (code-server linuxserver + Traefik, domínio `coder-leonidas.brasaai.com.br`, workspace `/home/leonidas/workspace`). É o ambiente de desenvolvimento remoto do leonidas.

---

## Relações de origem (deduzidas)

```
google-gemini/genai-processors (upstream)
  └─ fork → Workdir/genai-processors [branch leonidas]  ← leonidas nasceu aqui dentro (2025-11-10)
            └─ extração → Workdir/leonidas [repo próprio noneagi/leonidas, branch dev] (2025-11-11)
                          └─ cópias de referência → nexus-os-dev/resources/leonidas2 (+ relatório de análise)
                          └─ cópias de referência → nexus-os-dash/resources/leonidas2
                          └─ intento Telegram → noneagi/leonidas-claude-telegram (vazio)
                          └─ deploy swarm → */swarm/workspace-leonidas (3 cópias)

brasalabs6/genai-processors (fork da org)
  └─ /home/guilherme/genai-processors [main, limpo]  ← working tree ATUAL
  └─ /home/guilherme/brainstorm/genai-processors [docs/llms-reference, +experiments]  ← experimentos live_multimodal_observer

google-gemini/genai-processors (upstream) → renomeado
  └─ noneagi/nexus-processors [main] → /home/guilherme/Workdir/noneagi/nexus-processors

nexus-os-dev (monorepo)
  └─ packages/genai-processors (workspace + dash)
  └─ resources/leonidas (vazio) + resources/leonidas2 (cópia)

/home/guilherme/leonidas [master, sem remote]  ← memory root da "missão leonidas" (não é o código do agente)
```

---

## Estado de trabalho não commitado (dirty) — atenção para handoff

| Repo | Arquivos dirty | Risco |
|------|----------------|-------|
| `Workdir/leonidas` (dev) | **147** — muita doc MVP nova, remoções em `ui/` e `logs/`, `.roomodes`, `archive/` | **Alto**: trabalho substancial não commitado. Possível perda se `git clean`/checkout. |
| `Workdir/genai-processors` (leonidas) | **19** — staging de leonidas.py, docs, .roomodes | Médio: é o estado de "init leonidas" em andamento. |
| `/home/guilherme/leonidas` (master) | **16** — forge, issues, reviews, recovery | Médio: memory root, alterações em contratos forge. |
| `brainstorm/genai-processors` | **5** — experiments/, AGENTS.md, changes/ não-rastreados | Médio: `experiments/live_multimodal_observer` é o experimento mais recente de agente em tempo real e **não está versionado**. |
| `noneagi/nexus-processors` | **1** — `.llms/` | Baixo. |
| `leonidas-claude-telegram` | **1** — `.llms/` | Baixo (sem código). |

---

## Recomendação de "fonte da verdade" por objetivo

- **Quer a versão mais completa do agente leonidas como software?**
  → `/home/guilherme/Workdir/leonidas` (repo `noneagi/leonidas`, branch `dev`). Cuidado: 147 arquivos não commitados.
- **Quer o experimento mais recente de agente conversacional em tempo real (WebRTC multimodal)?**
  → `/home/guilherme/brainstorm/genai-processors/experiments/live_multimodal_observer` (não versionado — considere commitar).
- **Quer a biblioteca genai-processors limpa e atual?**
  → `/home/guilherme/genai-processors` (working tree atual, main, limpo).
- **Quer o genai-processors renomeado (nexus-processors)?**
  → `/home/guilherme/Workdir/noneagi/nexus-processors` (repo `noneagi/nexus-processors`).
- **Quer o contexto de missão/memory root do Guilherme?**
  → `/home/guilherme/leonidas` (não confundir com o agente).

---

## Próximos passos sugeridos

1. **Decidir o destino do `Workdir/leonidas`** (147 arquivos dirty): commitar em branch, ou arquivar. É a versão mais rica do agente e está vulnerável.
2. **Versionar `brainstorm/genai-processors/experiments/`** — o `live_multimodal_observer` é o experimento mais relevante de "agente que conversa em tempo real" e está apenas como não-rastreado.
3. **Consolidar cópias** — há pelo menos 4 cópias do leonidas monoarquivo (Workdir/genai-processors/leonidas, nexus-os-dev/resources/leonidas2, nexus-os-dash/resources/leonidas2, e a origem). Manter só a do repo `noneagi/leonidas` como canônica e arquivar as demais.
4. **Definir se `nexus-processors` e `genai-processors` devem convergir** ou se o nexus-processors segue como fork renomeado independente.
5. **Avaliar o `leonidas-claude-telegram`** — está vazio; confirmar se o intento de porta Telegram ainda vale.
