# Implementar e validar o agente Leonidas

## Escopo ativo após decisão do usuário — 2026-08-01

Codex foi explicitamente removido do objetivo. As seções Codex deste arquivo
permanecem somente como histórico e não são acceptance criteria, blockers ou
trabalho futuro deste goal. Não modificar a integração Codex existente. A
conclusão deve provar Gemini Live 2.5/3.1, Parakeet v3 → Groq → XTTS v2,
diarização Pyannote opcional, coexistência CUDA, cleanup, observabilidade,
API/WebSocket, WebUI responsiva e E2E com mídia demo. Reconciliar qualquer item
posterior que ainda cite Codex como gate segundo esta decisão mais recente.

Prioridade operacional reafirmada: não executar mais testes ou trabalho Codex.
Começar pelos E2E de diarização e cascata local, depois Gemini, API/WebSocket,
observabilidade e UI. Ausência de login/token Hugging Face bloqueia somente o
load dos pesos Pyannote; deve produzir erro acionável e não interromper as
demais validações.

Diarização fica restrita à cascata local. Não inserir Pyannote em Gemini Live.
Na cascata, falha/timeout da diarização deve preservar Parakeet → Groq → XTTS.
A primeira repetição do E2E encontrou GPU saudável com 5.914 MiB livres, mas
somente 2.179 MiB de RAM; o guard XTTS recusou o load abaixo do mínimo de
5.120 MiB. Manter o guard e repetir após liberar RAM ou configurar swap.

Ao obter diarização, construir o input interno do Groq como
`Speaker N falou: <transcrição>` usando associação temporal real entre segmentos
e texto. Não alterar o texto exibido na UI. Sem speaker confiável, preservar a
transcrição original e sinalizar fallback; nunca inventar identidade. Cobrir
speaker único, múltiplos speakers, ausência, atraso e erro com testes.

O fixture anterior de tons foi substituído por um corpus privado Gemini TTS
com vozes Kore/Puck, 10,44 s e silêncio de endpointing. O corpus passou os
contratos de WAV/manifesto; a execução Pyannote continua bloqueada apenas pelo
acesso gated do Hugging Face.

Checkpoint de speaker context: STT/Pyannote rodam concorrentemente; speaker
único prefixa somente o prompt Groq, ambiguidade/erro/timeout mantém a
transcrição original, com numeração estável e métricas. Evidência: 42 testes
diretos, 174 Leonidas/E2E (2 skips, 9 subtests), 24 Vitest, typecheck/build e
Gemini Live 2.5/3.1 real em 39,97 s. A cascata CUDA continua bloqueada pelo
guard de RAM do host, apesar de 5.914 MiB de VRAM livre.

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

### Reconciliação do requisito de autenticação Codex — 2026-08-01

O usuário determinou que `codex_realtime` deve usar as credenciais Codex de
`.codex/auth.json` e solicitou análise de `~/github/codex`. A exigência
anterior de `OPENAI_API_KEY` separada deixa de ser uma conclusão: deve ser
confirmada ou substituída pela API mais recente. Preservar o arquivo somente
no servidor, não converter tokens, não expor segredos e cobrir o fluxo real de
`CODEX_HOME`/`auth.json` com testes e smoke opt-in redigido.

### Resultado da análise do checkout Codex — 2026-08-01

Foi analisado `/home/guilherme/github/codex`, branch
`feature/turn-pinning-validation`, commit `33bf318bd7`, além do binário local
`codex-cli 0.144.0`. O schema `AuthDotJson` em
`codex-rs/login/src/auth/storage.rs` confirma `auth_mode`,
`OPENAI_API_KEY` e `tokens` de login. Porém, em
`codex-rs/core/src/realtime_conversation.rs`, `realtime_api_key()` só aceita
API key do provider, `experimental_bearer_token` configurado no provider,
API key do Codex ou `OPENAI_API_KEY` do ambiente; tokens ChatGPT de
`auth.json` não são convertidos nem aceitos diretamente. O realtime prepara
o provider com `AuthMode::ApiKey` e devolve
`realtime conversation requires API key auth` quando não encontra material
compatível.

Decisão: o adapter sempre deve encaminhar o `auth.json` server-side por meio
de `CODEX_HOME` e aceitar `OPENAI_API_KEY` quando esse campo existe. Um login
ChatGPT válido no mesmo arquivo continua suficiente para `codex_text`, mas
não é suficiente para o WebSocket `codex_realtime` no checkout atual. Não
converter `access_token`/`id_token`, não fazer replay de cookies ou tokens
privados e não inventar um bypass de entitlement. O realtime deve emitir um
erro acionável diferenciando credencial inválida de credencial de login válida
sem API key para o transporte WebSocket. Quando o cliente fornecer uma oferta
SDP, o adapter deve escolher WebRTC em vez de converter tokens. Só um smoke
WebSocket com API key compatível ou um smoke WebRTC com login ChatGPT pode ser
marcado como realtime verde; isso não altera o pipeline Gemini/Groq/local.
O README/protocolo mais novo também confirma `transport: {type: "webrtc", sdp}`:
o navegador cria a oferta, o app-server cria a chamada autenticada e emite a
resposta em `thread/realtime/sdp`; o código do checkout documenta que o
sideband WebSocket reutiliza os headers da autenticação da sessão, inclusive
para login ChatGPT. Portanto, o caminho para cumprir realtime com login do
`auth.json` é WebRTC + sinalização SDP, não a conversão de tokens para API key.
Não converter `access_token`/`id_token`, não fazer replay de cookies ou tokens
privados e não inventar bypass de entitlement. WebSocket fica como transporte
compatível para `OPENAI_API_KEY`; o realtime ChatGPT deve ter smoke real via
WebRTC antes de ser marcado verde.

### Requisito adicional: sinalização WebRTC Codex — 2026-08-01

Para cumprir realtime com o login presente em `auth.json`, implementar
sinalização SDP pelo WebSocket local: oferta do navegador para o backend e
resposta emitida pelo backend após `thread/realtime/sdp`. Usar envelopes
tipados `application/x-codex-webrtc-offer`/`application/x-codex-webrtc-answer`,
com limite de tamanho, estados de conexão, timeout, stop/reset e testes. O
navegador deve enviar microfone como WebRTC track e reproduzir a track remota,
sem duplicar PCM pelo WebSocket. Credenciais nunca atravessam a UI e Gemini,
cascata e WebSocket/API-key permanecem inalterados.

Implementação local concluída: o backend valida e limita o envelope de oferta,
o processor inicia WebRTC com `v1`, devolve a resposta SDP e evita emitir
áudio PCM do sideband quando a track remota já está ativa. A WebUI cria
`RTCPeerConnection`, `oai-events`, microfone e reprodução remota, com timeout,
erro e cleanup. Typecheck, build, 22 testes Vitest e regressões Python
passaram. Falta somente o smoke empírico em navegador com o `auth.json` real;
não marcar realtime ChatGPT como verde antes dessa prova.

Smoke Chromium real executado: `RTCPeerConnection`, microfone fake, data
channel `oai-events`, oferta SDP e sinalização pelo WebSocket local chegaram ao
upstream. A conta Codex respondeu `403 Voice session access denied`; a UI agora
recebe apenas diagnóstico sanitizado, sem URL/request id/headers. O binário
local `codex-cli 0.144.0` aceita v1/v2, então o default do pipeline foi ajustado
para v2 no WebSocket e v1 é escolhido automaticamente para WebRTC; v3 segue
opt-in quando o schema instalado o suportar. O acesso upstream de voz ainda é
o gate externo antes de declarar realtime ChatGPT funcional.

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
essa revisão final e os testes da composição. A integração pública foi
posteriormente conectada como `codex_realtime` e `codex_text`; este trecho
registra o estado anterior ao checkpoint.

O loader server-side passou a validar e encaminhar somente a
`OPENAI_API_KEY` de `auth.json` para o processo Codex; tokens ChatGPT não são
tratados como API key. O smoke real com o `auth.json` local foi executado e
falhou sem vazar segredo: o arquivo está em `auth_mode=chatgpt`, sem
`OPENAI_API_KEY`, e o app-server exige API key para realtime. Repetir o smoke
é obrigatório depois de configurar uma credencial compatível.

O subprocesso não depende mais do `~/.codex/config.toml` global: usa um
`CODEX_HOME` temporário com link para o auth original. O smoke atual falha
antes do spawn, de forma segura, quando a API key compatível não está presente.

O mesmo `auth.json` foi validado em um smoke real de texto do app-server:
handshake, thread efêmero, turn textual, deltas e conclusão retornaram com
sucesso. A implementação deve expor isso como `pipeline_id=codex_text`, sem
transformar falha de `codex_realtime` em fallback implícito e sem prometer
áudio/voz nessa capacidade. O smoke textual deve ser repetível sem imprimir o
conteúdo da resposta ou qualquer credencial; o smoke atual passou com resposta
não vazia.

O recurso opcional de diarização também aparece no snapshot/API/UI como
`unavailable` ou `unloaded`, sem degradar a prontidão STT/TTS. A suíte completa
Leonidas/E2E passou com 139 testes, 2 skips e 9 subtests.

Auditoria ampla: a suíte completa passou com 709 testes, 2 skips e 27
subtests; flake8 restrito passou sem `.venv`/artefatos; os 21 arquivos Python
alterados passaram no Pyink. O Pyink global ainda reporta 37 arquivos antigos
fora desta mudança e eles não foram reformatted.

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

## Próxima onda de continuidade — diarização configurável e smoke real

Auditoria identificou que `CascadeConfig.diarization_enabled` já existe no
backend, mas ainda não tem controle correspondente na WebUI. O próximo
checkpoint deve adicionar esse controle, um teste de contrato com áudio PCM
sintético de dois falantes e um runner opt-in para o adapter Pyannote. O runner
deve falhar explicitamente quando dependência, pesos ou credencial Hugging
Face estiverem ausentes; nunca deve substituir o resultado por um fake e nunca
deve bloquear Gemini ou a cascata com diarização desativada.

Verificação de dependências: o dry-run de `pyannote.audio==4.0.7` tentou
resolver uma versão nova de Torch incompatível com o runtime validado do
Parakeet (`torch 2.6.0+cu124`), e foi cancelado antes de modificar o ambiente.
`pyannote.audio==3.4.0` declara compatibilidade com Python 3.13 e Torch >=2.0,
mas suas dependências opcionais não estão instaladas e os pesos do modelo
`pyannote/speaker-diarization-community-1` ainda exigem acesso Hugging Face.
O suporte permanece opt-in até existir um ambiente isolado validado para esse
adapter.

O smoke real do Codex textual foi ampliado para dois turnos no mesmo thread:
`codex_text_smoke_ok=true turns=2`, resposta não vazia e latência total de
13,22 s. Isso confirma persistência de conversa no app-server com o login
ChatGPT local, além do contrato offline de lifecycle.

O acesso anônimo aos manifests de `pyannote/speaker-diarization-community-1`
e `pyannote/speaker-diarization-3.1` retornou HTTP 401 neste host. Portanto o
smoke real da diarização depende também de login/aceite de modelo no Hugging
Face, além da instalação compatível; nenhum token foi solicitado, lido ou
registrado pelo Leonidas.

Auditoria final desta rodada: a suíte completa do repositório passou com 716
testes, 2 skips e 27 subtests em 144,5 s; Pyink dos arquivos alterados,
Flake8 restrito e `git diff --check` também passaram. Nenhuma tag estável nova
foi criada porque o smoke real Pyannote e o Codex realtime nativo permanecem
gates externos não verdes.

Validação pós-diarização: o standalone em `web_port=8081` e
`websocket_port=8876` aceitou a origem local não padrão, anunciou quatro
pipelines e três componentes e entregou os dois envelopes iniciais pelo
WebSocket. Gemini 2.5/3.1 passou novamente em 34,4 s. O smoke CUDA local passou
em três turnos reais (`6,06 s`, `6,07 s` e `4,39 s` de PCM); o validador foi
ajustado para exigir somente STT/TTS prontos e aceitar o componente opcional de
diarização.

### Decisão de isolamento do worker de diarização

Para não substituir o Torch validado do Parakeet, o adapter Pyannote deve
rodar em um processo/runtime opcional próprio, selecionado por
`LEONIDAS_DIARIZATION_PYTHON`. O servidor principal mantém apenas o contrato
JSONL e `ProcessorPart`; o worker é responsável por carregar Pipeline, CUDA,
pesos e converter os segmentos. Ausência do executável ou falha do worker
permanece um erro de recurso observável e não altera Gemini nem a cascata sem
diarização.

Implementação do isolamento: `diarization_process.py` e
`diarization_worker.py` agora usam o mesmo protocolo JSONL dos workers locais,
com `LEONIDAS_DIARIZATION_PYTHON` configurável, progresso de load, segmentos
validados e shutdown. A suíte Leonidas/E2E passou com 148 testes, 2 skips e 9
subtests. O smoke real continua bloqueado somente pela ausência do runtime
opcional/pesos Hugging Face.

Após a implementação do worker, a auditoria completa passou com 718 testes,
2 skips e 27 subtests em 143,6 s; WebUI passou com 22 testes, typecheck e
build; Pyink dos 11 arquivos alterados, Flake8 restrito e `git diff --check`
passaram. O smoke real Pyannote ainda retorna `DiarizationWorkerError` antes
do load porque o runtime isolado não existe neste host.

O loader Codex agora rejeita de forma redigida arquivos cujos JWTs conhecidos
estão todos expirados, sem validar ou expor assinaturas/claims. A regressão
sintética passou e o `codex_text` smoke real com o `auth.json` atual passou
novamente em um turno (`response_chars=8`, 9,16 s).

### Continuação: diarização instalável e bloqueio explícito — 2026-08-01

O host foi reavaliado antes de qualquer instalação: CUDA enumera a RTX 2060,
há cerca de 4 GiB de RAM disponível, não existe `.venv-diarization` e não há
token Hugging Face no cache local. Foi criado o instalador
`leonidas/cascade/install_diarization.sh`, isolando Torch 2.6/cu124 e
`pyannote.audio==3.4.0` do ambiente Parakeet. A capability/API/UI agora
expõem o caminho e o comando de setup sem expor credenciais. A instalação e o
smoke Pyannote real continuam um gate externo até o usuário configurar acesso
ao modelo; não substituir esse smoke por um fake.

### Requisito futuro: reescrita completa da WebUI e mobile — 2026-08-01

Depois de finalizar os gates do backend atual, implementar uma nova WebUI
completa tomando `resources/ui_002/` como inspiração visual e de fluxo. A
frente não pode presumir uma API nova: deve primeiro auditar a referência,
mapear as telas para os contratos REST/WS atuais e atualizar
`leonidas/UI_SPECS.md`. A UI continuará em Vite + TypeScript e deverá manter
Gemini 2.5/3.1, cascata Parakeet/Groq/XTTS, Codex text/realtime explícitos,
configuração, lifecycle, logs, métricas, readiness e diarização opcional.

O suporte mobile é requisito de aceite, não apenas um breakpoint: testar
viewport estreito, touch, teclado virtual, orientação, permissões de mídia,
preview, reprodução PCM, reconexão e ausência de overflow horizontal. A
reescrita deve incluir testes Vitest/contrato, typecheck, build e inspeção
visual desktop/mobile. Não versionar assets privados, logs, capturas ou
credenciais de `resources/ui_002`.

O runtime isolado foi instalado e validado com Torch `2.6.0+cu124`, Pyannote
`3.4.0`, `huggingface_hub==0.36.2` e CUDA disponível. O smoke real chegou ao
modelo e confirmou a dependência externa de acesso/autorização Hugging Face;
quando `Pipeline.from_pretrained` retorna `None`, o worker agora publica erro
redigido e acionável, sem `AttributeError` enganoso.

Durante a instalação da diarização, o primeiro smoke encontrou uma
incompatibilidade concreta: `pyannote.audio==3.4.0` usa `use_auth_token`,
removido em `huggingface_hub==1.26.0`. O instalador deve fixar
`huggingface_hub<1.0` e repetir o smoke; somente depois desse ajuste o erro de
acesso/peso do modelo pode ser classificado como bloqueio externo.

Validação posterior: o runtime isolado passou `pip check`, import de Pyannote
e CUDA; o smoke real chegou ao modelo e falhou apenas por ausência de
autorização ao pipeline gated. A suíte Leonidas passou com 151 testes, 2 skips
e 9 subtests; a cascata real CUDA passou em três turnos e Gemini Live passou
nos dois perfis. O próximo trabalho de implementação continua sendo a frente
UI mobile, conforme o requisito futuro registrado acima.

Compatibilidade Codex atualizada: o checkout mais recente aceita WebRTC AVAS
em `v1` e `v3`, mas rejeita `v2` nesse transporte. O adapter aceita `v3` por
opt-in via `LEONIDAS_CODEX_REALTIME_VERSION=v3`; sem esse opt-in, a oferta
WebRTC usa `v1`, compatível com o `codex-cli 0.144.0` instalado. O caminho
WebSocket continua usando `v2` por padrão.

Correção de método: a tentativa de `cargo build` do `codex-cli` no checkout
mais novo foi descartada. Esse checkout deve ser lido somente para entender
schemas, eventos e autenticação; não é alvo de build ou teste do produto. A
validação deve exercitar diretamente a API do app-server implementada no
Leonidas, com contrato offline e smoke real redigido. O target temporário foi
limpo sem alterar checkout, código Leonidas, `auth.json` ou binário instalado.

Checkpoint UI v2 iniciado: após auditar `resources/ui_002`, a WebUI foi
reorganizada em Operação, Configuração e Diagnóstico sem alterar os IDs dos
controles existentes nem os contratos do backend. A navegação suporta teclado,
touch e layout mobile; a inspeção Chromium passou em 1440×1000 e 390×844.
Typecheck, 24 testes Vitest e build Vite passaram. O backend ainda precisa
seguir a regressão Python antes do checkpoint ser considerado completo.

## Onda ativa: compatibilidade integral da API Codex — 2026-08-01

Continuar até o adapter Leonidas refletir os contratos observáveis do
app-server atual e funcionar com o `auth.json` local em todos os transportes
que essa credencial e a conta autorizarem. O contrato corrente exige:

1. requests JSONL com handshake obrigatório e parâmetros camelCase exatos;
2. `appendText.role` explícito para novos clientes;
3. áudio como chunk estruturado (`data`, `sampleRate`, `numChannels`,
   `samplesPerChannel`, `itemId` opcional);
4. tratamento terminal de `thread/realtime/error` e
   `thread/realtime/closed`, além de SDP, started, transcript, item e áudio;
5. descoberta/validação da versão e das vozes no runtime, sem anunciar v3 como
   operacional no binário 0.144.0;
6. WebSocket v2 somente com API key compatível e WebRTC v1/v3 para login
   ChatGPT, sem converter ou expor tokens de `auth.json`;
7. testes offline Red-Green-Refactor e smokes reais redigidos de texto e voz.

Critério de conclusão: nenhuma divergência conhecida entre requests,
notifications, versões, vozes, lifecycle e autenticação; suites relevantes e
smoke textual verdes; smoke realtime verde ou evidência conclusiva de que a
única falha restante é autorização upstream da conta, depois de esgotar as
rotas suportadas sem hacks. Preservar Gemini 2.5/3.1 e a cascata local em todos
os checkpoints.

### Extensão empírica: áudio Gemini simulando microfone

Criar um corpus privado em `leonidas/.runtime/e2e/codex_audio/` usando Gemini
TTS, com pelo menos duas falas PT-BR e manifesto técnico redigido. Implementar
runner opt-in que converta as fixtures para PCM16 mono, envie chunks com pacing
de microfone em múltiplos turnos e verifique lifecycle, transcrição, saída de
áudio/resposta, stop e cleanup. Exercitar WebSocket/`appendAudio` quando houver
API key compatível e WebRTC com track alimentada pelo corpus quando o login
ChatGPT tiver entitlement. Não versionar áudio, transcript, resposta, token ou
payload; bloqueios upstream devem ser reportados como evidência real, não
mascarados por mocks.

### Evidência da onda de compatibilidade Codex

- corpus Gemini privado: dois WAVs, 9,36 s totais, manifesto técnico redigido;
- `listVoices` real no app-server 0.144.0: 9 vozes V1, 10 V2 e defaults
  consistentes;
- áudio WebSocket V1/V2: bloqueado antes de mídia por `api_key_required`;
- áudio WebSocket V3: bloqueado pelo schema 0.144.0 como
  `protocol_version_unsupported`;
- WebRTC V1 em Chromium com WAV como microfone: oferta SDP real chegou ao
  upstream e falhou antes da mídia com `voice_entitlement_denied`;
- smoke WebRTC automatizado: os dois WAVs são combinados com silêncio de
  endpointing, Chromium aguarda REST/WebSocket prontos e reproduz o mesmo
  `voice_entitlement_denied` sem registrar SDP, resposta ou credencial;
- Codex Text com o mesmo `auth.json`: 2 turnos verdes em 12,17 s;
- regressões: 168 testes Python + 9 subtests, 24 Vitest, typecheck e build;
- baseline preservado: cascata CUDA 3 turnos verde em 46,45 s, sem workers
  órfãos; Gemini Live 2.5/3.1 verde em 43,97 s.

O adapter agora envia `appendText.role`, valida vozes descobertas por versão,
trata `error`/`closed` como terminal, rejeita versões desconhecidas e não envia
o modelo V1/V2 ao protocolo V3. O código local não possui outra rota
autorizada para atravessar os gates upstream atuais sem API key ou entitlement;
não converter tokens nem chamar endpoints privados fora do app-server.

Revalidação de fonte em 2026-08-01: o checkout
`/home/guilherme/github/codex` está em `91f3c3824` e confirma no contrato/teste
do app-server o modelo `gpt-realtime-1.5`, POST WebRTC AVAS, headers derivados
do login ChatGPT e resposta `thread/realtime/sdp`. O binário disponível para a
integração continua 0.144.0; portanto o smoke usa V1, voz retornada por
`listVoices` e o app-server instalado. Não compilar nem executar o checkout
Codex como substituto do produto: ele é fonte de contrato; a validação real é
feita exclusivamente pelo adapter Leonidas contra a API do app-server.

Correção da auditoria de escopo: JSONL com `codex app-server` não substitui o
transporte direto solicitado pelo usuário. Implementar no Leonidas um cliente
server-side para o backend HTTP/WebRTC confirmado em `~/github/codex`, usando
somente as credenciais de `auth.json`, com autenticação, account header,
multipart/SDP, sideband, timeout, cancelamento, refresh/expiração, sanitização e
testes de contrato próprios. O checkout Codex permanece read-only e nunca deve
ser compilado/executado para validar Leonidas. Preservar o adapter app-server
como capability separada até o transporte direto passar smoke real. O release
oficial isolado 0.146.0 confirmou texto em dois turnos; V1 continuou bloqueado
por entitlement e V3 repetiu timeout, portanto atualização de binário não
resolveu a autorização da conta.

### Gate adicional: Parakeet + XTTS + Pyannote simultâneos

Validar empiricamente os três workers no mesmo host/GPU antes de afirmar que a
diarização cabe na RTX 2060 de 6 GiB. Pico recente medido: Parakeet 1.358 MiB e
XTTS 2.034 MiB, total 3.392 MiB e margem nominal próxima de 2,5 GiB. A margem
não inclui pesos Pyannote, buffers temporários, contexto CUDA ou fragmentação.
Critério: load/warm-up conjunto, diarização real, três turnos completos, sem
OOM e com cleanup. Sem acesso ao modelo gated, classificar como não provado.
