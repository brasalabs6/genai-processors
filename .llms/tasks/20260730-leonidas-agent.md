# Implementar e validar o agente Leonidas

## Goal Metadata

- Goal type: `implementation-program`
- Version: `20260730-0031`
- Owner/repo: `local/genai-processors`
- Local path: `/home/guilherme/genai-processors`
- Primary branch: `main`
- Task file: `/home/guilherme/genai-processors/.llms/tasks/20260730-leonidas-agent.md`
- Expected duration: `multi-hour`

## Objective

Entregar o aplicativo standalone `/leonidas`: agente conversacional que vê,
ouve e fala em tempo real, suporta Gemini Live 2.5/3.1 e pipeline cascata local
Parakeet v3 → Groq reasoning → XTTS v2/CUDA, possui controle local, Vite WebUI,
observabilidade e validação empírica com mídia demo gerada pelo Gemini. O plano
operacional detalhado e seu progresso vivem em
`/home/guilherme/genai-processors/leonidas/PLAN.md`.

## Success Criteria

- Documentação, backend, API, WebSocket e UI satisfazem os três specs canônicos.
- Gemini 2.5 e 3.1 preservam seus transports e tool-call modes distintos.
- Start/Stop/Apply nunca reutilizam coroutine/stream e não deixam tasks órfãs.
- Configuração, voz, objetivo, latência, métricas e logs funcionam pela UI.
- Suíte offline cobre contratos E2E e suíte opt-in testa ambos os modelos reais.
- O áudio demo é gerado pelo Gemini; a imagem tenta Gemini e pode usar fallback
  Pillow explícita e rotulada quando a quota de imagem estiver bloqueada.
- O milestone Gemini é commitado e recebe a tag anotada `leonidas-v0.1.0` antes
  de qualquer implementação da pipeline cascata.
- Parakeet v3 transcreve áudio real localmente, Groq produz a resposta e XTTS v2
  sintetiza áudio reproduzível; a composição completa passa smoke empírico.
- Pipeline e modelos cascata são configuráveis pela UI via capabilities.
- Todas as validações do plano passam ou uma dependência externa é registrada
  com comando e condição exata de desbloqueio.

## Target And Context

- Repository/path: `/home/guilherme/genai-processors`, aplicação `/leonidas`.
- Relevant specs/contracts: `leonidas/SPECS.md`, `leonidas/WORKFLOW.md`,
  `leonidas/UI_SPECS.md`, `leonidas/PLAN.md`, root `AGENTS.md`.
- Existing artifacts to read first: `llms.txt`, `README.md`, `pyproject.toml`,
  `examples/live_commentator`, `genai_processors/core/live_model.py`,
  `genai_processors/dev/live_server.py`.
- External systems/checks: Google Gemini Live/image APIs, NVIDIA NGC/Hugging
  Face para Parakeet, Groq API e pesos XTTS v2; real calls require
  `GOOGLE_API_KEY`/`GROQ_API_KEY` e downloads locais dos modelos.

## Operating Mode

- Continue until a stop condition or blocked condition is reached.
- Prefer the next safe action when the contract is explicit.
- Ask the human only for listed human-decision triggers.
- If this file is missing, unreadable, or internally conflicting, report `BLOCKED`.
- Antes de agir sobre qualquer novo input do usuário, reler este arquivo e
  `leonidas/PLAN.md`, reconciliar o input e atualizar ambos primeiro. Requisitos
  anteriores só podem ser removidos por instrução explícita.

## Invariants

- Preservar APIs públicas e o exemplo `examples/live_commentator`.
- Nunca registrar ou versionar chaves, mídia, transcripts ou payloads privados.
- Configuração/provider-specific fica no adapter; `ProcessorPart` permanece o
  contrato multimodal interno e WebSocket.
- Nenhuma dependência base obrigatória de CUDA; engines locais permanecem
  isolados como runtime opcional e declaram device/VRAM/fallback.
- Todo comportamento novo segue Red-Green-Refactor.
- UI é implementada diretamente com Vite + TypeScript, sem Gemini como agente.

## Allowed Actions

- Ler e modificar `/leonidas`, seus testes, docs e configuração necessária.
- Adicionar entradas estritamente necessárias ao `.gitignore`.
- Usar `GOOGLE_API_KEY` do ambiente em smokes opt-in sem imprimir seu valor.
- Usar `GROQ_API_KEY` já presente no ambiente sem imprimir seu valor.
- Instalar dependências opcionais e baixar pesos Parakeet/XTTS em caches locais
  ignorados, após verificar compatibilidade do Python/CUDA.
- Gerar mídia e relatórios somente em diretórios ignorados pelo Git.
- Executar testes, builds, format checks e smokes reais explicitamente previstos.

## Forbidden Actions

- Alterar comportamento público de `genai_processors` ou do Live Commentator
  original sem migração e autorização separada.
- Commitar credenciais, `.runtime`, logs, assets/resultados E2E ou node_modules.
- Expor servidores fora de `127.0.0.1`.
- Simular sucesso de provider real, ocultar a origem sintética de imagem ou
  enfraquecer thresholds para obter aprovação.
- Anunciar Parakeet/Groq/XTTS como suportados antes de testes reais por estágio
  e end-to-end.

## Mode-Specific Rules

Este é um `implementation-program`. Executar ondas pequenas e revisáveis,
validar cada contrato antes da integração e registrar rollback para mudanças de
lifecycle/configuração. Commits, se solicitados, devem ser atômicos e excluir
trabalho não relacionado como `.agents/`. A suíte real é opt-in e a suíte fake
de contrato é obrigatória. Falha externa não autoriza substituir evidência real
por mocks; mocks provam apenas o contrato offline.

## Execution Model

1. Reconciliar specs, plano, task e estado do worktree.
2. Concluir a UI e integração local já iniciadas.
3. Criar tests-first a infraestrutura E2E: manifest, asset generator, validação,
   Live runner, avaliação e report.
4. Gerar assets Gemini quando a credencial/capability estiver disponível.
5. Rodar offline, build/UI e smokes 2.5/3.1; corrigir causas e repetir.
6. Auditar todos os requisitos Gemini, segurança e diff; criar commit atômico e
   tag anotada `leonidas-v0.1.0`.
7. Atualizar os três specs para a pipeline cascata antes de implementá-la.
8. Verificar ambiente CUDA/Python e instalar adapters opcionais compatíveis.
9. Implementar, testar e integrar Parakeet v3, Groq reasoning e XTTS v2.
10. Rodar smokes reais por estágio e end-to-end, auditar tudo e produzir o
    relatório final ampliado.

Após cada novo input do usuário, voltar ao passo 1 antes de executar a mudança.

## Issue, Decision, And Blocker Rules

- Classify findings as:
  - confirmed actionable issue
  - decision-needed item
  - duplicate/resolved/non-issue
  - external blocker
- Mark `Human decision required: yes` only when product intent, architecture,
  ownership, credentials, or external policy blocks safe progress.
- Erros 1007, config incompatível, reset loop, áudio inválido e tasks pendentes
  são issues confirmadas; não são flakiness.

## Validation Plan

- `.venv/bin/python -m pytest leonidas/tests`
- `.venv/bin/python -m pytest leonidas/e2e/tests`
- `cd leonidas/webui && npm test && npm run typecheck && npm run build`
- `.venv/bin/python -m pyink --check leonidas`
- `.venv/bin/python -m flake8 leonidas --count --select=E9,F63,F7,F82 --show-source --statistics`
- Live: gerar assets e executar `python -m leonidas.e2e.run --models all`.
- Cascata: executar preflight CUDA/modelos, testes reais por adapter e cenário
  completo áudio → STT → Groq → TTS → PCM, incluindo cancelamento.
- If validation cannot run, record command, reason, risk, and substitute evidence.

## Memory And Artifacts

- Session/log path: `/home/guilherme/genai-processors/logs/` e
  `/home/guilherme/genai-processors/leonidas/.runtime/` (ignorados).
- Reports: `leonidas/.runtime/e2e/results/` para dados reais; resumo redigido no
  relatório final da sessão.
- Reviews: diff final e alinhamento contra os três specs e `PLAN.md`.
- Decisions: registrar em `leonidas/PLAN.md`.
- Completion report: resposta final com arquivos, comandos, resultados,
  limitações externas e comando de inicialização.
- Evidência Gemini 2026-07-30: suíte combinada 113 passed/1 live skipped,
  frontend 8 passed + typecheck/build, smoke standalone Start/Stop e E2E real
  PASS nos modelos 2.5 e 3.1; detalhes redigidos em `leonidas/PLAN.md`.

## Stop Conditions

- Todos os success criteria estão provados por código e validação relevante.
- Não há item executável independente pendente no plano.
- O worktree não contém segredo, asset real, log ou alteração não relacionada.
- Qualquer item externo restante possui estado, evidência e condição exata de
  desbloqueio, sem ser apresentado como concluído.

## Blocked Conditions

- A mesma dependência externa ausente bloqueia todo trabalho restante após a
  suíte offline, UI e infraestrutura live estarem completas.
- `GOOGLE_API_KEY` ou acesso ao modelo de geração de imagem está indisponível
  para produzir os assets/smokes reais; registrar `BLOCKED_EXTERNAL`.
- Um conflito de produto/contrato não resolvível por specs exige decisão humana.

## Final Report Requirements

- Final state: completo ou bloqueado com motivo exato.
- Files/artifacts created: docs, código, testes e caminhos ignorados.
- Validation performed: comandos, contagens e resultados reais.
- PRs/issues/commits if any: IDs e escopo, excluindo trabalho do usuário.
- Residual risks: modelos preview, browser/device, VRAM/CUDA, compatibilidade
  Python dos engines, download/cache de pesos e disponibilidade Groq.
- Completion or blocked verdict: explícito, sem tratar teste fake como live.
