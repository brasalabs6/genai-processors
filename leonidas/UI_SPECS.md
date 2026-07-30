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

- pipeline (read-only nesta versão);
- modelo;
- voz, com Automática e botão Ouvir;
- chattiness;
- preset low latency, balanced ou quality.

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
- sparklines limitadas às últimas 100 amostras;
- `—` em vez de zero quando não há medição.

### LogPanel

- tabs Live e Arquivos;
- nível, logger, texto, autoscroll e Pausar;
- buffer visual máximo de 2.000 linhas;
- seleção de arquivo e paginação por cursor;
- timestamps locais e opção de copiar somente linhas selecionadas;
- sem excluir, editar ou escolher caminhos locais.

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
automaticamente.

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
