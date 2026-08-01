# Leonidas — Especificação da Web UI

## 1. Princípios

- Standalone, local-first, sem dependência de AI Studio.
- Vite + TypeScript sem framework de componentes adicional.
- Estado explícito: conexão, sessão, captura e geração nunca são combinados em
  um único booleano.
- Alterar controles edita somente o draft. Reinícios acontecem apenas por ação
  explícita.
- Teclado, leitores de tela, contraste e redução de movimento são requisitos.

## 2. Estrutura visual

Desktop usa uma grade de 12 colunas:

```text
┌──────────────────────────────────────────────────────────────┐
│ Leonidas   conexão · sessão      Start Stop Apply & Restart │
├──────────────────────────────┬───────────────────────────────┤
│ Preview tela/câmera          │ Conversa e transcrições      │
│ Mic · Câmera · Tela          │ input textual                │
├──────────────────────────────┼───────────────────────────────┤
│ Métricas de latência         │ Configuração                 │
│ TTFA · p50 · p95 · resposta │ modelo · voz · objetivo      │
├──────────────────────────────┴───────────────────────────────┤
│ Logs: filtros · tail · arquivos                             │
└──────────────────────────────────────────────────────────────┘
```

Até 900 px, painéis viram uma coluna. A barra de sessão permanece sticky. Até
600 px, ações usam duas linhas e nunca dependem apenas de ícones.

## 3. Estados

Conexão: `connecting`, `connected`, `reconnecting`, `disconnected`.

Sessão: `stopped`, `starting`, `running`, `stopping`, `error`.

Agente: `ready`, `listening`, `observing`, `thinking`, `speaking`,
`interrupted`, `error`.

Regras:

- Start só habilita com WebSocket conectado, sessão parada e config ativa.
- Stop habilita durante starting/running/error e é idempotente.
- Apply habilita quando há draft válido e dirty fields.
- Apply & Restart mostra confirmação quando a sessão está running.
- `interrupted` e `stopped` chamam `PcmPlayer.clear()` sincronamente.
- falha ao criar ou retomar `AudioContext` mostra erro `Áudio indisponível`
  com ação para desbloquear novamente a saída; nunca é rotulada como mensagem
  WebSocket inválida.
- Controles de captura continuam independentes da sessão, mas não enviam mídia
  quando ela não está running.

## 4. Componentes

### SessionBar

- badges de REST, WebSocket e sessão;
- Start, Stop e Apply & Restart;
- duração da sessão;
- erro resumido com ação de recuperação.

### CapturePanel

- preview 16:9;
- toggles separados de microfone, câmera e tela;
- câmera e tela são mutuamente exclusivas;
- indicador de permissão, resolução, FPS efetivo e frames descartados;
- headphone hint quando echo cancellation não for suficiente.

### ConversationPanel

- histórico limitado a 100 itens em memória;
- papéis usuário, Leonidas e sistema;
- transcrições intermediárias atualizam a mesma linha; final cria item;
- input envia turno completo; Enter envia e Shift+Enter quebra linha;
- conteúdo não é persistido.

### ConfigPanel

Seções básica, objetivo e avançada.

Básica:

- pipeline Gemini Live ou Cascata local;
- modelo Gemini ou modelo Groq, conforme a pipeline;
- voz, com Automática e botão Ouvir;
- chattiness;
- preset low latency, balanced ou quality.

Quando Cascata local estiver selecionada, a seção mostra Parakeet v3, GPT-OSS
20B/120B, reasoning effort, device e voz XTTS. Câmera e tela ficam desabilitadas
com a mensagem “Visão ainda não suportada nesta pipeline”; microfone e texto
continuam disponíveis. Falhas de CUDA, download, Groq ou voz mostram o estágio
exato e a ação de recuperação.

Quando a cascata estiver selecionada, mostrar `LocalResources` com cards
Parakeet e XTTS. Cada card exibe estado/fase, modelo, device, GPU, duração de
carga, memória alocada/reservada e erro recuperável. O topo apresenta um badge
compacto `Locais: não carregados/carregando/prontos/erro`. Não há botões
separados de preparar ou descarregar: Start dispara a carga e os modelos ficam
residentes até o shutdown.

Durante carga, o estado de sessão é `starting`, Start fica desabilitado e Stop
permanece habilitado. A UI não promete percentual quando o backend só conhece
fases discretas.

Se um worker local morrer ou a memória mínima não estiver disponível, a UI
mostra a sessão como `Erro`, exibe `last_error_detail` acionável e mantém Start
disponível para uma nova tentativa explícita. Não exibe `Falando` indefinidamente
nem reinicia em loop silencioso.

Quando diarização estiver instalada, a UI exibirá seu estado (`indisponível`,
`carregando`, `pronta` ou `erro`), device e memória estimada. A ativação será
independente do botão de microfone; enquanto estiver indisponível, a
transcrição e o playback continuam normalmente.
No painel da cascata, o checkbox “Ativar diarização opcional” só fica habilitado
quando a capability anuncia a dependência instalada; alterar o checkbox é uma
mudança de configuração que exige Apply/Start e nunca altera Gemini.

Quando `codex_realtime` estiver selecionado, a UI mostra o badge “Codex
experimental”, o modelo `gpt-realtime-1.5`, a versão realtime negociada e as
vozes anunciadas pelo capability document. No transporte WebRTC v1, deve
priorizar as vozes compatíveis (`juniper`, `maple`, `spruce`, `ember`, `vale`,
`breeze`, `arbor`, `sol`, `cove`) e enviar a oferta SDP somente pelo WebSocket
de sinalização local; o microfone não deve ser duplicado como PCM. Erros de
`auth.json`, API key
ausente, feature desabilitada ou versão não suportada são acionáveis. A UI
nunca mostra o conteúdo de `auth.json` nem oferece campo de credencial.

Quando `codex_text` estiver selecionado, a UI mostra “Codex Text”, não oferece
voz nem controles de áudio e deixa explícito que é o fallback textual do
app-server. A UI nunca troca automaticamente entre `codex_realtime` e
`codex_text`; a escolha é do usuário e o erro de autenticação do realtime deve
ser acionável.

O erro de runtime XTTS deve distinguir ambiente ausente, referência de voz
ausente e termos CPML ainda não aceitos. A UI nunca oferece um botão que aceite
licença automaticamente; ela mostra o comando de preparação documentado.

Objetivo:

- textarea livre com contador 12.000;
- texto explicando que ferramentas/instruções internas são protegidas;
- reset apenas para o objetivo default.

Avançada:

- controles derivados de `/capabilities`;
- campos incompatíveis ficam ausentes, não apenas desabilitados;
- VAD, captura, resolução, thinking, temperatura e contexto;
- reset da seção para o preset atual.

O topo mostra “Ativa” e “Rascunho com N alterações”. Erros de validação ficam
junto ao campo e no resumo acessível.

### MetricsPanel

- cards TTFA atual, p50, p95 e duração;
- startup, interruption flush, frames e chunks;
- candidatos VAD rejeitados, utterances aceitas, interrupções de turno e
  cancelamentos do TTS;
- sparklines limitadas às últimas 100 amostras;
- `—` em vez de zero quando não há medição.

### LogPanel

- tabs Live e Arquivos;
- nível, logger, texto, autoscroll e Pausar;
- buffer visual máximo de 2.000 linhas;
- seleção de arquivo e paginação por cursor;
- timestamps locais e opção de copiar somente linhas selecionadas;
- sem excluir, editar ou escolher caminhos locais.
- eventos SSE entram em buffer e são renderizados em lote, nunca uma
  reconstrução de 2.000 linhas por evento;
- polling de métricas/recursos não aparece no tail INFO e não pode criar
  requisições sobrepostas;
- aba oculta reduz polling; busca é debounceada e Pausar não acumula linhas.

### VoicePreview

- confirmação “usa uma chamada real ao modelo” na primeira execução;
- loading cancelável e timeout visível;
- resposta WAV reproduzida em player separado;
- não mistura áudio com o `PcmPlayer` da sessão.

## 5. Design system

- tema escuro neutro com verde/âmbar como acentos, sem replicar AI Studio;
- fonte de sistema para UI e monoespaçada para logs/métricas;
- espaçamento base 4 px; raios 8/12/16 px;
- foco de 2 px sempre visível;
- estados não dependem somente de cor;
- animações abaixo de 180 ms e removidas com `prefers-reduced-motion`.

## 6. Comunicação

O cliente REST possui timeout, abort e parsing de erro comum. O WebSocket usa
backoff 1, 2, 4, 8 e 15 segundos com jitter; após conexão, não inicia sessão
automaticamente. O backoff só volta a 1 segundo depois de receber um snapshot
de estado válido. Um handshake encerrado porque outra aba possui a mídia não
cria reconnect loop: a UI informa a contenção e mantém tentativas limitadas.

O cliente valida forma e tamanho antes de enviar, mas o backend permanece a
autoridade. Mensagens desconhecidas são ignoradas com evento de diagnóstico,
nunca lançadas na raiz do app.

## 7. Acessibilidade e erros

- `aria-live=polite` para estado e `assertive` apenas para falhas críticas;
- labels reais para todos os inputs;
- dialogs prendem foco e restauram ao fechar;
- logs e histórico não roubam foco durante autoscroll;
- mensagens informam causa, impacto e ação: permissão, dispositivo, provider,
  configuração, timeout, desconexão ou conflito de revisão.

## 8. Critérios de aceitação

- Todo estado definido pode ser reproduzido por teste sem API real.
- O usuário consegue configurar, aplicar, iniciar, interromper e parar somente
  com teclado.
- A UI não envia mídia durante sessão parada.
- Configuração incompatível nunca é apresentada como aplicada.
- Tail pausado não cresce indefinidamente.
- O build Vite não contém chave, token ou prompt protegido.
- Um fluxo de 100 linhas/s não trava controles nem excede 2.000 linhas.
- A cascata mostra cada componente local antes de declarar sessão running.
- Selecionar/iniciar Gemini não carrega recursos locais nem altera seus
  controles ou lifecycle.
