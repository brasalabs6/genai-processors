# Plano de execução — Leonidas

Versão: 20260730-0041

## Escopo ativo após decisão do usuário — 2026-08-01

A integração Codex foi retirada do objetivo por decisão explícita do usuário.
Todas as seções Codex abaixo são registro histórico de trabalho já commitado,
não constituem gate, requisito pendente ou frente autorizada. Não ampliar,
corrigir ou validar Codex durante este goal. O escopo ativo passa a ser:
Gemini Live 2.5/3.1, cascata Parakeet v3 → Groq → XTTS v2, diarização Pyannote,
coexistência CUDA, observabilidade, API/WebSocket, WebUI desktop/mobile,
documentação e testes E2E. O código Codex existente permanece isolado e sem
fallback implícito; sua eventual remoção é uma decisão separada.

Prioridade reafirmada pelo usuário: Codex está adiado e não deve consumir mais
trabalho, inclusive testes. A execução deve atacar diretamente todo o restante
com validação end-to-end, começando por diarização e pela coexistência da
cascata local. Enquanto a autorização Hugging Face estiver ausente, comprovar
o comportamento offline/erro acionável da diarização e continuar Gemini,
Parakeet, Groq, XTTS, API, UI e cleanup; não usar Codex como regressão.

Fronteira de diarização confirmada pelo usuário: Pyannote pertence somente à
pipeline local nesta fase. Gemini Live 2.5/3.1 permanece sem diarização externa
e não pode ter seu transporte, VAD ou áudio alterado por esse componente. A
cascata local aplica diarização opcional depois do endpointing/STT e antes de
montar o contexto do Groq; indisponibilidade ou atraso da diarização preserva a
transcrição Parakeet e não bloqueia reasoning/TTS.

Contrato de contexto para reasoning: quando a diarização local produzir um
speaker válido, o texto enviado ao Groq deve ser prefixado como
`Speaker 1 falou: <transcrição>` (e correspondentemente `Speaker 2`, etc.). O
prefixo pertence somente ao prompt interno do reasoning; a transcrição original
permanece inalterada nos substreams/UI. Segmentos devem ser associados às
palavras/turnos por timestamps reais; não atribuir uma transcrição inteira a um
speaker arbitrário. Sem resultado de diarização, enviar a transcrição normal e
registrar o fallback observável.

O corpus E2E de diarização agora usa duas vozes humanas Gemini (`Kore` e
`Puck`), 10,44 s no total, com silêncio entre falantes e manifesto redigido. A
validação de assets passou; o Pyannote ainda falha antes da inferência por falta
de autorização Hugging Face, confirmando que mídia/formato não são o blocker.

Implementação tests-first concluída para o contexto de speaker: STT e
diarização executam em paralelo por utterance; um único speaker recebe número
estável e prefixa somente o prompt Groq; múltiplos speakers ambíguos preservam
o texto; erro/timeout gera fallback e métrica. Foram aprovados 42 testes
diretamente relacionados, 174 testes Leonidas/E2E (2 skips, 9 subtests), 24
Vitest, typecheck e build. Gemini 2.5/3.1 passou no smoke pago em 39,97 s. A
cascata CUDA foi tentada duas vezes e o guard XTTS bloqueou com 2.179/3.558 MiB
de RAM disponível; a GPU estava saudável com 5.914 MiB livres.

Primeira revalidação E2E desta fase: CUDA estava saudável e a GPU possuía
5.914 MiB livres, mas o guard XTTS interrompeu corretamente o load porque o
host tinha somente 2.179 MiB de RAM disponível, abaixo dos 5.120 MiB exigidos.
Isso é um gate ambiental de RAM, não falta de VRAM. Não reduzir o guard; liberar
memória ou prover swap antes de repetir os três turnos e a coexistência.

## Incidente de continuidade de áudio local — 2026-08-01

O usuário relatou que a pipeline local reproduz voz inicialmente, mas deixa
de emitir áudio depois de algum tempo. A investigação reproduziu uma falha de
infraestrutura que atualmente pode aparecer como silêncio na UI: o worker
XTTS terminou com `-9` durante o carregamento/aquecimento. O journal do kernel
registrou `global_oom` e matou um processo Python com 3,7 GiB de RSS enquanto
a máquina estava com apenas cerca de 4 GiB disponíveis e sem swap. Portanto,
o preflight anterior, que apenas importava `TTS`, não prova que o worker
consegue carregar e permanecer vivo.

Requisitos adicionais desta onda:

- distinguir explicitamente worker morto por OOM/kill, timeout, erro de
  protocolo e falha de playback;
- nunca deixar a UI aparentar que a sessão continua falando quando o backend
  perdeu o worker de áudio;
- expor a falha e a recuperação nos estados, métricas e logs, preservando o
  contrato `ProcessorPart`;
- adicionar regressões para worker encerrado e para múltiplos pedidos de áudio;
- validar a composição real em mais de um turno, com memória do sistema
  suficientemente livre para não confundir falha ambiental com falha da
  pipeline;
- manter Gemini 2.5/3.1 como regressão obrigatória.

O incidente não autoriza mascarar OOM com retries infinitos. A recuperação
deve ser limitada e observável; se a memória disponível for insuficiente, a
UI deve informar a causa e impedir novos turnos locais até o recurso estar
saudável.

## Requisito adicional: diarização local — 2026-08-01

O usuário reforçou que a evolução do agente deve incluir diarização. Ela será
um componente opcional da cascata local, com contrato próprio e sem bloquear o
caminho crítico de áudio:

- receber PCM endpointado ou janelas de áudio e emitir segmentos com
  `speaker_id`, início/fim e confiança;
- preservar a transcrição Parakeet mesmo quando a diarização estiver
  indisponível, atrasada ou em CPU;
- declarar device, VRAM/RAM, cache, versão de PyTorch/CUDA e fallback CPU;
- executar fora do event loop e fora do worker XTTS, com cancelamento e
  shutdown explícitos;
- aparecer na capability/configuração somente quando instalada e pronta;
- ter testes de contrato com áudio sintético multi-speaker e smoke real
  opt-in, sem tornar CI ou Gemini dependentes de pesos de diarização.

A implementação entra depois da correção de continuidade do áudio; até lá o
contrato permanece documentado para evitar acoplamento posterior ao Parakeet,
Groq ou XTTS.

## Requisito adicional: backend realtime do Codex — 2026-08-01

Ao final desta onda, analisar o documento
`Codex_App_Server_Realtime_API_Engenharia_Reversa.md` e verificar se o
contrato permite adicionar um adapter de backend realtime do Codex. O adapter
deve:

- ficar atrás da mesma composição/capability de modelos, sem quebrar Gemini,
  Groq ou os adapters locais;
- traduzir eventos para `ProcessorPart`, estados e cancelamento internos;
- manter credenciais e conexão do backend exclusivamente no servidor;
- documentar autenticação, limites, reconexão, streaming, áudio e lifecycle;
- ter contrato/testes offline antes de qualquer smoke opt-in real;
- ser implementado somente onde o documento e o código local confirmarem um
  protocolo estável; lacunas da engenharia reversa devem permanecer explícitas.

Atualização de fonte de verdade — 2026-08-01: o usuário informou que o
binário instalado pode estar desatualizado. Antes de congelar o adapter, também
devemos comparar o protocolo e os schemas em `~/github/codex` com o binário
local. A versão mais recente disponível no workspace passa a ser a referência
preferencial; diferenças entre ela, o binário e o documento devem ser
registradas e cobertas por testes, sem presumir suporte a versões futuras.

Autenticação — 2026-08-01: o adapter deve descobrir a autenticação local pelo
arquivo `~/.codex/auth.json` (ou pelo caminho equivalente configurado pelo
runtime), sempre no processo servidor. O conteúdo nunca pode aparecer em
logs, respostas HTTP/WebSocket, fixtures ou commits. O smoke real deve ser
opt-in, validar apenas handshake/lifecycle e relatar somente versão, estado e
latência; ausência, JSON inválido ou credencial expirada devem produzir erro
acionável sem quebrar Gemini/Groq.

### Reconciliação do requisito de autenticação Codex — 2026-08-01

O usuário esclareceu que o realtime deve usar as credenciais Codex presentes
em `.codex/auth.json`, e pediu uma análise de `~/github/codex` antes de novas
alterações. A hipótese histórica de exigir uma `OPENAI_API_KEY` separada fica
em revisão: não converter tokens de login, não inventar um fluxo OAuth e não
copiar segredos para o ambiente/UI. A implementação deve seguir o mecanismo
de autenticação confirmado pelo checkout mais recente e pelo documento de
engenharia reversa, com teste offline do encaminhamento de `CODEX_HOME`/
`auth.json` e smoke real redigido.

### Resultado da análise do checkout Codex — 2026-08-01

A análise foi feita no checkout `/home/guilherme/github/codex`, branch
`feature/turn-pinning-validation`, commit `33bf318bd7`, com o binário local
`codex-cli 0.144.0`. O checkout mais novo confirma que `auth.json` pode
conter `auth_mode`, `OPENAI_API_KEY` e/ou `tokens` (`id_token`,
`access_token`, `refresh_token` e `account_id`), mas esses materiais não têm
o mesmo significado para todos os serviços.

O ponto decisivo está em `codex-rs/core/src/realtime_conversation.rs`:
`realtime_api_key()` procura a API key do provider, o
`experimental_bearer_token` configurado no provider, a API key carregada pelo
Codex ou `OPENAI_API_KEY` do ambiente. Ele não transforma tokens de login
ChatGPT armazenados em `auth.json` em API key. Quando nenhum caminho existe,
retorna `realtime conversation requires API key auth`; o provider realtime é
preparado com `AuthMode::ApiKey`. O schema de `AuthDotJson` foi confirmado em
`codex-rs/login/src/auth/storage.rs`.

Conclusão operacional: o Leonidas deve sempre carregar o `auth.json` no
servidor via `CODEX_HOME`, e pode usar um `OPENAI_API_KEY` presente nele. Um
`auth.json` somente com login ChatGPT autentica o app-server e o pipeline
`codex_text`, mas não torna o WebSocket realtime funcional no Codex atual.
O README/protocolo mais novo confirma uma segunda opção: `transport` pode ser
`{type: "webrtc", sdp: "..."}`; o navegador cria a oferta SDP, o app-server
cria a chamada autenticada e emite `thread/realtime/sdp` com a resposta. O
código do checkout também documenta que o sideband WebSocket de uma chamada
WebRTC reutiliza os headers da autenticação da sessão, inclusive para login
ChatGPT.
Não será feita conversão de `access_token`/`id_token`, replay de cookie,
injeção de bearer privado ou alteração do provider para contornar essa
restrição. O adapter deve distinguir “auth.json ausente/inválido” de “login
válido, mas o transporte WebSocket exige API key”; quando o cliente fornecer
uma oferta SDP, deve selecionar WebRTC em vez de tentar converter o login.

Assim, o suporte realtime por WebSocket continua válido quando o `auth.json`
contém API key compatível, enquanto o suporte realtime com login ChatGPT deve
ser implementado pelo caminho WebRTC e sua sinalização SDP. Não converter
`access_token`/`id_token`, replay de cookie, injeção de bearer privado ou
alteração do provider para contornar a restrição do WebSocket. O suporte
textual com login ChatGPT permanece separado e validado.

### Requisito adicional: sinalização WebRTC Codex — 2026-08-01

Para permitir `codex_realtime` com o login existente em `auth.json`, a UI e o
servidor devem trocar somente a oferta/resposta SDP pelo canal de controle;
credenciais e conexão upstream continuam no app-server. O envelope deve ser
explicitamente tipado (`application/x-codex-webrtc-offer` e
`application/x-codex-webrtc-answer`), limitado em tamanho e rejeitado por
Gemini/cascata como input de mídia comum. A UI deve:

- criar `RTCPeerConnection` apenas para `codex_realtime` e versão WebRTC
  suportada (`v1`), com microfone em track e reprodução no elemento de áudio;
- enviar a oferta SDP pelo WebSocket já autenticado localmente;
- aplicar a resposta SDP recebida, tratar `connectionstatechange`, timeout,
  stop/reset e permissão de microfone;
- manter câmera/tela e mensagens de texto sob o contrato existente, sem
  duplicar áudio PCM pelo WebSocket quando o transporte WebRTC estiver ativo;
- testar o envelope, as transições e o fallback explícito para WebSocket/API
  key. Não enviar `auth.json`, bearer ou cookies ao navegador.

Implementação inicial concluída nesta onda: o backend aceita a oferta como
`ProcessorPart` limitado, o `CodexRealtimeProcessor` a consome antes de abrir
a sessão, força versão `v1` no transporte WebRTC e emite a resposta como
`application/x-codex-webrtc-answer`; o áudio recebido pelo sideband é
descartado nesse modo para não duplicar a track remota. A UI criou
`RTCPeerConnection`, o data channel `oai-events`, a track de microfone, o
reprodutor remoto e timeout/cleanup de sinalização. O caminho PCM/WebSocket e
Gemini permanecem inalterados. O smoke real de navegador ainda é pendente e
deve ser executado com a UI standalone e o `auth.json` local antes de marcar
este transporte como verde.

Smoke Chromium real — 2026-08-01: com `RTCPeerConnection`, dispositivo de
áudio fake, data channel `oai-events` e SDP real, a oferta chegou ao backend e
o pipeline alcançou a chamada upstream. O serviço respondeu `403 Voice session
access denied` para a conta Codex local; o erro agora é sanitizado para a UI
sem URL, request id ou headers. O app-server instalado (`codex-cli 0.144.0`)
também aceita somente v1/v2; o pipeline usa v2 por padrão para WebSocket e
força v1 para WebRTC, enquanto v3 permanece opt-in para instalações cujo
schema o suporte. A autorização upstream de voz continua pendente e impede
marcar o smoke realtime como verde.

Compatibilidade do checkout mais recente — 2026-08-01: o código em
`~/github/codex` aceita WebRTC AVAS nas versões `v1` e `v3`; `v2` continua
exclusivo do transporte WebSocket. O adapter agora aceita `v3` quando
`LEONIDAS_CODEX_REALTIME_VERSION=v3` for definido, mas mantém `v1` automático
para WebRTC quando a versão não for `v3`, preservando o binário local
`codex-cli 0.144.0`. O smoke com v3 permanece condicionado a um binário que
publique esse schema e a uma conta com entitlement de voz.

## Governança de checkpoints e versões estáveis — 2026-08-01

Cada checkpoint funcional deve ser commitado com mensagem detalhada antes de
abrir a próxima frente. Milestones que passam seus gates offline e reais devem
receber tag anotada versionada; a tag só pode ser criada depois de validar o
estado, revisar o diff e confirmar que nenhum artefato privado foi incluído.
Falhas, bloqueios ambientais e requisitos ainda não implementados permanecem
fora de tags estáveis.

### Evidência desta onda

- Reprodução real do defeito: worker XTTS terminou com `-9`; journal confirmou
  `global_oom`, 3,7 GiB de RSS e ausência de swap.
- Implementado guard de memória antes do load real, com limite padrão de
  5120 MiB e override explícito `LEONIDAS_XTTS_MIN_AVAILABLE_MEMORY_MIB`.
- Implementados tipos de erro para recurso insuficiente e crash transitório,
  retry único somente para crash não classificado como OOM, e
  `last_error_detail` seguro na sessão/UI.
- Regressão XTTS de SIGKILL passou; cascata offline: 128 passed, 2 skipped.
- WebUI: 22 testes, typecheck e build passaram.
- Gemini Live 2.5/3.1 passou no smoke real com mídia gerada em 30,3 s.
- Smoke local multi-turno permanece pendente até liberar memória do host;
  o preflight atual falha corretamente com `memory_available_mib=1801` e
  `system_memory=missing`, sem iniciar outro worker condenado ao OOM.

O host foi posteriormente liberado e o novo smoke passou: preflight CUDA com
10.685 MiB disponíveis, XTTS carregado com 1.831 MiB alocados/1.918 MiB
reservados na GPU, cinco sínteses consecutivas no mesmo worker e
`cascade_smoke --device cuda --turns 3` concluído em 37,51 s. Os três turnos
produziram transcrição, resposta Groq e PCM válido; não houve worker órfão.
Esta é a primeira evidência multi-turno real do caminho local.

Checkpoint Codex — contrato offline: `codex_app_server.py` agora encapsula
JSONL multiplexado, handshake `experimentalApi`, lifecycle de thread/realtime,
texto, áudio e tradução de notificações para `ProcessorPart`. O adapter usa
v3 por padrão quando o runtime mais novo estiver disponível e aceita v2
explicitamente para o binário instalado; nenhum campo v3 é enviado no teste v2.
O contrato offline passou 4 testes. A implementação foi posteriormente
conectada à composição/capability pública como `codex_realtime` e
`codex_text`; este trecho registra o estado anterior ao checkpoint.

O loader de autenticação agora lê `auth.json` apenas no servidor e exige
`OPENAI_API_KEY` para o realtime; tokens de login `chatgpt` são reconhecidos,
mas não são aceitos pelo backend realtime atual. O smoke real foi executado
com o ambiente local e falhou de forma segura porque o arquivo existente só
contém tokens ChatGPT (`auth_mode=chatgpt`) e o app-server respondeu que realtime
exige API key. Não houve exposição de valores secretos. O smoke poderá ser
repetido assim que `auth.json` tiver uma API key compatível.

Para não depender do `~/.codex/config.toml` inválido observado nesta máquina,
o subprocesso agora usa `CODEX_HOME` temporário com link para o `auth.json`
original e configuração limpa; a execução real é bloqueada antes do spawn
quando a API key não existe.

O mesmo `auth.json` foi validado em um smoke real de texto do app-server:
handshake, thread efêmero, turn textual, deltas e conclusão retornaram com
sucesso. A implementação deve expor isso como `pipeline_id=codex_text`, sem
transformar falha de `codex_realtime` em fallback implícito e sem prometer
áudio/voz nessa capacidade. O smoke textual deve ser repetível sem imprimir o
conteúdo da resposta ou qualquer credencial; o smoke atual passou com resposta
não vazia.

Readiness adicional: o snapshot `/api/v1/resources` e a WebUI agora exibem o
componente opcional `diarization` como `unavailable` ou `unloaded`, sem alterar
o cálculo de prontidão obrigatório de STT/TTS. A suíte completa Leonidas/E2E
passou com 139 testes, 2 skips e 9 subtests.

Auditoria ampla posterior: a suíte completa do repositório passou com 709
testes, 2 skips e 27 subtests; flake8 restrito passou excluindo ambientes e
artefatos gerados; os 21 arquivos Python alterados nesta onda passaram no
Pyink. O check global de Pyink continua apontando 37 arquivos históricos fora
do escopo, que não foram reformatted para evitar uma mudança não relacionada.

## Reconciliação da troca de executor 2026-07-31

O usuário pediu continuidade sob o executor Luna e determinou que o estado
existente fosse preservado em commit antes de qualquer nova alteração. O
checkpoint foi criado como `68c2cb5` (`chore(leonidas): checkpoint local model
observability work`). Esta troca de executor não altera escopo nem contratos:
Gemini 2.5/3.1 continuam regressão obrigatória, e a próxima onda deve validar
o estado efetivo dos workers locais e da WebUI antes de novas mudanças.

Regra operacional adicional: se a complexidade ou uma falha repetida exceder
a capacidade de execução segura, registrar evidência concreta e avisar o
usuário; não mascarar falhas nem trocar de arquitetura sem atualizar este
plano e a task durável.

Validação desta continuação: a composição real `CascadeResources` atingiu
`stt=ready` e `tts=ready` em CUDA (RTX 2060), com Parakeet v3 em cerca de
29,7 s e XTTS v2 em cerca de 35,4 s; o smoke completo
`Parakeet → Groq → XTTS` passou em 13,0 s após o warm-up, gerando 89
caracteres transcritos, 77 caracteres de resposta e 8,25 s de PCM. A UI foi
ajustada para permitir retry depois de erro de preparação e exibir a fase
detalhada (`loading_weights`, `warming`, etc.). Regressão adicionada para
retry do runtime; suíte passou com 77 testes Python, 14 Vitest, typecheck,
build, Pyink, Flake8 e `git diff --check`.

## Reconciliação dos problemas observados na sessão local 2026-07-31

O usuário confirmou que Parakeet v3, Groq e o carregamento CUDA estão
funcionando pela WebUI, mas reportou dois defeitos concretos: (a) o PCM gerado
pela resposta local não é reproduzido no navegador; (b) a transcrição exibida
contém tokens literais como `<blank>`. O estado anterior foi preservado antes
da investigação no commit `30a2044` (`chore(leonidas): checkpoint working local
cascade session`).

Hipóteses a validar tests-first: a serialização WebSocket pode estar emitindo
áudio como `inline_data` em um formato que o decoder do frontend não aceita, ou
o player pode estar recebendo uma taxa/formato incompatível; o adapter
Parakeet pode estar retornando tokens especiais que devem ser normalizados no
limite STT, sem alterar o texto original do Gemini. A correção deve preservar
PCM mono 24 kHz no TTS, PCM 16 kHz no STT, o contrato `ProcessorPart` e os
smokes Gemini 2.5/3.1.

Diagnóstico e correção desta onda: o Parakeet v3 retornou literalmente
`'<blank><blank> Leônidas<blank>, diga o que você vê, e confirme que me ouviu.<blank>'`.
O normalizador agora remove somente tokens de controle allowlisted
(`<blank>`, `<pad>`, `<unk>`), colapsa whitespace e corrige espaço antes de
pontuação no adapter STT. A inspeção do WebSocket local confirmou PCM
`audio/pcm;rate=24000` com payload base64 válido e 27 chunks por resposta; o
player WebAudio passou a tentar retomar um `AudioContext` suspenso antes de
agendar cada chunk. O contrato Gemini permanece inalterado.

Validação: 88 testes Python (2 live opt-in ignorados), 14 Vitest, typecheck,
build, Pyink, Flake8 e `git diff --check`; transcrição real pós-correção ficou
`Leônidas, diga o que você vê, e confirme que me ouviu.`.

### Onda VAD híbrido e áudio local — concluída 2026-07-31

A sessão manual seguinte mostrou falsos turnos válidos lexicalmente (`Okay`,
`Yeah`, `Mm-hmm`) durante silêncio absoluto e novamente nenhum áudio. A
telemetria correlacionou 10 STTs, 7 respostas Groq, 9 flushes e nenhum
`local_tts_ms`/`audio_chunks_sent`: o VAD iniciava fala após somente 90 ms de
ruído e cancelava o XTTS antes da síntese. O usuário decidiu preservar falas
curtas reais. Implementar o gate híbrido definido em `SPECS.md`, sem blacklist
textual, instrumentar rejeições/interrupções/cancelamentos e provar silêncio,
fala curta, barge-in e resposta PCM ponta a ponta.

O primeiro E2E WebSocket detectou que 12 frames finais dividiam a fixture real
quando a fala começava fora do alinhamento de 30 ms. A varredura 12/15/18/20/
24/30 provou que 15 frames (450 ms) preservam um turno único; este valor
substitui os 12 frames iniciais e possui regressão de alinhamento arbitrário.

Evidência final: 5 s de silêncio digital concatenados à fala real produziram
zero turno durante o silêncio e exatamente uma utterance limpa, sem
interrupção nem TTS cancelado. Pelo servidor standalone/WebSocket, XTTS
concluiu uma síntese, enviou 284 chunks/681.056 bytes de PCM 24 kHz e publicou
`generation_complete`. O smoke CUDA direto passou com 8,28 s de áudio. Gemini
2.5 passou com 6,12 s/TTFA 9,30 s e Gemini 3.1 com 10,88 s/TTFA 7,15 s.

Repositório: `/home/guilherme/genai-processors`

Task durável: `/home/guilherme/genai-processors/.llms/tasks/20260730-leonidas-agent.md`

## Regra de continuidade para novos inputs

Antes de agir sobre **todo novo input do usuário** relacionado ao Leonidas, o
executor deve:

1. reler este plano e o arquivo de task durável por completo;
2. comparar o novo input com requisitos, invariantes e progresso registrados;
3. atualizar primeiro os dois arquivos com requisitos adicionais, decisões,
   conflitos, impactos nos testes e ordem de execução;
4. preservar requisitos anteriores, salvo remoção ou substituição explícita do
   usuário;
5. só então implementar o novo input e registrar a evidência de validação.

Se o novo input conflitar materialmente com um contrato público ou requisito
anterior sem dizer qual deve prevalecer, registrar o conflito e pedir apenas a
decisão bloqueante.

## Objetivo

Criar `/leonidas` como agente conversacional standalone, derivado mas
independente de `examples/live_commentator`, com Gemini Live 2.5/3.1 e uma
pipeline cascata Parakeet v3 → Groq reasoning → XTTS v2, configuração e
lifecycle explícitos, Vite WebUI útil, métricas, logs e testes automatizados
reais usando áudio/imagens demo.

## Reconciliação da continuação 2026-07-30

A continuação automática do goal não adiciona nem remove requisitos. O próximo
trabalho seguro permanece: auditar contratos e dirty state, investigar o estado
CUDA sem ações privilegiadas/destrutivas e manter preparado o smoke XTTS/E2E.
O aceite de licença XTTS continua sendo decisão humana; não será inferido nem
automatizado.

## Reconciliação do diagnóstico pós-suspensão 2026-07-30

O usuário informou que retirou o notebook da tomada e suspendeu o sistema antes
de um possível novo problema com a GPU. Este input acrescenta uma investigação
read-only do ciclo suspend/resume: validar `nvidia-smi` e uma operação CUDA
PyTorch real, correlacionar o journal do boot com eventos de suspensão,
retomada e `NVRM Xid`, e inspecionar os parâmetros e serviços oficiais de power
management do driver NVIDIA. Distinguir a retirada da alimentação AC da
suspensão como gatilho; não atribuir causalidade sem timestamps e evidência.

Se a GPU estiver enumerada mas CUDA estiver indisponível, registrar separadamente
a recuperação imediata e a prevenção para suspensões futuras. Antes de recomendar
qualquer configuração, confirmar se `NVreg_PreserveVideoMemoryAllocations`, o
backing store e os serviços `nvidia-suspend`, `nvidia-resume` e
`nvidia-hibernate` já estão configurados. Não alterar `/etc`, initramfs, kernel,
serviços ou estado da GPU nesta etapa; mudanças privilegiadas dependem do
diagnóstico e de autorização explícita.

Evidência coletada:

- `nvidia-smi` enumera a RTX 2060/6 GiB, mas uma operação PyTorch CUDA real
  falha com `CUDA-capable device(s) is/are busy or unavailable`;
- o boot suspendeu em modo `deep` às 07:19 e retomou às 08:53; a primeira
  operação CUDA testada após a retomada gerou `NVRM Xid 31`/MMU Fault às
  10:15. O boot anterior contém o mesmo padrão suspend/resume seguido de Xid
  31, enquanto não há evidência que isole a retirada da alimentação AC;
- os três serviços NVIDIA de suspend/resume estão instalados, habilitados e
  foram executados, mas `PreserveVideoMemoryAllocations` está em `0`. Essa
  combinação não satisfaz o contrato documentado pela NVIDIA para preservar
  toda a VRAM e suportar UVM/CUDA no mecanismo `/proc/driver/nvidia/suspend`;
- `/tmp` e `/var/tmp` em ZFS suportam arquivos temporários sem nome, mas o pool
  do sistema oferece somente 3,02 GiB aos datasets. Para 6.144 MiB de VRAM, a
  margem oficial de 5% exige ao menos 6.452 MiB de backing store. O pool
  `internal` tem espaço, porém está degradado por um disco offline e não é um
  destino preventivo robusto enquanto não for reparado.

Recuperação imediata: reiniciar o sistema antes de executar novamente as
pipelines CUDA. Prevenção proposta, ainda não aplicada: primeiro disponibilizar
espaço confiável suficiente; depois configurar `nvidia.ko` com
`NVreg_PreserveVideoMemoryAllocations=1` e
`NVreg_TemporaryFilePath=<diretório ZFS confiável>`, manter habilitados os hooks
systemd existentes, reconstruir o initramfs, reiniciar e provar o ciclo
suspend/resume com uma operação CUDA antes e depois. Não usar o pool degradado
nem ativar a opção com backing store subdimensionado.

## Reconciliação do erro de origem na porta 8081 2026-07-30

O usuário iniciou o Leonidas com a WebUI na porta 8081 e recebeu `Sessão não
iniciada / Origin not allowed`. A causa foi localizada no adaptador HTTP: a
allowlist estava fixa nas portas 8000 e 5173, enquanto o WebSocket já calculava
corretamente a origem a partir de `--web-port`. O controle HTTP, portanto,
rejeitava os `fetch` same-origin da própria WebUI em 8081.

O contrato permanece local e seguro: a origem HTTP é calculada a partir da
porta efetiva do servidor, aceita `localhost`/`127.0.0.1` nessa porta e as
origens de desenvolvimento Vite 5173, e continua rejeitando origens externas.
Foi adicionada regressão para porta não padrão e para origem não allowlisted.

## Reconciliação da observabilidade dos modelos locais 2026-07-30

O usuário confirmou que Gemini Live 2.5 e 3.1 funcionam, mas a cascata local
não concluiu conversas, produziu muitos diagnósticos ruidosos e deixou a UI
lenta. A execução deve preservar o caminho Gemini e tornar o runtime local
explícito: Start local responde rapidamente em `starting`, carrega e aquece
Parakeet e XTTS, publica estados por componente e só entra em `running` quando
ambos estiverem comprovadamente prontos. Por decisão do usuário, não haverá
botão separado de preload/unload; modelos prontos permanecem residentes até o
Leonidas encerrar.

Evidência do runtime atual: Parakeet e XTTS chegaram a residir na GPU usando
aproximadamente 1.356 MiB e 2.048 MiB por processo, mesmo com sessão parada,
mas não existe contrato de readiness. Parakeet carrega no primeiro áudio,
XTTS carrega na primeira resposta, erros de worker perdem o estágio e a UI
re-renderiza até 2.000 linhas a cada evento SSE. O polling de métricas também
gera access logs, criando feedback de renderização.

Nova ordem de execução:

1. atualizar SPECS/WORKFLOW/UI_SPECS e contratos de resource state;
2. criar supervisor observável e workers persistentes para Parakeet/XTTS;
3. integrar Start assíncrono somente à cascata, sem alterar Gemini;
4. publicar readiness/estágios via REST e ProcessorPart WebSocket;
5. adicionar painel local e batching/adaptive polling na UI;
6. validar E2E local real e repetir os dois smokes Gemini.

## Reconciliação do input sobre reinicialização CUDA 2026-07-30

O usuário se disponibilizou a reiniciar a máquina para recuperar o CUDA. A
falha observada é um `NVRM Xid 31` no driver: `nvidia-smi` ainda enumera a RTX
2060, mas o PyTorch passou a retornar `CUDA unknown error` e
`torch.cuda.is_available() == False`. Reiniciar a máquina é a recuperação
conservadora aprovada; não tentar reset da GPU, unload de módulos ou outra ação
privilegiada enquanto o servidor gráfico utiliza a placa.

Após o reboot, antes de continuar a implementação, executar novamente o
preflight Leonidas, confirmar CUDA no PyTorch e então repetir o smoke real do
Parakeet em CUDA. A reinicialização não resolve nem substitui a decisão humana
separada sobre a licença do XTTS.

O usuário confirmou que a máquina foi reiniciada. Esta execução deve começar
por verificar o estado pós-boot (`nvidia-smi`, PyTorch e preflight); somente se
todos estiverem saudáveis o smoke Parakeet CUDA poderá iniciar.

A primeira tentativa de diagnóstico pós-boot foi interrompida antes de produzir
evidência completa. O usuário solicitou continuar; repetir todos os comandos de
diagnóstico desde o início e não inferir sucesso a partir da execução parcial.

O diagnóstico repetido comprovou recuperação do CUDA: PyTorch 2.6.0+cu124
detectou a RTX 2060, compute capability 7.5, e executou uma operação real de
tensor na GPU. O preflight passou CUDA, Groq, runtime/import XTTS e referência
de voz; permaneceu não zero exclusivamente por `xtts_license_agreement=missing`.

O usuário pediu instruções para aceitar a licença XTTS. A aceitação continua
sendo ação humana explícita: executar o downloader interativo, ler a CPML e
responder `y` somente se possuir licença comercial aplicável ou concordar com
o uso não comercial permitido pela CPML. Não definir a variável de aceite nem
criar `tos_agreed.txt` automaticamente pelo agente.

O usuário confirmou explicitamente que o uso será não comercial sob a CPML e
autorizou o agente a responder ao prompt interativo em seu nome. Executar o
downloader oficial do runtime XTTS, responder `y`, permitir que ele crie seu
próprio `tos_agreed.txt` e validar modelo/síntese. Não usar essa autorização
para alterar a finalidade declarada nem para uso comercial futuro.

O primeiro smoke Parakeet pós-reboot carregou os 723 pesos em CUDA, mas falhou
na inferência porque o adapter criou o modelo em FP16 e manteve
`input_features` em FP32 (`Input type (float) and bias type (c10::Half)`).
CUDA está funcional; esse é um bug confirmado de conversão de dtype no adapter
e requer teste de regressão antes da correção.

O usuário pediu a VRAM efetivamente usada e confirmação de que o modelo é a
versão mais recente. O adapter está configurado explicitamente com
`nvidia/parakeet-tdt-0.6b-v3`. Após corrigir o dtype tests-first, repetir o
smoke em CUDA medindo memória alocada e reservada de pico pelo PyTorch; confirmar
o status da versão em fonte oficial da NVIDIA/Hugging Face antes de responder.

Evidência concluída: `nvidia/parakeet-tdt-0.6b-v3` transcreveu o áudio demo em
CUDA em 8,12 s, retornou 83 caracteres e atingiu pico PyTorch de 1,205 GiB
alocados e 1,238 GiB reservados. A model card oficial da NVIDIA identifica
essa como a versão corrente do Parakeet TDT 0.6B, com suporte a 25 idiomas,
incluindo português.

O gate de revisão cascata encontrou que uma falha Groq/TTS podia ficar sem
propagação enquanto o input realtime permanecesse aberto. Uma regressão
reproduziu o timeout; o pipeline passou a enfileirar a exceção, acordar a saída
e recolher a task de resposta no cleanup. Validação após a correção: 70 testes
Python aprovados, 2 live opt-in ignorados, Pyink e Flake8 aprovados; frontend
permanece com 11 testes, typecheck e build aprovados.

O usuário autorizou e o downloader oficial registrou o aceite CPML para uso
não comercial. XTTS v2 baixou 1,87 GB e sintetizou fala real em CUDA em
2,645 s. O primeiro E2E completo revelou que áudio base64 excedia o limite
default de 64 KiB do StreamReader; uma regressão com resposta de 70.000 bytes
reproduziu a falha e o protocolo passou a declarar limite bounded de 64 MiB.

Após a correção, o E2E real Parakeet → Groq → XTTS passou em CUDA:
89 caracteres transcritos, resposta de 77 caracteres, 7,84 s de PCM e 49,40 s
totais. Com os dois modelos residentes, `nvidia-smi` mediu 1.376 MiB no processo
Parakeet e 2.084 MiB no XTTS (3.460 MiB combinados). Ambos os processos
encerraram sem órfãos após o smoke.

Cancelamento XTTS real também passou: worker cancelado durante geração,
cleanup em 2,02 s e zero processo órfão. Validação final ampliada: 70 testes
Python aprovados/2 live opt-in ignorados, 11 testes Vite, typecheck, build,
Pyink, Flake8, preflight CUDA/XTTS/Groq e `git diff --check` aprovados.

## Requisitos consolidados

- Documentação primeiro: `SPECS.md`, `WORKFLOW.md`, `UI_SPECS.md`.
- Código do Live Commentator copiado e refatorado sem alterar o original.
- Profiles separados para Gemini 2.5 e 3.1, preservando transports/tools.
- Objetivo/persona editável; instruções internas protegidas.
- REST para controle e observabilidade; WebSocket `ProcessorPart` para mídia.
- Start, Stop e Apply & Restart transacionais, sem reuse de coroutine/task.
- Voz automática ou allowlisted e preview real isolado.
- Presets de latência e overrides compatíveis por capabilities.
- Config persistente local sem segredos.
- Tail ao vivo e arquivos de log redigidos e limitados.
- UI Vite + TypeScript implementada diretamente, sem Gemini como agente de UI.
- Aplicação restrita a localhost e uma conexão de mídia proprietária.
- Interfaces reais para pipelines e nenhum adapter anunciado antes de passar
  testes de contrato e smoke real.

## Novo requisito: milestone Git e pipeline offline/cascata

Depois de concluir e testar todo o milestone Gemini/UI/E2E:

1. revisar o diff e excluir `.agents/`, secrets, logs, `.runtime` e assets;
2. criar um commit atômico do milestone;
3. criar a tag anotada `leonidas-v0.1.0` nesse commit;
4. somente então iniciar o milestone cascata;
5. implementar STT local NVIDIA Parakeet v3, Groq para reasoning/LLM e XTTS v2
   local para fala, usando CUDA quando disponível;
6. manter fallbacks explícitos de device e nunca degradar silenciosamente;
7. executar testes reais de áudio end-to-end e só anunciar suporte quando o
   pipeline tiver transcrito, raciocinado, sintetizado e sido interrompido/
   encerrado de forma limpa.

A pipeline cascata deve ser selecionável na UI e construída por capabilities,
sem condicionais espalhadas por nome de modelo. Segredos Groq vêm somente de
`GROQ_API_KEY`. Pesos e caches NVIDIA/XTTS ficam fora do Git. Dependências CUDA
permanecem opcionais para a biblioteca base e podem usar um ambiente runtime
dedicado se Python 3.13 não for suportado pelos engines.

## Novo requisito: testes empíricos reais

Criar `leonidas/e2e/` com:

- manifest versionado de cenários e mídia;
- gerador opt-in que usa a API Gemini para produzir fala demo e imagens demo;
- cache local ignorado pelo Git para mídia gerada e resultados;
- validação estrutural dos assets antes de qualquer chamada Live;
- runner que inicia cada profile Gemini suportado, envia imagem + áudio PCM em
  chunks realtime, encerra o stream e coleta áudio, transcrição, estados,
  latências e erros;
- critérios objetivos por cenário: conexão, primeiro output, áudio PCM válido,
  duração mínima, ausência de erro/reset/task pendente e stop limpo;
- relatório JSON e Markdown redigido por execução;
- execução offline/CI com provider fake que valida o mesmo contrato;
- testes reais marcados `live`/opt-in, nunca obrigatórios no CI normal;
- nenhuma chave, mídia gerada, áudio retornado, transcript ou relatório com
  conteúdo privado versionado.

Áudios devem ser gerados pela própria API Gemini. Como Gemini Live retorna PCM,
o gerador solicita uma frase sintética curta por uma sessão efêmera e encapsula
o PCM em WAV. A imagem tenta primeiro o endpoint Gemini configurável. Evidência
de 2026-07-30 mostrou quota zero tanto para `gemini-3.1-flash-image` quanto para
`gemini-2.5-flash-image`; nesse caso é permitido, somente por flag explícita,
gerar uma cena determinística com Pillow e registrar `image_source=synthetic`.
Essa fallback testa visão, mas nunca é apresentada como imagem Gemini.

## Ondas de execução e estado

1. **Documentos canônicos — concluído**
   - SPECS, workflows Mermaid, UI specs e README criados.
2. **Contratos/configuração/pipeline — concluído**
   - capabilities, config revisionada, prompts protegidos e Gemini pipeline.
3. **Runtime/API/observabilidade — concluído**
   - lifecycle, REST, WebSocket, métricas, logs e preview implementados;
   - falta revisão integrada e smoke do servidor.
4. **Vite WebUI — concluído**
   - módulos REST/protocolo/mídia e layout criados;
   - falta CSS final, atualizar testes TypeScript, build e correções.
5. **E2E empírico — concluído**
   - tests-first para manifest, geração, chunking, avaliação e relatórios;
   - gerar assets reais somente se `GOOGLE_API_KEY` estiver disponível;
   - áudio Gemini TTS e imagem synthetic rotulada validados;
   - 2.5 PASS: 5,88 s de áudio, TTFA 12,26 s;
   - 3.1 PASS: 5,14 s de áudio, TTFA 6,92 s.
6. **Auditoria do milestone Gemini — concluído**
   - testes Python/TypeScript, build, Pyink, Flake8, segurança, dirty state,
     alinhamento specs/código e comando final de execução.
   - 113 passed/1 live skipped, 8 Vitest, typecheck/build, Pyink/Flake8;
   - smoke REST/WebSocket `starting→running→stopping→stopped`;
   - inspeção Chromium 1440×1100 aprovada.
7. **Commit e tag do milestone — concluído**
   - commit atômico sem `.agents/` ou artefatos privados;
   - tag anotada `leonidas-v0.1.0`.
   - commit `85f5d9b`, tag `leonidas-v0.1.0`.
8. **Specs da pipeline cascata — concluído**
   - atualizar SPECS/WORKFLOW/UI_SPECS primeiro;
   - capabilities, contratos de áudio, processos, CUDA/VRAM e falhas.
9. **Parakeet v3 + Groq reasoning + XTTS v2 — concluído**
   - adapters tests-first e composição turn-based/realtime;
   - seleção pela UI, métricas e logs;
   - testes offline de contrato e smokes reais de cada estágio e do conjunto.
   - Groq GPT-OSS 20B real: PASS, resposta em 0,31 s;
   - referência privada Gemini TTS: PASS, PCM16/24 kHz/mono, 10,00 s;
   - CUDA: PyTorch 2.6.0+cu124, RTX 2060, 5,78 GiB;
   - runtime XTTS isolado importa Coqui com Transformers 4.57.6: PASS;
   - aceite CPML XTTS: autorizado explicitamente para uso não comercial;
     download e síntese CUDA real: PASS;
   - Parakeet v3 real CPU: PASS, 723 blocos, 83 caracteres, critério semântico
     satisfeito em 19,32 s;
   - Parakeet CUDA: driver recuperado após reboot e operação PyTorch real
     aprovada; incompatibilidade FP32/FP16 corrigida tests-first;
     smoke PASS em 8,12 s, pico 1,205 GiB alocado/1,238 GiB reservado.
   - E2E Parakeet/Groq/XTTS CUDA: PASS, 7,84 s de áudio, 49,40 s total,
     3.460 MiB combinados com ambos os modelos residentes e cleanup limpo.

### Decisão de runtime local 2026-07-30

O preflight empírico confirmou um conflito de dependências impossível de
resolver corretamente no mesmo processo: Parakeet v3 expõe `AutoModelForTDT`
na linha Transformers 5, enquanto Coqui TTS 0.27.5/XTTS v2 ainda depende de
uma API removida no Transformers 5. XTTS portanto roda em `.venv-xtts` e em
subprocesso persistente, com protocolo local privado. A revisão 0041 passa
também o Parakeet para um subprocesso persistente usando a `.venv` principal:
isso preserva Transformers 5, isola carga/GIL/CUDA do servidor e permite
readiness e health checks simétricos. Não usar monkey patch nem rebaixar o
Parakeet. Ambos os workers são encerrados com a aplicação e cache/pesos
continuam fora do Git.
10. **Auditoria final ampliada — concluído**
    - validar Gemini e cascata, CPU/device errors, CUDA, downloads, cancelamento,
      segurança e documentação; commit final coerente.
    - validações offline/live, memória simultânea e cleanup: aprovados;
    - stage revisado exclui artefatos privados e arquivos não relacionados;
      checkpoint final será o commit e a tag anotada `leonidas-v0.2.0`.
11. **Readiness local e desempenho da UI — concluído em 2026-07-30**
    - Parakeet e XTTS usam workers persistentes com preparação sequencial,
      warm-up real e estado `unloaded→loading→warming→ready/error`;
    - o start da cascata retorna `202 starting`; Gemini preserva o caminho
      síncrono e não executa preparação local;
    - REST/WS expõem modelo, device, GPU, VRAM e tempo por componente;
    - a UI renderiza cartões, agrupa logs, limita 2.000 linhas e usa polling
      adaptativo sem requests concorrentes;
    - contenção de segunda aba usa backoff que só reinicia após estado válido;
    - inspeção real mostrou STT `ready` em 14,1 s/1.246 MiB reservados enquanto
      XTTS carregava; o vazamento do `id` privado XTTS foi reproduzido, coberto
      por regressão e removido;
    - E2E Parakeet/Groq/XTTS CUDA: PASS, transcript 89 caracteres, resposta 23
      caracteres, 3,15 s de áudio, 6,82 s após readiness e cleanup limpo;
    - Gemini real: 2.5 PASS (5,88 s, TTFA 9,47 s) e 3.1 PASS (6,04 s, TTFA
      6,92 s).

## Contrato dos cenários E2E

Cada cenário define `id`, `description`, `image_prompt`, `audio_script`,
`expected_modalities`, `timeout_seconds` e thresholds. O cenário inicial deve
mostrar uma mesa com um objeto vermelho e dizer em português “Leonidas, diga o
que você vê e confirme que me ouviu”. A avaliação não exige texto literal;
exige output de áudio não vazio e, quando transcription estiver disponível,
termos semânticos configurados como `mesa`, `vermelho` ou reconhecimento de
incerteza visual.

Thresholds iniciais:

- conexão/start: até 20 s;
- primeiro áudio: até 20 s após fim do input;
- áudio retornado: PCM 24 kHz mono, pelo menos 0,25 s;
- stop: até 5 s e zero tasks do runner pendentes;
- máximo de um retry somente para erro transitório de rede/429/5xx;
- qualquer 1007, config incompatível ou reset loop reprova sem retry estrutural.

## Validação obrigatória

```bash
.venv/bin/python -m pytest leonidas/tests
.venv/bin/python -m pytest leonidas/e2e/tests
cd leonidas/webui && npm test && npm run typecheck && npm run build
.venv/bin/python -m pyink --check leonidas
.venv/bin/python -m flake8 leonidas --count --select=E9,F63,F7,F82 --show-source --statistics
```

Live opt-in, quando houver credencial e assets válidos:

```bash
.venv/bin/python -m leonidas.e2e.generate_assets
.venv/bin/python -m leonidas.e2e.run --models all
```

O milestone cascata acrescentará comandos próprios de preflight e smoke, que
devem verificar `torch.cuda.is_available()`, compute capability/VRAM, modelo
Parakeet, `GROQ_API_KEY`, pesos XTTS, formatos PCM e tempo de cancelamento.

## Stop condition

Parar somente quando Gemini, cascata local, diarização, coexistência CUDA,
API/WebSocket, observabilidade e WebUI estiverem implementados e validados
empiricamente. Codex não participa da conclusão. Se um recurso externo bloquear
Pyannote, continuar todos os requisitos independentes; somente considerar
impasse quando não existir outra frente ativa segura e o critério de bloqueio
do goal tiver sido satisfeito.

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

### Continuação: instalação acionável da diarização — 2026-08-01

O preflight confirmou que este host ainda não possui `.venv-diarization` nem
token Hugging Face. Para tornar o bloqueio acionável sem contaminar o runtime
Parakeet/Transformers 5, foi adicionado `install_diarization.sh`, que cria o
runtime isolado com Torch 2.6/cu124 (ou CPU) e `pyannote.audio==3.4.0`.
`.venv-diarization` entrou no `.gitignore`; pesos e tokens continuam fora do
repositório. A capability agora informa somente metadados seguros de runtime,
comando de instalação e o fato de que acesso ao modelo Hugging Face é exigido.
O smoke real continua pendente até esse runtime e o acesso ao modelo serem
configurados; a cascata sem diarização e os dois perfis Gemini não dependem
dessa instalação.

### Próxima frente: reescrita da WebUI inspirada em `resources/ui_002` — 2026-08-01

Após fechar e validar os gates atuais de backend, workers e diarização,
a WebUI do Leonidas deverá ser reescrita integralmente usando
`resources/ui_002/` como referência visual e de interação. A implementação
deve continuar sendo Vite + TypeScript direta, sem trocar o contrato atual da
API REST, do envelope `ProcessorPart` ou do WebSocket. Antes de editar a UI,
auditar os assets e padrões de `resources/ui_002`, mapear cada tela/estado para
os endpoints existentes e atualizar `UI_SPECS.md` com os contratos derivados.

Requisitos obrigatórios dessa frente:

- preservar Gemini 2.5/3.1, cascata local, configuração, lifecycle, logs,
  métricas, readiness e diarização opcional;
- suporte mobile real, incluindo layout responsivo, controles touch,
  captura/preview adaptados, teclado virtual, orientação estreita e estados
  de permissão/erro sem overflow horizontal;
- manter testes Vitest, typecheck, build e testes de contrato WebSocket/API;
- validar visualmente desktop e mobile antes de substituir a UI atual;
- não incluir assets privados, credenciais, logs ou resultados de runtime no
  commit.

Essa frente permanece pendente até a conclusão da validação atual e deve ter
checkpoint próprio, revisão de diff e tag somente se todos os gates aplicáveis
estiverem verdes.

Início da implementação v2 — 2026-08-01: a auditoria confirmou que os
contratos funcionais já existentes podem ser preservados por IDs DOM enquanto
a apresentação é reorganizada em Operação, Configuração e Diagnóstico. A
primeira onda da UI v2 não altera REST, WebSocket, ProcessorPart ou lifecycle;
ela adiciona navegação semântica, layout cockpit desktop e navegação touch
mobile. O mapeamento foi registrado em `UI_SPECS.md` antes da edição.

O runtime foi instalado com Torch `2.6.0+cu124`, Pyannote `3.4.0` e
`huggingface_hub==0.36.2`; `pip check` e CUDA passaram. O smoke então chegou
ao carregamento real e confirmou o bloqueio externo: o pipeline Hugging Face
retorna `None` sem acesso/autorização ao modelo. O worker agora converte esse
caso em erro acionável e redigido, em vez de expor um `AttributeError` interno.

O primeiro smoke após a instalação encontrou incompatibilidade entre
`pyannote.audio==3.4.0` e `huggingface_hub==1.26.0` (`use_auth_token` removido).
O instalador foi corrigido para fixar `huggingface_hub<1.0`; o smoke deve ser
repetido para separar essa falha de compatibilidade do acesso Hugging Face.

Validação posterior: o runtime isolado passou `pip check`, import de Pyannote
e CUDA (`torch==2.6.0+cu124`). O smoke real chegou ao carregamento do modelo e
falhou somente porque o pipeline gated não está autorizado neste host; o
worker agora reporta isso de forma redigida. A suíte completa do Leonidas
passou com 151 testes, 2 skips e 9 subtests; o smoke cascata real CUDA passou
em três turnos (50,63 s), e o smoke Gemini Live passou novamente nos dois
perfis (35,90 s). Nenhum desses testes habilita diarização implicitamente.

Validação UI v2 — 2026-08-01: a estrutura foi reorganizada em Operação,
Configuração e Diagnóstico preservando os IDs DOM e os contratos REST,
WebSocket e ProcessorPart. A navegação possui suporte a foco e setas de
teclado; em viewport de 390×844 torna-se uma barra inferior touch. Chromium
foi usado para inspeção em 1440×1000 e 390×844; typecheck, 24 testes Vitest e
build Vite passaram. A tela também exibiu corretamente erro de API offline,
sem impedir o carregamento do shell.

Regressão real pós-UI — 2026-08-01: `LEONIDAS_RUN_CODEX_TEXT_E2E=1 ...
codex_text_smoke --turns 2` passou com dois turnos e resposta não vazia
(10,77 s); o smoke Gemini 2.5/3.1 passou (`unittest`, 33,83 s). Duas
tentativas de `cascade_smoke --device cuda --turns 3` foram interrompidas
corretamente pelo guard do XTTS antes do load, primeiro com 5050 MiB e depois
com 4005 MiB disponíveis para um mínimo de 5120 MiB. A cascata não deve ser
declarada verde até repetir com memória/swap suficientes; não foi reduzido o
limite e nenhum processo do usuário foi encerrado.

Correção de método — 2026-08-01: uma tentativa de compilar
`codex-cli` diretamente do checkout `~/github/codex` foi interrompida por
falta de espaço e não faz parte da validação do produto. O checkout deve ser
somente referência de leitura para schemas, eventos e autenticação; o
Leonidas valida a API do app-server diretamente por JSONL/WebRTC. O target
gerado foi limpo com `cargo clean`, sem alterar código, auth ou o binário
instalado. Não usar compilação do CLI como gate futuro.

### Onda de compatibilidade integral com o protocolo Codex — 2026-08-01

O objetivo ativo exige documentar e tornar o adapter integralmente compatível
com os contratos identificados no checkout mais recente, preservando o uso
server-side das credenciais de `auth.json`. A leitura dos structs Rust e do
README do app-server confirmou os seguintes gaps concretos no estado atual:

- `thread/realtime/appendText` aceita compatibilidade legada sem `role`, mas o
  contrato corrente requer que novos clientes enviem explicitamente `user`,
  `developer` ou `assistant`;
- o adapter precisa consumir `thread/realtime/error` e
  `thread/realtime/closed` durante toda a sessão, encerrando o processor de
  forma observável em vez de aguardar indefinidamente;
- deltas e finais de transcrição, áudio, `itemAdded`, SDP e lifecycle devem ter
  tradução ou tratamento explícito, sem vazar objetos provider-specific;
- a versão realtime e as vozes devem ser obtidas/validadas contra o app-server
  executado. O binário local 0.144.0 aceita apenas v1/v2, enquanto o checkout
  mais recente inclui v3; a capability pública não pode anunciar uma versão
  como funcional sem negociação ou evidência do runtime;
- WebRTC continua restrito a v1/v3 e exige oferta SDP real. WebSocket v2 exige
  API key; login ChatGPT de `auth.json` deve seguir pelo WebRTC sem conversão
  de tokens;
- o smoke real deve exercitar `initialize`, `thread/start`, realtime start,
  lifecycle e stop com o `auth.json` atual. Erro upstream de entitlement deve
  permanecer distinguível de incompatibilidade local e de credencial inválida.

Ordem desta onda: registrar regressões de contrato; corrigir requests e
lifecycle; negociar capabilities com `thread/realtime/listVoices` e/ou versão
do app-server; atualizar SPECS/WORKFLOW/UI_SPECS; executar suites offline;
repetir `codex_text` e WebRTC reais; registrar cada rota esgotada sem expor
credenciais. Gemini e cascata local são regressões obrigatórias antes do
checkpoint.

### Requisito empírico: corpus de microfone e múltiplos turnos Codex

Gerar com a API Gemini um pequeno corpus privado de falas PT-BR e armazená-lo
somente em `leonidas/.runtime/e2e/codex_audio/`, já ignorado pelo Git. Cada
fixture deve possuir manifesto redigido com duração, sample rate, canais,
sample width e hash, sem persistir transcrição privada em relatórios. O runner
deve validar WAV/PCM, converter para PCM16 mono na taxa exigida pelo protocolo
e enviar chunks com pacing equivalente a microfone em pelo menos dois turnos.

O teste deve cobrir separadamente:

- WebSocket app-server com `appendAudio`, quando o `auth.json` fornecer API key
  compatível;
- WebRTC com track de áudio real/fake alimentada pelo corpus, quando a conta
  ChatGPT do `auth.json` possuir entitlement de voz;
- lifecycle por turno, transcrição, resposta/áudio, stop e ausência de tasks ou
  processos órfãos;
- falha explícita e redigida quando a credencial/entitlement não autorizar a
  rota, sem substituir o teste real por mock.

Assets gerados, áudio capturado e respostas permanecem fora do Git. Testes de
contrato usam fixtures sintéticas pequenas; o corpus Gemini é exclusivamente
um smoke real opt-in.

Evidência desta onda: o Gemini TTS gerou dois WAVs privados válidos, total de
9,36 s, em `.runtime/e2e/codex_audio`; o manifesto contém somente propriedades
técnicas e SHA-256. O binário 0.144.0 respondeu ao `listVoices` real com nove
vozes V1, dez V2 e defaults válidos. Os runners de áudio V1/V2 WebSocket
falharam antes do primeiro chunk com `api_key_required`; V3 falhou com
`protocol_version_unsupported`. Chromium real usou o primeiro WAV como
microfone fake, criou `RTCPeerConnection`/SDP V1 e alcançou o backend, que
respondeu `voice_entitlement_denied` antes do transporte de mídia
(`audioIn=0`, `audioOut=0`). Portanto o corpus e os dois caminhos de envio
estão implementados, mas múltiplos turnos pagos não podem atravessar a criação
da sessão com esta credencial/conta.

Automação do smoke WebRTC — 2026-08-01: o procedimento manual foi convertido
em `python -m leonidas.e2e.codex_webrtc_smoke`. O runner combina os dois WAVs
Gemini com silêncio de endpointing, inicia Leonidas e Chromium headless em
portas/perfis temporários, aguarda os handshakes REST e WebSocket da WebUI,
aciona a sessão e classifica somente resultados redigidos. A execução real com
o `auth.json` atual comprovou novamente `voice_entitlement_denied`, agora por
um caminho reproduzível e sem persistir conversa, SDP ou erro upstream. O
checkout Codex em `91f3c3824` continua confirmando `gpt-realtime-1.5`, WebRTC
AVAS e os headers ChatGPT encaminhados pelo app-server; o binário executado
permanece `codex-cli 0.144.0`. Assim, modelo, voz descoberta, versão instalada,
sinalização e autenticação foram confrontados; o gate restante continua sendo
autorização upstream de voz, não um fallback ou bypass a implementar.

### Correção de escopo: transporte direto do backend Codex — 2026-08-01

A auditoria do objetivo identificou que o adapter atual usa JSONL com o
processo `codex app-server`. Isso valida os contratos do app-server, mas não
cumpre sozinho a instrução de integrar a API do backend diretamente no código
Leonidas e usar `~/github/codex` somente como fonte de protocolo. Adicionar um
transporte HTTP/WebRTC server-side próprio, atrás de uma capability explícita,
que carregue `access_token` e `account_id` de `auth.json`, reproduza apenas os
headers, query, multipart/JSON e lifecycle confirmados pelo código oficial e
nunca envie credenciais à WebUI. Manter o transporte app-server como opção de
compatibilidade até o direto possuir testes de contrato e smoke real.

Esta onda deve começar pela extração integral dos contratos de autenticação,
URL, headers, criação da chamada, resposta SDP, sideband, refresh/expiração e
erros. Fixtures usam tokens sintéticos; o smoke real relata apenas código de
resultado e latência. Não usar endpoints descobertos por tentativa cega, não
persistir SDP/token e não declarar voz funcional enquanto a conta continuar
respondendo `voice_entitlement_denied`. Evidência atual: no release oficial
0.146.0 isolado, Codex Text passou em dois turnos, WebRTC V1 repetiu o 403 de
entitlement e WebRTC V3 repetiu timeout de sinalização; o `auth.json` possui
login ChatGPT/access token/account id e não possui `OPENAI_API_KEY`.

Compatibilidade corrigida tests-first: `appendText` envia `role=user`, versões
desconhecidas são rejeitadas antes de criar thread, vozes são descobertas e
validadas por versão, `closed`/`error` encerram startup e runtime, V3 não envia
o modelo V1/V2 incompatível e a capability separa versões confirmadas de V3
experimental. Validação: 168 testes Python passaram, 2 foram ignorados e 9
subtests passaram; WebUI teve 24 testes, typecheck e build verdes. O smoke
Codex Text passou em dois turnos (12,17 s), a cascata CUDA passou em três
turnos (46,45 s) com cleanup sem workers órfãos, e Gemini 2.5/3.1 passou no
smoke real conjunto (43,97 s).

### Gate de coexistência CUDA com diarização

Antes de habilitar diarização por padrão, medir Parakeet, XTTS e Pyannote
carregados simultaneamente na RTX 2060 de 6 GiB e medir também RSS/RAM do host.
O último smoke observou aproximadamente 1.358 MiB para Parakeet e 2.034 MiB
para XTTS, totalizando 3.392 MiB de VRAM. Isso deixa margem nominal de cerca de
2,5 GiB, mas ainda não prova que Pyannote, kernels temporários e fragmentação
caibam juntos. O aceite exige load/warm-up simultâneo, uma diarização real e
três turnos STT/LLM/TTS sem OOM, com cleanup. Se não couber, a política deve
usar scheduling/offload explícito; não reduzir guards nem mascarar OOM.
