# Plano de execução — Leonidas

Versão: 20260730-0041

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

Parar somente quando os milestones Gemini e cascata estiverem implementados e
validados empiricamente, com o milestone Gemini commitado/tagueado, ou quando
todo trabalho restante depender da mesma credencial/capacidade externa
indisponível. Nesse caso, manter a suíte e comandos prontos, registrar a
evidência offline e declarar exatamente o que falta para o smoke real.

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
