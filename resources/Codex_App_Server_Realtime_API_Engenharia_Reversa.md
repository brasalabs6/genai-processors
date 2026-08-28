> **Aviso de compatibilidade:** O contrato autoritativo é o bundle gerado pelo binário instalado com `codex app-server generate-json-schema`. Este documento descreve a build/branch observada e inclui comportamento interno útil para investigação; campos experimentais podem mudar sem versionamento semântico.

# Codex App Server Realtime API

Contratos, eventos, transporte, WebRTC, handoffs, aprovações e plano completo de integração

# Sumário executivo

Sim, outro programa pode integrar-se diretamente ao Codex App Server sem usar a interface TUI. O programa deve tratar o app-server como um processo/serviço de controle bidirecional: abre um transporte local, executa o handshake de inicialização, cria ou retoma uma thread e chama os métodos experimentais `thread/realtime/*`. Para browser ou WebView, a arquitetura recomendada é WebRTC para mídia e JSON-RPC para controle.

A expressão “acessar a API diretamente” precisa ser definida com precisão. O app-server não é um REST público hospedado: é uma API local do runtime Codex. O cliente pode iniciar o binário no modo `app-server` por stdio, ou conectar a um listener já iniciado. Isso não utiliza a TUI. Eliminar também o binário do app-server exigiria reimplementar partes do Codex Core ou depender de endpoints privados e instáveis, o que não é necessário para o objetivo de interoperabilidade.

> **Conclusão operacional:** Use o App Server como sidecar/daemon e mantenha o frontend responsável por microfone, reprodução e RTCPeerConnection. Não exponha o JSON-RPC bruto na internet e não tente obter acesso por replay de cookies, tokens privados ou bypass de entitlement.

| Pergunta | Resposta objetiva |
| --- | --- |
| É possível usar sem a TUI? | Sim. `codex app-server` é um serviço/processo, não a interface de terminal interativa. |
| O browser conecta diretamente? | Não ao listener WS nativo observado: requisições com `Origin` recebem 403. Use bridge local Node/Rust ou stdio. |
| Há voz full duplex? | Sim no transporte WebRTC: o browser negocia mídia e recebe o answer SDP por notificação JSON-RPC. |
| O start retorna o SDP? | Não. A resposta é `{}`; o answer chega depois em `thread/realtime/sdp`. |
| Ter app-server logado garante o modelo? | Garante a configuração local existente, mas o backend ainda aplica routing, feature flags e entitlement. |
| A API é estável? | Não. Todos os métodos realtime estão marcados como experimentais. |

# 1. Escopo, evidência e classificação de confiança

Este documento combina três níveis de evidência: contrato público do App Server, estruturas Rust serializadas no repositório e comportamento interno observável do gerenciador realtime. Cada afirmação importante deve ser verificada contra o schema gerado pela versão instalada antes de produzir um cliente em produção.

| Classe | O que inclui | Como usar |
| --- | --- | --- |
| Contrato exposto | Nomes de métodos, parâmetros, respostas e notificações descritos no README e schemas gerados. | Pode orientar implementação; ainda é experimental. |
| Contrato serializado | Structs Rust com `serde`, `schemars` e `ts-rs`. | Alta confiança sobre nomes camelCase e optionalidade na build observada. |
| Comportamento interno | Defaults, filas, roteamento de handoffs, auth e interrupção no Codex Core. | Útil para debug; não assumir estabilidade. |
| Inferência de produto | Relação entre Work/Codex desktop, GPT-Live e endpoints upstream. | Tratar como hipótese; não acoplar o produto a aliases/endpoints internos. |

- Baseline de pesquisa: branch `main` de `openai/codex`, consultada em 29 de julho de 2026.
- O release observado no mesmo dia era `0.147.0-alpha.1`; a branch principal pode avançar independentemente.
- A fonte autoritativa para a máquina do usuário é `codex app-server generate-json-schema --out DIR`.
- O projeto entregue inclui `npm run schema:sync` para congelar esse bundle por versão.

# 2. Terminologia essencial

| Termo | Definição |
| --- | --- |
| App Server | Processo Codex que expõe JSON-RPC bidirecional para UIs ricas. Pode operar por stdio, WebSocket ou Unix socket. |
| TUI | Interface interativa de terminal. Não é necessária para esta integração. |
| Thread | Conversa persistente ou efêmera entre usuário e agente; contém turns e items. |
| Turn | Unidade de execução agentic iniciada por entrada do usuário e finalizada com status/itens. |
| Item | Mensagem, raciocínio, comando, mudança de arquivo, chamada de ferramenta ou outro elemento da execução. |
| Realtime session | Sessão de voz/texto vinculada a uma thread; possui lifecycle próprio. |
| Realtime session ID | Identificador da sessão upstream realtime, não o threadId do Codex. |
| Control plane | JSON-RPC entre cliente, bridge e app-server. |
| Media plane | Fluxo de áudio WebRTC ou chunks base64 no caminho WebSocket. |
| Handoff/delegation | Encaminhamento entre a camada realtime e o agente Codex que executa trabalho profundo. |
| Sideband | Canal de controle/eventos associado à mesma call realtime, separado da mídia. |
| Entitlement | Autorização server-side que determina disponibilidade de produto/modelo; não é criado pelo protocolo local. |

# 3. Arquitetura recomendada

![Figura 1 — Separação entre UI, bridge, App Server, Codex Core e backend realtime.](architecture.png)

O frontend deve possuir os dispositivos de áudio e o RTCPeerConnection. O app-server recebe o SDP offer, cria a sessão no backend autorizado e publica o SDP answer como notificação. O bridge local existe porque o listener WebSocket experimental do app-server rejeita requests que carregam `Origin`; navegadores incluem esse header por padrão.

## 3.1 Modos de implantação

| Modo | Topologia | Vantagens | Riscos/limites |
| --- | --- | --- | --- |
| Spawn + stdio | Bridge inicia `codex app-server --listen stdio://`. | Framing simples, local, recomendado; lifecycle alinhado à UI. | Cada console cria seu processo; gerenciar shutdown. |
| Attach WebSocket | Bridge Node conecta a `ws://127.0.0.1:4500`. | Reutiliza daemon já iniciado. | Listener é experimental; não conectar browser diretamente. |
| Unix socket | Cliente nativo usa upgrade WebSocket sobre socket local. | Controle local robusto em Unix. | Mais implementação; browser precisa bridge. |
| Endpoint remoto próprio | Seu backend encapsula o app-server com autenticação. | Multi-cliente e observabilidade centralizada. | Exige isolamento por tenant e forte segurança; não expor RPC cru. |

# 4. Protocolo de fio JSON-RPC

O protocolo é semelhante a JSON-RPC 2.0, mas omite o membro literal `"jsonrpc":"2.0"`. Em stdio, cada envelope é um objeto JSON completo em uma única linha. Em WebSocket, cada frame de texto contém uma mensagem completa.

```json
// request
{"id": 7, "method": "thread/realtime/stop", "params": {"threadId": "thr_123"}}

// response
{"id": 7, "result": {}}

// notification
{"method": "thread/realtime/closed", "params": {"threadId": "thr_123", "reason": null}}

// server-initiated request: MUST receive a response
{"id": 61, "method": "item/commandExecution/requestApproval", "params": {...}}
{"id": 61, "result": {"decision": "accept"}}
```

## 4.1 Correlação e ordenação

- Preserve o `id` exatamente; respostas podem chegar fora de ordem.
- Notificações não possuem `id` e não recebem acknowledgement.
- Requests iniciados pelo servidor possuem `method` e `id`; tratá-los como notificações causa deadlock.
- Deltas devem ser concatenados na ordem recebida por thread/item/role.
- Em reconexão, não reaproveite um mapa de requests pendentes da conexão anterior.

## 4.2 Backpressure

O servidor usa filas limitadas entre ingresso, processamento e escrita. Quando o ingresso satura, requests novos podem receber código `-32001` e mensagem `Server overloaded; retry later.`. O cliente deve aplicar exponential backoff com jitter e não reenviar operações não idempotentes sem conhecer o resultado anterior.

```text
delay = min(cap, base * 2**attempt)
actual = random.uniform(delay * 0.5, delay * 1.5)
retry only when:
  error.code == -32001
  AND operation is safe/idempotent or has an application idempotency key
```

# 5. Transportes do App Server

| Transporte | Inicialização | Framing | Status |
| --- | --- | --- | --- |
| stdio | `--listen stdio://` ou default | JSONL: uma mensagem por linha | Preferido para sidecar local |
| WebSocket | `--listen ws://IP:PORT` | Um frame de texto por mensagem | Experimental/unsupported |
| Unix socket | `--listen unix://` ou PATH | HTTP Upgrade + frames WebSocket | Controle local Unix |
| off | `--listen off` | Nenhum listener local | Somente outros modos internos |

## 5.1 Restrição de Origin

> **Impacto no Vite:** O listener WebSocket do app-server responde 403 a qualquer request com header `Origin`. Um browser padrão não consegue abrir esse WebSocket diretamente. O projeto entregue usa um bridge local que aceita o browser e encaminha mensagens ao app-server por stdio ou WebSocket Node.

## 5.2 Health probes

- `GET /readyz`: 200 quando o listener aceita conexões.
- `GET /healthz`: 200 apenas sem `Origin`.
- Health não substitui o handshake JSON-RPC nem confirma entitlement realtime.

# 6. Handshake obrigatório

Cada conexão deve executar uma única inicialização antes de qualquer outro método. O realtime exige opt-in experimental por conexão.

```json
{"method":"initialize","id":0,"params":{
  "clientInfo":{"name":"our_realtime_client","title":"Our Realtime Client","version":"1.0.0"},
  "capabilities":{"experimentalApi":true}
}}

// aguardar resposta do id 0
{"method":"initialized","params":{}}
```

| Regra | Falha esperada |
| --- | --- |
| Request normal antes do handshake | `Not initialized` |
| Segundo initialize na mesma conexão | `Already initialized` |
| Realtime sem experimentalApi | Método experimental rejeitado/indisponível |
| Nome do cliente empresarial não reconhecido | Pode afetar identificação em compliance logs; registrar cliente quando necessário |

## 6.1 Capabilities úteis

Além de `experimentalApi`, builds recentes aceitam opt-out exato de notificações e capabilities para forms MCP, attestation e outros recursos. Declare apenas o que o cliente realmente implementa. Em especial, não anuncie `requestAttestation` sem conseguir responder ao request `attestation/generate`.

# 7. Thread lifecycle antes do realtime

A sessão realtime é escopada a uma thread carregada. O cliente deve criar, retomar ou bifurcar uma thread antes de chamar start.

```json
{"method":"thread/start","id":1,"params":{
  "cwd":"/workspace/project",
  "ephemeral":true,
  "sandbox":"workspaceWrite",
  "approvalPolicy":"onRequest"
}}
// extrair result.thread.id
```

| Operação | Uso |
| --- | --- |
| thread/start | Nova conversa; aceita cwd, model, sandbox, approvalPolicy e vários overrides. |
| thread/resume | Carrega uma thread existente pelo ID. |
| thread/fork | Cria uma nova thread com histórico copiado. |
| thread/read | Inspeciona estado/histórico quando necessário. |
| thread/archive | Arquiva quando o produto mantém histórico. |

> **Feature gate:** Mesmo com método disponível, o request processor verifica `Feature::RealtimeConversation` na thread. A falha típica informa que a thread não suporta realtime. Isso pode depender da configuração resolvida para o cwd, feature flags e rollout.

# 8. Catálogo completo de métodos realtime

## 8.1 thread/realtime/listVoices

| Campo | Tipo | Obrigatório | Semântica |
| --- | --- | --- | --- |
| params | {} | Sim | Objeto vazio. |
| result.voices | RealtimeVoicesList | Sim | Lista/estrutura de vozes builtin suportadas pela build. |

```json
{"method":"thread/realtime/listVoices","id":2,"params":{}}
{"id":2,"result":{"voices":[/* shape gerada pela build */]}}
```

Não fixe uma enum manual sem consultar a resposta. O projeto aceita tanto lista de strings quanto itens com `id`/`name`, pois a forma concreta de `RealtimeVoicesList` pode evoluir.

## 8.2 thread/realtime/start

Inicia uma sessão realtime vinculada à thread. A resposta sincrônica é sempre um objeto vazio quando o request é aceito; os sinais de sessão e SDP são assíncronos.

| Campo | Tipo | Req. | Semântica |
| --- | --- | --- | --- |
| threadId | string | Sim | Thread carregada que será dona da sessão. |
| outputModality | `text` \| `audio` | Sim | Modalidade emitida pelo modelo; independente do transporte. |
| transport | websocket \| webrtc | Não | Ausente = WebSocket. WebRTC exige offer SDP. |
| version | v1 \| v2 \| v3 | Não | Override da versão somente para a sessão. |
| model | string | Não | Override da configuração/modelo realtime somente para a sessão. |
| voice | RealtimeVoice/string | Não | Voz selecionada. |
| prompt | omitido \| null \| string | Não | Campo com semântica de três estados; ver seção dedicada. |
| realtimeSessionId | string\|null | Não | ID upstream; normalmente deixar ausente/null. |
| includeStartupContext | boolean\|null | Não | Default true; false remove contexto gerado pelo Codex. |
| initialItems | InitialItem[]\|null | Não | Somente V3; semeia histórico textual completo. |
| clientManagedHandoffs | boolean\|null | Não | Default false; true desliga entrega automática de respostas Codex. |
| flushTranscriptTailOnSessionEnd | boolean\|null | Não | Default false interno; encaminha cauda restante ao Codex ao encerrar. |
| codexResponsesAsItems | boolean\|null | Não | Entrega experimental como itens de conversa em vez de handoff append. |
| codexResponseItemPrefix | string\|null | Não | Prefixo experimental para response items. |
| codexResponseHandoffMode | thinking\|commentary\|bemTags | Não | V3; default thinking. V1/V2 ignoram. |
| codexResponseHandoffChannelPrefixes | map<string,string[]> | Não | Overrides BEM para analysis/commentary/final. |

```json
{"method":"thread/realtime/start","id":40,"params":{
  "threadId":"thr_123",
  "version":"v3",
  "outputModality":"audio",
  "transport":{"type":"webrtc","sdp":"v=0\r\no=..."},
  "includeStartupContext":true,
  "clientManagedHandoffs":false,
  "flushTranscriptTailOnSessionEnd":true,
  "codexResponseHandoffMode":"bemTags",
  "prompt":"You are the voice interface for a Codex agent."
}}
{"id":40,"result":{}}
```

## 8.3 Semântica tri-state do prompt

| Wire value | Significado |
| --- | --- |
| campo omitido | Usar prompt backend default/configurado do Codex. |
| `prompt: null` | Iniciar sem o prompt default. |
| `prompt: ""` | Também iniciar sem o prompt default. |
| string não vazia | Substituir o prompt por esse conteúdo. |

Esse comportamento existe porque a struct usa double option: o servidor distingue ausência do campo de presença explícita com valor nulo. Clientes que normalizam `undefined` e `null` para o mesmo valor quebram essa escolha.

## 8.4 initialItems

| Restrição | Valor |
| --- | --- |
| Versão | Somente V3 |
| Roles | user, developer, assistant |
| Máximo de itens | 128 |
| Máximo estimado por item | 8.192 tokens |
| Máximo estimado total | 8.192 tokens |

```json
"initialItems": [
  {"role":"developer","text":"Contexto operacional persistente."},
  {"role":"user","text":"Continue a investigação da sessão anterior."}
]
```

O README observado contém linguagem ligeiramente redundante sobre limite por item e total. Implemente o limite total de 8.192 como restrição efetiva conservadora e valide o erro real da build instalada.

## 8.5 thread/realtime/appendAudio

| Campo | Tipo | Notas |
| --- | --- | --- |
| threadId | string | Thread com sessão ativa. |
| audio.data | string | Bytes de áudio codificados em base64. |
| audio.sampleRate | u32 | Taxa de amostragem. |
| audio.numChannels | u16 | Número de canais. |
| audio.samplesPerChannel | u32? | Ajuda a calcular duração/timing. |
| audio.itemId | string? | Correlação opcional com item. |

```json
{"method":"thread/realtime/appendAudio","id":41,"params":{
  "threadId":"thr_123",
  "audio":{"data":"<base64>","sampleRate":24000,"numChannels":1,"samplesPerChannel":480}
}}
```

> **Codec não declarado:** O DTO não inclui um campo de encoding/codec. Não assuma PCM16 somente pelo sampleRate. Para integração browser, WebRTC evita essa ambiguidade. Para appendAudio, inspecione schemas/config/eventos da build e faça um probe controlado.

## 8.6 thread/realtime/appendText

```json
{"method":"thread/realtime/appendText","id":42,"params":{
  "threadId":"thr_123","text":"Priorize os testes que estão falhando.","role":"user"
}}
```

Roles aceitos: `user`, `developer` ou `assistant`. Clientes antigos que omitem `role` recebem default `user`. Use developer apenas para instrução confiável; não promova texto arbitrário do usuário.

## 8.7 thread/realtime/appendSpeech

```json
{"method":"thread/realtime/appendSpeech","id":43,"params":{
  "threadId":"thr_123","text":"Encontrei três falhas e estou corrigindo a primeira."
}}
```

Esse método representa conteúdo que o modelo realtime deve falar. Ele é útil em orquestração client-managed, atualizações de progresso e integração de resultados externos.

## 8.8 thread/realtime/stop

```json
{"method":"thread/realtime/stop","id":44,"params":{"threadId":"thr_123"}}
{"id":44,"result":{}}
```

Após a resposta, continue consumindo notificações até `thread/realtime/closed`. Faça cleanup local de tracks, AudioContext, timers e RTCPeerConnection mesmo se o stop falhar.

# 9. Catálogo completo de notificações realtime

| Método | Payload | Tratamento do cliente |
| --- | --- | --- |
| thread/realtime/started | threadId, realtimeSessionId?, version | Marcar sessão aceita; registrar versão efetiva. |
| thread/realtime/itemAdded | threadId, item (JSON opaco) | Persistir raw; tolerar novos tipos/campos. |
| thread/realtime/transcript/delta | threadId, role, delta | Concatenar incrementalmente por segmento/role. |
| thread/realtime/transcript/done | threadId, role, text | Substituir/fechar o segmento com texto autoritativo. |
| thread/realtime/outputAudio/delta | threadId, audio chunk | Usado no transporte/chunk path; ordenar e reproduzir conforme formato efetivo. |
| thread/realtime/sdp | threadId, sdp | Aplicar como RTCSessionDescription answer. |
| thread/realtime/error | threadId, message | Exibir, registrar contexto e iniciar cleanup/retry conforme classe. |
| thread/realtime/closed | threadId, reason? | Finalizar lifecycle e recursos locais. |

```json
{"method":"thread/realtime/started","params":{
  "threadId":"thr_123","realtimeSessionId":"rt_456","version":"v3"
}}
{"method":"thread/realtime/transcript/delta","params":{
  "threadId":"thr_123","role":"user","delta":"Analise o "
}}
{"method":"thread/realtime/transcript/done","params":{
  "threadId":"thr_123","role":"user","text":"Analise o repositório inteiro."
}}
```

## 9.1 Regras para transcript

- Não derive o texto final apenas dos deltas; `done.text` é autoritativo.
- Não suponha que role seja uma enum fechada; o contrato de notificação usa string.
- Um delta vazio pode carregar boundary/estado em futuras builds; registre raw.
- Se houver múltiplos streams concorrentes, associe pelo item/session metadata quando presente nos eventos raw.

# 10. Versões realtime e matriz de transporte

| Versão | Nome interno | Handoffs | WebSocket | WebRTC | Observações |
| --- | --- | --- | --- | --- | --- |
| v1 | Legacy Bidi | conversation.handoff.* | Sim | Sim | Comportamento Codex Voice legado. |
| v2 | Realtime Voice API | eventos Realtime convencionais | Sim | Não | Inclui truncation explícito em interrupções. |
| v3 | Frameless Bidi | delegation.* | Sim | Sim | Suporta initialItems e modos de handoff. |

O transporte ausente seleciona WebSocket. Para WebRTC, envie explicitamente `version: v1` ou `v3`; V2 é rejeitado. O projeto Vite desabilita V2 no seletor quando usa WebRTC.

## 10.1 Defaults internos observados

| Constante | Valor observado | Interpretação |
| --- | --- | --- |
| DEFAULT_REALTIME_MODEL | gpt-realtime-1.5 | Fallback para caminho realtime convencional na branch observada. |
| DEFAULT_FRAMELESS_REALTIME_MODEL | gpt-live-1-boulder-alpha | Fallback interno para Frameless/V3. |
| Config/rollout | pode sobrescrever | O nome efetivo em produção pode ser outro alias; não fixe em código cliente. |

> **Não confundir alias com API pública:** Esses nomes são detalhes internos observados no código. O campo `model` permite override, mas disponibilidade real é decidida pelo backend/configuração. Deixar vazio é o primeiro probe correto.

# 11. Negociação WebRTC passo a passo

![Figura 2 — Sequência completa da negociação WebRTC V3.](webrtc-sequence.png)

## 11.1 Preparação do peer

```javascript
const pc = new RTCPeerConnection();
const remoteAudio = document.querySelector("audio");
remoteAudio.autoplay = true;
pc.ontrack = (event) => { remoteAudio.srcObject = event.streams[0]; };

const stream = await navigator.mediaDevices.getUserMedia({
  audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
});
for (const track of stream.getAudioTracks()) pc.addTrack(track, stream);
pc.createDataChannel("oai-events");

const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
```

## 11.2 Start e answer assíncrono

```javascript
await rpc.request("thread/realtime/start", {
  threadId,
  outputModality: "audio",
  version: "v3",
  transport: { type: "webrtc", sdp: offer.sdp }
});

// em handler de notification:
if (method === "thread/realtime/sdp") {
  await pc.setRemoteDescription({ type: "answer", sdp: params.sdp });
}
```

## 11.3 Regras de SDP

- Não gere um SDP manual/minimal; use `createOffer()` depois de adicionar track/transceiver e data channel.
- O data channel deve ser criado antes da offer para que a m-line/aplicação seja negociada.
- A resposta imediata `{}` não significa que a conexão de mídia está pronta.
- Aplique o answer apenas no peer que gerou a offer correspondente.
- Colete `connectionState`, `iceConnectionState`, candidate-pair RTT, jitter e packet loss para debug.
- Em nova tentativa, descarte o peer anterior; não reutilize offer/answer de outra sessão.

# 12. Caminho WebSocket e áudio por chunks

Quando `transport` é omitido ou `{type:"websocket"}`, o Codex Core cria um transporte realtime por WebSocket e o cliente envia áudio via `appendAudio`, recebendo `outputAudio/delta`. Esse caminho é apropriado para clientes nativos que controlam encoding, jitter buffer e reprodução; para web, WebRTC é mais simples e mais natural.

## 12.1 Autenticação observada no caminho WebSocket

O gerenciador realtime tenta resolver credencial em ordem aproximada: API key do provider, bearer token experimental configurado, API key da autenticação Codex e `OPENAI_API_KEY`. Se nenhuma for encontrada, o código pode retornar `realtime conversation requires API key auth`. Esse comportamento é específico do caminho/configuração e não deve ser generalizado para WebRTC desktop.

> **Login não é sinônimo de qualquer transporte:** Uma instalação “logada e funcional” pode ter routing suficiente para WebRTC e ainda não fornecer a credencial esperada pelo caminho WebSocket standalone. Faça probes separados para cada transporte.

# 13. Handoffs, delegações e respostas do Codex

A sessão de voz não precisa executar todo o trabalho. Ela pode delegar tarefas à thread Codex, manter uma conversa curta com o usuário e reinserir resultados. O App Server possui flags para determinar quem controla essa entrega.

| Configuração | Efeito |
| --- | --- |
| clientManagedHandoffs=false | Codex encaminha respostas automaticamente para a sessão realtime. |
| clientManagedHandoffs=true | Somente appends explícitos do cliente produzem handoffs; o programa vira orquestrador. |
| codexResponsesAsItems=true | Respostas automáticas entram como itens de conversa experimentais. |
| codexResponseItemPrefix | Prefixo anexado aos itens automáticos. |
| handoffMode=thinking | V3 envia todo output como append sem canal explícito de thinking. |
| handoffMode=commentary | V3 envia output no canal commentary. |
| handoffMode=bemTags | Envelope BEM decide commentary vs speakable; mantém o envelope no texto. |

## 13.1 Roteamento BEM observado

| Envelope/caso | Canal API |
| --- | --- |
| BEM analysis | commentary |
| BEM commentary | commentary |
| BEM final | speakable |
| Output sem parse válido | speakable |

Os prefixos default são marcadores uppercase entre colchetes; `codexResponseHandoffChannelPrefixes` permite sobrescrever por `analysis`, `commentary` e `final`. O cliente deve registrar o texto raw e o canal efetivo para entender mudanças de comportamento entre builds.

## 13.2 Flush da cauda do transcript

Com `flushTranscriptTailOnSessionEnd=true`, texto de usuário que ainda não foi transformado em delegação no encerramento é encaminhado ao Codex. Isso evita perder uma solicitação quando a call fecha imediatamente após a fala, mas pode iniciar trabalho no momento do shutdown; o produto deve decidir se deseja esse efeito.

# 14. Interrupção e barge-in

No caminho V2, quando o usuário começa a falar durante output de áudio, o core calcula o ponto reproduzido e envia `conversation.item.truncate` com `item_id`, `content_index:0` e `audio_end_ms`. Isso mantém o histórico alinhado ao áudio realmente ouvido. Em V3/GPT-Live, parte desse comportamento é incorporada ao modelo/protocolo, mas o cliente ainda precisa habilitar captura contínua e não bloquear o track de entrada durante playback.

```json
{
  "type":"conversation.item.truncate",
  "item_id":"item_abc",
  "content_index":0,
  "audio_end_ms":1234
}
```

# 15. Requests iniciados pelo servidor

JSON-RPC é bidirecional. Durante uma delegação, o App Server pode pedir aprovação, entrada estruturada, horário ou outras informações. Cada request possui `id` e precisa de uma response com o mesmo `id`. A ausência de resposta pode deixar a execução suspensa.

| Request | Resposta típica | Observação |
| --- | --- | --- |
| item/commandExecution/requestApproval | {decision: accept\|acceptForSession\|decline\|cancel} | Pode incluir command, cwd, permissions, network context e availableDecisions. |
| item/fileChange/requestApproval | {decision: ...} | Pode incluir reason e grantRoot experimental. |
| item/permissions/requestApproval | payload específico de permissions | Não inventar; usar schema da build. |
| item/tool/requestUserInput | resposta estruturada | Renderizar perguntas/campos conforme schema. |
| mcpServer/elicitation/request | {action, content} | Form, openai/form ou URL. |
| currentTime/read | {currentTimeAt: Unix seconds} | Pode ser respondido automaticamente. |
| attestation/generate | {token: opaque} | Somente anunciar capability se o host realmente produz token. |

```json
// request do servidor
{"method":"item/commandExecution/requestApproval","id":61,"params":{
  "threadId":"thr_123","turnId":"turn_123","itemId":"call_123",
  "command":"npm test","cwd":"/workspace","reason":"Run tests"
}}
// response do cliente
{"id":61,"result":{"decision":"accept"}}
// cleanup de lifecycle
{"method":"serverRequest/resolved","params":{"threadId":"thr_123","requestId":61}}
```

## 15.1 Decisões avançadas

Command approvals podem aceitar estruturas como `acceptWithExecpolicyAmendment` e `applyNetworkPolicyAmendment`. Renderize `availableDecisions` quando presente; isso evita oferecer decisões que a build não aceita. O console entregue fornece botões simples e uma resposta JSON manual para investigação de novos payloads.

# 16. Filas, budgets e latência interna

| Recurso | Valor observado |
| --- | --- |
| Fila de input de áudio | 256 |
| Fila de input de texto | 64 |
| Fila de handoff | 64 |
| Fila de eventos de saída | 256 |
| Budget de startup context | 5.300 tokens estimados |
| Budget de assistant output | 1.000 tokens estimados |
| Flush interval de handoff | 200 ms |
| initialItems | 128 itens / 8.192 tokens estimados |

Esses valores explicam sintomas como atraso, backpressure e truncation, mas são detalhes internos. Instrumente timestamps em quatro pontos: captura local, envio RPC, recebimento de transcript/evento e playback. A medição end-to-end é mais confiável do que pressupor que uma fila específica é o gargalo.

# 17. Erros e estratégia de recuperação

| Classe | Exemplo | Ação |
| --- | --- | --- |
| Handshake | Not initialized / Already initialized | Recriar conexão e executar sequência correta. |
| Experimental API | método não permitido | Enviar experimentalApi=true e verificar build. |
| Feature gate | thread does not support realtime | Verificar feature/config/cwd; criar nova thread após mudança. |
| Transporte | V2 unsupported for WebRTC | Selecionar V1 ou V3. |
| Credencial | requires API key auth | Testar WebRTC/config autorizada ou configurar API key suportada. |
| Entitlement/routing | upstream 4xx/5xx ou SDP ausente | Não contornar; verificar conta, rollout e logs. |
| Overload | -32001 | Retry com backoff e jitter. |
| WebRTC | ICE failed / remote SDP inválido | Descartar peer, coletar stats e renegociar. |
| Sessão fechada | thread/realtime/closed | Cleanup idempotente; decidir reconexão. |
| Approval pendente | turn sem progresso | Responder server request com mesmo id. |

## 17.1 Timeout recomendado por fase

| Fase | Timeout inicial sugerido | Observação |
| --- | --- | --- |
| Bridge connect | 10 s | Falha local imediata normalmente. |
| initialize | 20 s | Inclui startup do app-server. |
| thread/start | 45 s | Config e carregamento podem custar mais. |
| realtime/start request | 60 s | Resposta `{}` não encerra negociação. |
| thread/realtime/sdp | 30–60 s após start | Tratar como evento separado. |
| appendText/Speech | 15 s | Request pequeno. |
| stop | 15 s | Sempre executar cleanup local em finally. |

# 18. Estado e concorrência do cliente

![Figura 3 — Estados mínimos para impedir starts concorrentes e peers órfãos.](state-machine.png)

- Mantenha no máximo uma sessão realtime ativa por thread até provar suporte contrário.
- Associe cada SDP ao peer e thread que originaram a offer.
- Bloqueie novo start durante STARTING/LIVE/STOPPING.
- Cleanup deve ser idempotente e parar tracks, meter, timers e áudio remoto.
- No close do transporte JSON-RPC, rejeite promises pendentes e invalide requests do servidor.
- Em SPA, execute cleanup em `beforeunload` e ao trocar de workspace/thread.

# 19. Autenticação, sessão e entitlement

O app-server pode estar autenticado por fluxos diferentes, e o transporte realtime pode resolver headers/credenciais de maneiras diferentes. O código observado também adiciona headers de sessão/thread e flags alpha conforme versão. Isso é implementação interna e pode variar.

| Camada | Responsabilidade |
| --- | --- |
| Cliente local | Identificar-se no initialize, proteger bridge e responder approvals. |
| Codex Auth/config | Fornecer credencial/provider/config resolvida ao core. |
| Backend realtime | Validar token, modelo, conta, rollout, call/session e limites. |
| Produto desktop | Pode injetar URLs, headers, attestation e aliases não presentes no standalone. |

> **Limite da engenharia reversa:** Mapear contratos e comportamento para interoperabilidade é válido. Não implemente extração de cookies/tokens privados, replay de credenciais do app oficial, falsificação de attestation ou bypass de entitlement. Além de inseguro e frágil, isso não é necessário quando o app-server já está logado e expõe o fluxo suportado na instalação.

# 20. Plano de engenharia reversa reproduzível

## 20.1 Congelar a versão

```bash
codex --version
codex app-server generate-json-schema --out captures/schema-$(date +%Y%m%d)
codex app-server generate-ts --out captures/ts-$(date +%Y%m%d)
git rev-parse HEAD   # se estiver compilando do source
```

## 20.2 Capturar o fio

- No modo stdio, interponha um proxy JSONL que grave timestamp, direção, method, id, bytes e hash do payload.
- Mantenha SDP e áudio em arquivos separados; redija tokens e dados pessoais antes de compartilhar traces.
- Grave stderr JSON com `LOG_FORMAT=json` e RUST_LOG apropriado.
- Correlacione threadId, realtimeSessionId, request id, WebRTC stats e timestamps.

## 20.3 Matriz de probes

| Probe | Variáveis | Resultado a registrar |
| --- | --- | --- |
| Start mínimo | v1/v3, model omitido, voice omitida | result, started.version, sdp, error/closed |
| Prompt tri-state | omitido/null/empty/custom | diferença de comportamento e eventos |
| Startup context | true/false | initial items/context observável |
| Handoffs | managed false/true | entrega automática vs explícita |
| Response items | false/true + prefix | itemAdded e transcript |
| BEM modes | thinking/commentary/bemTags | canal e fala resultante |
| Interrupção | falar durante playback | latência de barge-in e truncation |
| Approval | comando que exige permissão | request, decisions, resolved e item/completed |
| Reconnect | derrubar bridge/peer | cleanup e capacidade de nova sessão |

## 20.4 Diff de contratos

```bash
# Exemplo conceitual
jq -S . old/schema.json > old.sorted.json
jq -S . new/schema.json > new.sorted.json
diff -u old.sorted.json new.sorted.json

Classifique mudanças:
  additive optional      -> compatível
  new enum variant       -> cliente deve tolerar unknown
  required field         -> breaking
  rename/method removal  -> breaking
  semantic/default change-> breaking comportamental
```

# 21. Blueprint de um cliente direto

O agente implementador pode usar Node, Rust, Go ou outra linguagem. A separação de componentes abaixo evita acoplamento entre framing, lifecycle e UI.

| Componente | Responsabilidade |
| --- | --- |
| TransportAdapter | stdio JSONL, WebSocket ou Unix socket; read/write envelopes. |
| RpcMultiplexer | IDs, promises/futures, timeouts, notifications e server requests. |
| CodexSession | initialize, thread lifecycle, feature/config probes. |
| RealtimeSession | start/stop/appends, state machine e event reducers. |
| MediaController | getUserMedia/WebRTC ou audio chunk codec/jitter. |
| ApprovalController | fila de server requests, políticas e UI segura. |
| TraceRecorder | logs estruturados, redaction e export de sessão. |
| CompatibilityLayer | capabilities por schema/version e fallbacks. |

```typescript
interface Transport {
  send(envelope: RpcEnvelope): Promise<void>;
  onMessage(handler: (envelope: RpcEnvelope) => void): Unsubscribe;
  close(): Promise<void>;
}

interface RealtimeApi {
  listVoices(): Promise<unknown>;
  start(params: RealtimeStartParams): Promise<void>;
  appendText(threadId: string, text: string, role?: Role): Promise<void>;
  appendSpeech(threadId: string, text: string): Promise<void>;
  appendAudio(threadId: string, frame: AudioFrame): Promise<void>;
  stop(threadId: string): Promise<void>;
}
```

# 22. Interface Vite entregue

O projeto `codex-realtime-console` acompanha este documento. Ele foi projetado como um laboratório de compatibilidade e uma base funcional, não apenas como mock visual.

| Área da UI | Capacidades |
| --- | --- |
| Bridge local | URL, connect/disconnect, status e logs. |
| Thread | cwd, resume ID, sandbox, approvalPolicy, model, ephemeral, overrides JSON. |
| Áudio | input/output device, mute, meter, setSinkId quando suportado. |
| Realtime | V1/V3, output modality, model, voice, prompt tri-state, startup context. |
| Handoffs | managed, flush tail, responses as items, mode, prefixes, initialItems. |
| Conversa | transcript delta/done, appendText, appendSpeech. |
| WebRTC | RTT, jitter, packets lost, ICE state. |
| Server requests | aprovações, resposta JSON manual, currentTime automático. |
| Wire Inspector | até 400 eventos raw e RPC manual. |

## 22.1 Execução

```bash
cd codex-realtime-console
cp .env.example .env
npm install
npm run dev
# abrir http://127.0.0.1:5173
```

## 22.2 Spawn mode

```dotenv
APP_SERVER_MODE=spawn
CODEX_COMMAND=codex
CODEX_ARGS_JSON=["app-server","--listen","stdio://"]
```

## 22.3 Attach mode

```bash
# terminal A
codex app-server --listen ws://127.0.0.1:4500

# .env do console
APP_SERVER_MODE=ws
APP_SERVER_WS_URL=ws://127.0.0.1:4500
```

## 22.4 Configuração inicial recomendada

| Campo | Primeiro teste |
| --- | --- |
| Version | v3 |
| Output modality | audio |
| Model | vazio |
| Voice | primeira retornada ou vazio |
| Prompt | default ou custom curto |
| Startup context | true |
| Managed handoffs | false |
| Flush tail | true para laboratório |
| Responses as items | false |
| Handoff mode | bemTags |
| Sandbox | workspaceWrite |
| Approval | onRequest |

# 23. Testes e validação

| Teste | Comando/ação | Critério |
| --- | --- | --- |
| TypeScript | `npm run typecheck` | Sem erros. |
| Bridge framing | `npm run smoke:bridge` | Request/response/notification passam por WS <-> stdio. |
| Build | `npm run build` | Bundle Vite produzido. |
| Schema sync | `npm run schema:sync` | Bundle da instalação gravado. |
| Handshake real | Conectar e observar initialize | Status connected; sem Not initialized. |
| Thread | start/resume | threadId aparece. |
| WebRTC | start v3 | started + sdp + ICE connected/completed. |
| Áudio | falar e ouvir | transcript delta/done e playback. |
| Delegação | pedir tarefa agentic | itens/approvals e atualização falada. |
| Shutdown | stop/desconectar | tracks e peer fechados; closed observado. |

## 23.1 Teste de contrato automatizado sugerido

```text
Given a fresh initialized connection:
  assert listVoices returns result.voices
  create ephemeral thread
  create browser offer with audio + oai-events
  start v3 and assert immediate result == {}
  wait for started(threadId, version=v3)
  wait for sdp(threadId, non-empty)
  apply answer and wait for ICE success
  appendText("say only ping")
  assert transcript or item event arrives
  stop and wait for closed
Always redact SDP credentials and auth headers in persisted fixtures.
```

# 24. Segurança de produção

- Bind do bridge e app-server em loopback por padrão.
- Adicione autenticação mútua ou token forte antes de qualquer bind não local.
- Não permita que parâmetros do browser escolham arbitrariamente CODEX_COMMAND/CODEX_CWD.
- Faça allowlist de métodos se expuser uma API de produto; não faça proxy irrestrito.
- Mantenha sandbox de menor privilégio e approvalPolicy compatível com risco.
- Trate `thread/shellCommand` como execução unsandboxed com acesso total.
- Trate `process/spawn` e operações fs como capacidades de host.
- Associe uma instância/thread a um usuário/tenant; não misture HOME, cwd ou credenciais.
- Não grave áudio/transcripts por default sem consentimento e política de retenção.
- Remova tokens, SDP ICE credentials, paths pessoais e conteúdo sensível de traces compartilhados.

## 24.1 Threat model mínimo

| Ameaça | Mitigação |
| --- | --- |
| Site malicioso acessa bridge localhost | Token na query, validação de Origin permitida pelo bridge, bind loopback. |
| RPC arbitrário executa comandos | Allowlist, sandbox, approvals, não expor raw RPC. |
| Confusão entre tenants | Processos e CODEX_HOME separados; ACL por conexão. |
| Replay de request approval | IDs por conexão, remover após serverRequest/resolved. |
| Prompt injection em developer role | Somente fonte confiável pode enviar role developer. |
| Trace vaza segredos | Redaction estruturada e retenção curta. |
| Endpoint interno muda | Adapter + schema diff + feature probe; não acoplar private backend. |

# 25. Checklist para o próximo agente

1. Executar `generate-json-schema` e arquivar junto à versão do binário.
1. Confirmar nomes exatos de sandbox/approvalPolicy aceitos pela instalação.
1. Executar listVoices e salvar a resposta raw.
1. Começar com V3 WebRTC, model/voice omitidos.
1. Confirmar evento started e versão efetiva antes de declarar sucesso.
1. Confirmar que sdp chega como notification, não result.
1. Implementar requests bidirecionais antes de testar delegação agentic.
1. Instrumentar SDP/ICE/transcript/handoff com timestamps.
1. Testar prompt omitido vs null vs custom.
1. Testar managed handoffs false e true.
1. Testar stop em estados starting, live e error.
1. Implementar unknown-field/unknown-event tolerance.
1. Não tentar contornar entitlement se o upstream recusar.
1. Produzir um relatório de diff entre contrato observado e schema da instalação.

# Apêndice A — TypeScript de referência

```typescript
type RealtimeVersion = "v1" | "v2" | "v3";
type OutputModality = "text" | "audio";
type Role = "user" | "developer" | "assistant";
type HandoffMode = "thinking" | "commentary" | "bemTags";

type AudioChunk = {
  data: string;
  sampleRate: number;
  numChannels: number;
  samplesPerChannel?: number;
  itemId?: string;
};

type RealtimeStartParams = {
  threadId: string;
  outputModality: OutputModality;
  clientManagedHandoffs?: boolean | null;
  flushTranscriptTailOnSessionEnd?: boolean | null;
  codexResponsesAsItems?: boolean | null;
  codexResponseItemPrefix?: string | null;
  codexResponseHandoffMode?: HandoffMode | null;
  codexResponseHandoffChannelPrefixes?: Record<string,string[]> | null;
  model?: string | null;
  includeStartupContext?: boolean | null;
  initialItems?: Array<{role:Role;text:string}> | null;
  prompt?: string | null; // omission is semantically distinct
  realtimeSessionId?: string | null;
  transport?: {type:"websocket"} | {type:"webrtc";sdp:string};
  version?: RealtimeVersion | null;
  voice?: string | null;
};
```

# Apêndice B — Transcript de uma sessão mínima

```text
C → S  {"id":0,"method":"initialize","params":{"clientInfo":{"name":"lab","title":"Lab","version":"1"},"capabilities":{"experimentalApi":true}}}
S → C  {"id":0,"result":{"userAgent":"...","codexHome":"...","platformFamily":"...","platformOs":"..."}}
C → S  {"method":"initialized","params":{}}
C → S  {"id":1,"method":"thread/start","params":{"ephemeral":true,"sandbox":"workspaceWrite","approvalPolicy":"onRequest"}}
S → C  {"id":1,"result":{"thread":{"id":"thr_123","ephemeral":true,...}}}
C → S  {"id":2,"method":"thread/realtime/start","params":{"threadId":"thr_123","version":"v3","outputModality":"audio","transport":{"type":"webrtc","sdp":"..."}}}
S → C  {"id":2,"result":{}}
S → C  {"method":"thread/realtime/started","params":{"threadId":"thr_123","realtimeSessionId":"rt_456","version":"v3"}}
S → C  {"method":"thread/realtime/sdp","params":{"threadId":"thr_123","sdp":"..."}}
S → C  {"method":"thread/realtime/transcript/delta","params":{"threadId":"thr_123","role":"user","delta":"Olá"}}
S → C  {"method":"thread/realtime/transcript/done","params":{"threadId":"thr_123","role":"user","text":"Olá"}}
C → S  {"id":3,"method":"thread/realtime/stop","params":{"threadId":"thr_123"}}
S → C  {"id":3,"result":{}}
S → C  {"method":"thread/realtime/closed","params":{"threadId":"thr_123","reason":null}}
```

# Apêndice C — Artefatos entregues

| Arquivo | Finalidade |
| --- | --- |
| Codex_App_Server_Realtime_API_Engenharia_Reversa.docx | Documento técnico formatado. |
| Codex_App_Server_Realtime_API_Engenharia_Reversa.md | Fonte Markdown pesquisável. |
| codex-realtime-console.zip | Projeto Vite + bridge + testes. |
| spec/codex-realtime-contract.json | Mapa machine-readable de métodos, eventos, defaults e limites. |
| scripts/sync-schema.mjs | Geração do contrato autoritativo da instalação. |
| scripts/smoke-bridge.mjs | Teste de framing/routing do bridge. |


---

# Apêndice D — Fontes e rastreabilidade

| ID | Fonte | URL |
| --- | --- | --- |
| [S1] | OpenAI Codex repository — `codex-rs/app-server/README.md`. Protocolo, transportes, lifecycle, métodos realtime, WebRTC, eventos e approvals. | https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md |
| [S2] | OpenAI Codex repository — `codex-rs/app-server-protocol/src/protocol/v2/realtime.rs`. Structs serializadas e schemas exatos da API realtime. | https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/realtime.rs |
| [S3] | OpenAI Codex repository — `codex-rs/core/src/realtime_conversation.rs`. Defaults, versões, filas, auth, handoffs, transcript tail e interrupção. | https://github.com/openai/codex/blob/main/codex-rs/core/src/realtime_conversation.rs |
| [S4] | OpenAI Codex repository — `codex-rs/app-server/src/request_processors/turn_processor.rs`. Feature gate, defaults e mapeamento dos métodos para Ops. | https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/turn_processor.rs |
| [S5] | OpenAI Codex releases. Baseline de versão observada em 29 Jul 2026. | https://github.com/openai/codex/releases |

Rastreabilidade por tema: transportes/handshake/backpressure [S1]; DTOs e optionalidade [S2]; defaults/queues/auth/interruption [S3]; feature gate/defaults request processor [S4]; versão temporal [S5].

> **Regra final:** Antes de qualquer implementação definitiva, substitua os tipos curados deste documento pelos schemas gerados pelo `codex app-server` instalado e registre o hash/versão usados no teste.
