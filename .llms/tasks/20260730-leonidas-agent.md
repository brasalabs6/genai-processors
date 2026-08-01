# Implementar e validar o agente Leonidas

## Requisito adicional: interrupção tardia de áudio local 2026-08-01

O usuário informou que a pipeline local funciona parcialmente e depois para
de reproduzir voz. A reprodução controlada no PR1 mostrou que o worker XTTS
também pode ser encerrado com código `-9`; o journal registrou `global_oom`,
com o processo Python usando aproximadamente 3,7 GiB de RSS, apenas 4 GiB de
memória disponível e swap desabilitado. Isso transforma uma falha de recurso
em silêncio aparente no browser.

Antes de considerar o MVP funcional, a execução deve:

1. registrar diagnóstico estruturado para OOM/kill, timeout, protocolo e
   playback;
2. publicar estado de erro acionável quando o worker de áudio morrer, sem
   manter a sessão em `speaking`/`running` falsamente;
3. implementar recuperação limitada, sem loop infinito de reinício, e evitar
   novos pedidos enquanto o recurso local estiver indisponível;
4. cobrir com regressão worker morto e sequência de múltiplas sínteses;
5. validar múltiplos turnos reais Parakeet → Groq → XTTS e repetir Gemini
   2.5/3.1.

O preflight de importação não é evidência suficiente: o teste deve atravessar
`load` e sínteses reais. O ambiente de teste deve registrar memória disponível,
swap, VRAM e processos relevantes; se houver OOM externo causado por outras
aplicações, isso deve ser separado da conclusão sobre o código.

## Requisito adicional: diarização — 2026-08-01

A próxima evolução obrigatória do agente inclui diarização local opcional. O
componente deve ser um adapter independente do Parakeet, Groq e XTTS, aceitar
janelas/turnos de áudio e emitir segmentos `{speaker_id, start, end,
confidence}`. Deve suportar CUDA e fallback CPU, declarar custos de memória e
cache, executar fora do event loop, cancelar de forma segura e nunca impedir
STT, reasoning ou playback quando estiver ausente ou indisponível.

Adicionar testes de contrato com áudio sintético de dois falantes e smoke real
opt-in. Não adicionar pesos ou dependências CUDA ao pacote base, não acoplar a
diarização ao protocolo provider-specific e não considerar o requisito
completo até que a UI/capability mostre `unavailable/loading/ready/error`.

## Requisito adicional: backend realtime do Codex — 2026-08-01

Depois da estabilização/validação do áudio local e do contrato de diarização,
ler integralmente `Codex_App_Server_Realtime_API_Engenharia_Reversa.md`.
Determinar, com evidência do documento e do repositório, o protocolo realtime,
autenticação, eventos, áudio, cancelamento e limites. Se for implementável com
contrato confiável, adicionar um adapter server-side selecionável por
capability, mantendo `ProcessorPart` e sem tocar nas pipelines Gemini/Groq.
Criar testes de tradução e lifecycle antes de smoke real. Não inventar campos
ou endpoints que o documento não confirme e não enviar tokens para a UI.

Atualização de fonte de verdade — 2026-08-01: o binário `codex` instalado pode
estar desatualizado. Antes de finalizar o adapter, comparar também o código e
os schemas em `~/github/codex`; preferir a versão mais recente existente no
workspace, registrar divergências com o documento/binário e não declarar
suporte a uma versão que não tenha teste de contrato.

Autenticação — 2026-08-01: carregar a autenticação local somente do
`~/.codex/auth.json` (ou caminho configurado pelo runtime), sem transportar ou
expor o conteúdo para a UI. Criar testes com arquivo sintético redigido e um
smoke real opt-in que verifique handshake/lifecycle, reportando somente estado,
versão e latência. JSON inválido, ausência ou expiração devem falhar de modo
seguro e não afetar as pipelines Gemini/Groq.

## Governança adicional: checkpoints e versões estáveis — 2026-08-01

Commitar cada checkpoint funcional com escopo explícito antes de iniciar a
próxima frente. Criar tags anotadas somente para milestones realmente verdes,
após revisão do diff, testes correspondentes e verificação de que logs, chaves,
pesos, runtime e artefatos privados ficaram fora do Git. Não chamar uma
versão de estável enquanto qualquer gate obrigatório estiver apenas pendente,
flaky ou bloqueado por recurso externo.

### Evidência da continuação 2026-08-01

O PR1 foi validado nos dois modelos Gemini Live (2.5 e 3.1) com sucesso. A
falha local foi reproduzida no host: o processo XTTS recebeu SIGKILL por
`global_oom`; o guard agora impede o load quando `MemAvailable` está abaixo de
5120 MiB, diferencia OOM de protocolo e publica detalhe seguro para a UI. A
suíte Leonidas e a WebUI permanecem verdes. A prova real de múltiplos turnos
locais ainda depende de memória disponível no host; não declarar a cascata
local como validada até repetir esse smoke após liberar memória.

O host foi liberado e a validação foi repetida com sucesso: preflight CUDA
reportou 10.685 MiB disponíveis; cinco sínteses XTTS consecutivas passaram e
`cascade_smoke --device cuda --turns 3` produziu três transcrições, respostas
Groq e áudios PCM válidos em 37,51 s. A continuidade do worker local está
empiricamente validada; ainda falta a revisão do documento de API realtime do
Codex e a implementação/teste do adapter correspondente.

Checkpoint Codex: o adapter server-side inicial foi criado com JSONL
multiplexado, handshake experimental, lifecycle realtime, texto, áudio e
tradução de notificações para `ProcessorPart`. O checkout `~/github/codex`
confirma v3 e campos adicionais ausentes no binário instalado; por isso v3 é o
default do adapter e v2 permanece uma opção explícita de compatibilidade. Os
4 testes offline do contrato passaram. A integração pública ainda aguarda
essa revisão final e os testes da composição.

O loader server-side passou a validar e encaminhar somente a
`OPENAI_API_KEY` de `auth.json` para o processo Codex; tokens ChatGPT não são
tratados como API key. O smoke real com o `auth.json` local foi executado e
falhou sem vazar segredo: o arquivo está em `auth_mode=chatgpt`, sem
`OPENAI_API_KEY`, e o app-server exige API key para realtime. Repetir o smoke
é obrigatório depois de configurar uma credencial compatível.

## Reconciliação da troca de executor 2026-07-31

O usuário solicitou a continuidade pelo executor Luna e exigiu um commit do
estado já alterado antes de qualquer modificação adicional. Esse checkpoint é
`68c2cb5` (`chore(leonidas): checkpoint local model observability work`). O
executor deve reler este arquivo e `leonidas/PLAN.md` antes de cada novo input,
preservar Gemini 2.5/3.1 como regressão e validar a implementação atual antes
de ampliar o escopo. Se a tarefa se tornar insegura ou houver falha repetida
sem hipótese nova, registrar a evidência e informar o usuário em vez de
ocultar o problema.

Evidência da continuação: os workers reais Parakeet v3 e XTTS v2 alcançaram
readiness em CUDA na composição de produção; o smoke E2E local com Groq
passou após o warm-up. A WebUI agora permite nova tentativa após erro de
preparação e informa a fase de carregamento/aquecimento de cada componente.
Foram aprovados 77 testes Python, 14 Vitest, typecheck/build, Pyink, Flake8 e
diff check.

## Requisito adicional: áudio local e normalização STT 2026-07-31

Na primeira sessão manual bem-sucedida, a UI mostrou respostas de texto do
Groq e transcrição Parakeet quase em tempo real, mas não reproduziu o áudio
XTTS e exibiu artefatos `<blank>` no texto transcrito. Antes de editar, o
estado foi commitado em `30a2044`. Investigar e corrigir os dois caminhos com
testes de protocolo/player e regressão do adapter STT, sem alterar o exemplo
original nem quebrar Gemini 2.5/3.1. O aceite é empírico: áudio local deve
chegar ao `PcmPlayer` e tocar no browser, e a mensagem final não deve conter
tokens especiais de silêncio/blank.

Implementação concluída nesta onda: normalização STT no adapter Parakeet e
retomada defensiva do `AudioContext` no `PcmPlayer`. A prova de protocolo local
mostrou PCM 24 kHz válido chegando pelo WebSocket; a prova Parakeet real não
contém mais `<blank>`. Validação aprovada: 88 testes Python (2 live skipped),
14 Vitest, typecheck/build, Pyink, Flake8 e diff check.

### Execução complementar: VAD híbrido

Evidência da sessão real: 10 inferências STT, 7 respostas Groq, 9 flushes e
zero síntese TTS concluída. O endpoint permissivo tratava ruído como fala e
cancelava a resposta. Preservar `sim/não/aham`, substituir o detector por
WebRTC modo 3 + piso de ruído/RMS/histerese, não filtrar palavras válidas,
expor métricas de decisão e validar silêncio, fala curta, barge-in e PCM real.
O E2E com início desalinhado comprovou que o fim de fala deve usar 15 frames
(450 ms), não 12, para não dividir uma frase natural em dois turnos.

Estado concluído: silêncio + fala real pelo standalone geraram uma única
transcrição, zero interrupções, uma síntese XTTS e 681.056 bytes de PCM em 284
chunks. Smoke CUDA e regressões Gemini 2.5/3.1 passaram. A UI expõe contadores
VAD/interrupção/cancelamento e falhas de `AudioContext` com erro específico.

## Goal Metadata

- Goal type: `implementation-program`
- Version: `20260730-0041`
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

Continuação 2026-07-30 reconciliada sem mudança de escopo: avançar auditoria e
diagnóstico CUDA seguros enquanto o aceite jurídico XTTS permanece uma decisão
humana explícita.

Input sobre reinicialização reconciliado em 2026-07-30: o usuário autorizou
reiniciar manualmente a máquina para recuperar o driver após `NVRM Xid 31`.
Não usar reset de GPU ou unload privilegiado enquanto a interface gráfica
utiliza a placa. Depois do reboot, validar o preflight Leonidas e
`torch.cuda.is_available()` antes de repetir o smoke Parakeet CUDA. A decisão
de licença XTTS continua independente e pendente.

O usuário confirmou que o reboot foi concluído. A ordem obrigatória agora é
diagnóstico pós-boot, preflight e somente então smoke CUDA do Parakeet, sem
declarar recuperação antes da evidência desses comandos.

Input pós-suspensão reconciliado em 2026-07-30: após retirar o notebook da
tomada e suspender o sistema, verificar novamente a saúde CUDA com uma operação
PyTorch real e correlacionar o journal com suspend/resume e `NVRM Xid`.
Inspecionar parâmetros do módulo NVIDIA, backing store e estado dos serviços
`nvidia-suspend`, `nvidia-resume` e `nvidia-hibernate`. Separar evidência de
causalidade entre alimentação AC e suspensão. Esta é uma etapa diagnóstica:
não alterar configuração privilegiada, initramfs, serviços ou resetar a GPU
antes de identificar a causa e obter autorização explícita para a correção.

Resultado do diagnóstico pós-suspensão: a GPU ainda aparece no `nvidia-smi`,
mas a primeira operação CUDA real falha e produz `NVRM Xid 31`/MMU Fault. O
journal mostra o mesmo padrão em dois boots: suspend/resume e falha posterior
ao primeiro uso CUDA. Os hooks systemd NVIDIA estão habilitados e executam, mas
`PreserveVideoMemoryAllocations=0`; portanto falta a configuração exigida pela
documentação NVIDIA para preservação integral de VRAM e UVM/CUDA. O backing
store recomendado para 6 GiB é ao menos 6.452 MiB, enquanto os datasets do pool
do sistema têm somente 3,02 GiB disponíveis. `/tmp` e `/var/tmp` suportam
arquivo temporário sem nome; o outro pool tem espaço, mas está degradado e não
deve virar dependência de suspend.

Próxima correção segura: reboot recupera o estado imediato. Para prevenir nova
falha, primeiro prover espaço confiável, então configurar
`NVreg_PreserveVideoMemoryAllocations=1` e um `NVreg_TemporaryFilePath`
dimensionado, reconstruir initramfs, reiniciar e validar uma operação CUDA
antes/depois de suspend. Essa alteração privilegiada não foi aplicada e requer
autorização explícita.

Input da WebUI na porta 8081 reconciliado em 2026-07-30: o erro `Origin not
allowed` foi reproduzido e atribuído à allowlist fixa do `http_server`, que só
aceitava 8000/5173. Corrigir para calcular a origem local com a porta efetiva
do servidor, mantendo rejeição de origens externas. Adicionar testes de
regressão para origem same-origin em porta não padrão e origem proibida; não
abrir CORS global nem alterar o bind localhost.

Execução de observabilidade local reconciliada em 2026-07-30: Gemini 2.5/3.1
estão funcionais e são regressão obrigatória. A cascata deve passar a carregar
Parakeet e XTTS ao pressionar Start, retornar `starting` sem bloquear a UI,
publicar readiness/estágio/device/VRAM/erro por componente e somente entrar em
`running` após warm-up real. O usuário escolheu manter os modelos residentes
até encerrar o Leonidas, sem preload ou unload manual. Parakeet passa a worker
persistente na `.venv` principal; XTTS mantém `.venv-xtts`. Corrigir o feedback
de logs/polling que trava a UI e validar áudio real ponta a ponta.

A tentativa inicial de diagnóstico foi interrompida e não constitui evidência.
Após o comando de continuação do usuário, repetir diagnóstico e preflight por
completo antes de iniciar o smoke real.

Diagnóstico repetido: CUDA recuperado e operação PyTorch na RTX 2060 aprovada.
O preflight passou todos os itens disponíveis, exceto o aceite humano XTTS. O
usuário pediu como aceitar: orientar o downloader interativo e deixar claro que
`y` só deve ser informado se houver licença comercial aplicável ou concordância
com a CPML para uso não comercial; o agente não aceita em nome do usuário.

O smoke Parakeet CUDA carregou o modelo, mas falhou por `input_features` FP32
contra pesos/bias FP16. Classificar como bug confirmado do adapter, adicionar
teste de regressão e corrigir antes de repetir o smoke; não atribuir a falha ao
driver CUDA.

O usuário declarou que o XTTS será usado de forma não comercial sob a CPML e
autorizou explicitamente o agente a confirmar o prompt. Executar o downloader
interativo oficial, responder `y`, validar o marcador criado pelo próprio
Coqui e realizar o smoke de síntese. A autorização não cobre uso comercial.

O usuário solicitou a medição de VRAM do Parakeet e confirmação da versão. O
modelo configurado é `nvidia/parakeet-tdt-0.6b-v3`; medir pico alocado/reservado
durante inferência CUDA corrigida e verificar em fonte oficial se v3 permanece
a versão publicada mais recente, sem inferir isso apenas do nome.

Evidência obtida: Parakeet v3 CUDA PASS, 83 caracteres em 8,12 s, com pico
PyTorch de 1,205 GiB alocados e 1,238 GiB reservados. A model card oficial da
NVIDIA declara v3 como a versão corrente do TDT 0.6B multilingual.

Gate de revisão encontrou hang em erro de provider com input realtime aberto.
Regressão falhou por timeout antes da correção e passou depois que a exceção
foi encaminhada à fila de saída e a task de resposta passou a ser recolhida no
cleanup. Suíte atual: 70 passed/2 live skipped, Pyink/Flake8 verdes; UI 11
passed mais typecheck/build.

Aceite CPML não comercial foi confirmado pelo downloader oficial. XTTS baixou
1,87 GB e sintetizou fala real em CUDA em 2,645 s. O primeiro E2E encontrou
resposta JSON de áudio maior que o limite default de 64 KiB; regressão realista
de 70.000 bytes falhou antes e passou após definir limite bounded de 64 MiB.

E2E real completo passou: Parakeet → Groq → XTTS em CUDA, 89 caracteres de
transcrição, 77 de resposta, 7,84 s de PCM e 49,40 s total. Memória simultânea:
1.376 MiB Parakeet + 2.084 MiB XTTS = 3.460 MiB. Cleanup deixou zero processos
`cascade_smoke`/`xtts_worker` órfãos.

Cancelamento XTTS empírico passou com cleanup em 2,02 s e zero worker órfão.
Gate final: 70 passed/2 live skipped, 11 Vite passed, typecheck/build,
Pyink/Flake8, preflight completo e diff check verdes. Revisar stage sem
`.agents/`, `resources/`, `leonidas_draft.md`, pesos, voz ou runtime; então
criar commit e tag anotada do milestone cascata.

Stage final revisado e limpo de artefatos privados/não relacionados. O
checkpoint desta execução cria o commit cascata e a tag anotada
`leonidas-v0.2.0`.

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
- Parakeet/Transformers 5 permanece no ambiente principal; XTTS/Coqui usa
  `.venv-xtts` e subprocesso persistente devido ao conflito comprovado de API
  do Transformers. Monkey patches e downgrade do Parakeet são proibidos.
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
9. Implementar, testar e integrar Parakeet v3, Groq reasoning e XTTS v2,
   isolando XTTS em ambiente/processo próprio conforme decisão de runtime.
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
- Milestone Gemini commitado em `85f5d9b` e tagueado com a tag anotada
  `leonidas-v0.1.0`; a implementação cascata começa após esse boundary.
- Evidência cascata parcial 2026-07-30: 49+ testes Python e 10 testes Vite
  verdes; Groq GPT-OSS 20B real respondeu em 0,31 s; referência de voz Gemini
  TTS validada com 10 s; CUDA RTX 2060/5,78 GiB e runtime XTTS isolado
  importaram corretamente. O usuário autorizou explicitamente a CPML para uso
  não comercial; aceite, download e smoke XTTS podem prosseguir.
- Parakeet v3 real passou em CPU (723 blocos, 83 caracteres, semântica válida,
  19,32 s). Após reboot, CUDA voltou a funcionar; o bug FP32/FP16 foi coberto
  por regressão e corrigido. Smoke CUDA passou em 8,12 s, pico 1,205 GiB
  alocado/1,238 GiB reservado.

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

## Evidência da revisão 0041

- Readiness/UI concluídos em 2026-07-30: workers persistentes Parakeet/XTTS,
  start local assíncrono, snapshots REST/WS, cartões GPU/VRAM, estágios de
  turno, logs em lote e backoff de segunda aba.
- E2E CUDA canônico passou com transcript de 89 caracteres, 3,15 s de áudio e
  cleanup limpo. Gemini 2.5 e 3.1 passaram novamente no cenário live real.
- O bug em que o `id` privado do worker XTTS substituía o componente canônico
  `tts` foi coberto por regressão e corrigido antes do checkpoint.
