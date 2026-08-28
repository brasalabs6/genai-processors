# Leônidas — análise do rascunho e direção de implementação

## Resultado

O rascunho visual tem uma identidade forte e aproveitável: cockpit escuro, tipografia condensada, bordas técnicas e acento amarelo-lima. O problema principal não é estético; é de alinhamento de produto. A tela ainda representa “Live Commentator” e inclui áreas que não existem no Leônidas atual, enquanto reduz a importância de recursos que já são centrais: configuração transacional, capabilities, recursos locais Parakeet/XTTS, estados de sessão e métricas reais.

A especificação v2 transforma o rascunho em uma interface do **Leônidas** e separa claramente três camadas:

1. **WebUI desktop**, implementável agora sem mudar contratos do backend.
2. **WebUI responsiva/mobile**, implementável em Vite e testável com mocks.
3. **Integrações Capacitor nativas**, necessárias para assistente global, botões físicos, captura da tela do sistema e execução em segundo plano.

## Estado atual observado

A WebUI atual já é Vite + TypeScript sem React. O HTML é monolítico, a classe `LeonidasApp` concentra conexão, sessão, captura, configuração, métricas, recursos e logs, e o CSS já possui dois breakpoints simples. Isso permite um redesenho inicial com baixo risco: preservar os IDs e listeners existentes, reorganizar o DOM e substituir integralmente os estilos.

A aplicação real possui:

- REST e WebSocket separados;
- sessão explícita `stopped/starting/running/stopping/error`;
- microfone, câmera e tela;
- conversa e input textual;
- configuração ativa/draft/revision;
- Gemini Live e cascata local;
- readiness de Parakeet e XTTS;
- métricas TTFA/VAD/chunks;
- logs SSE e arquivos.

O rascunho, por outro lado, mostra terminal, notificações, extensões, analytics, quick actions e sessões persistentes. Esses itens devem ser removidos ou tratados como slots futuros invisíveis.

## Nova arquitetura desktop

A navegação deve ter apenas três destinos reais: **Operação**, **Configuração** e **Diagnóstico**.

A tela Operação mantém a força visual do rascunho:

- coluna esquerda: percepção 16:9, controles de dispositivos e métricas em tempo real;
- coluna direita: conversa ocupando toda a altura;
- header sticky: REST, WebSocket, sessão, estado do agente, pipeline/modelo, Start, Stop e Apply;
- footer técnico apenas em telas largas.

A configuração sai do rodapé apertado e ganha uma tela própria. Isso é essencial porque o Leônidas possui configuração transacional, campos derivados de capabilities e recursos locais com estados de carga. Logs e métricas detalhadas passam para Diagnóstico.

## Nova arquitetura mobile

No celular, a interface deixa de ser um dashboard reduzido. Ela vira um controle de campo com quatro áreas:

- **Conversa**: tela inicial, mensagens, estado do agente, composer e mic.
- **Percepção**: preview, câmera/tela, permissões e telemetria visual.
- **Sessão**: Start/Stop, conexão, pipeline e recursos locais.
- **Ajustes**: configuração, draft, Apply e diagnóstico.

Quando uma fonte visual estiver ativa, o preview pode ficar em PiP sobre a conversa. Configurações avançadas e logs usam telas próprias, não accordions intermináveis.

## Overlay rápido e botão físico

A experiência proposta chama-se **Leônidas Quick Converse**: uma camada nativa compacta com estado, waveform/transcrição curta e duas ações principais — “Conversar agora” e “Compartilhar tela”.

No Android, a rota correta é tornar o Leônidas elegível ao papel de assistente e implementar `VoiceInteractionService`. O app não deve tentar interceptar diretamente o botão de energia. O acionamento por pressão longa depende de o usuário selecionar o Leônidas como assistente e da implementação do fabricante. O compartilhamento usa `MediaProjection`, consentimento do sistema e foreground service.

No iPhone, não existe uma substituição universal do botão lateral para apps comuns. A experiência equivalente deve usar App Intents/App Shortcuts, Action Button em aparelhos compatíveis, Control Center, Lock Screen e Siri. A captura deve usar a API nativa de screen sharing suportada pelo deployment target, sempre com seleção/permissão do sistema.

## Restrição estrutural do mobile

O backend atual escuta apenas em `127.0.0.1`. Em um telefone físico, `127.0.0.1` é o próprio telefone, não o computador. Portanto, empacotar a WebUI no Capacitor não cria automaticamente um cliente móvel funcional.

A recomendação é:

- desenhar e implementar agora a UI mobile com um `TransportAdapter`;
- validar o shell Capacitor;
- depois criar uma fase separada de pareamento, autenticação e transporte criptografado entre telefone e host desktop.

Até essa fase existir, o mobile real deve ser tratado como protótipo de interface ou executar apenas contra mocks/emulador.

## Estratégia de implementação

A primeira entrega pode modificar apenas `index.html` e os estilos, preservando os IDs atuais. Em seguida, a classe monolítica pode ser dividida por renderizadores, ainda sem adotar framework. A integração Capacitor vem depois, com plugins nativos separados para invocação e captura.

O arquivo JSON anexo contém tokens, layouts desktop/mobile, estados, arquitetura nativa, compatibilidade de IDs, critérios de aceitação e fases de rollout.
