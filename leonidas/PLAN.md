# Plano de execução — Leonidas

Versão: 20260730-0031

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
7. **Commit e tag do milestone — em andamento**
   - commit atômico sem `.agents/` ou artefatos privados;
   - tag anotada `leonidas-v0.1.0`.
8. **Specs da pipeline cascata — pendente**
   - atualizar SPECS/WORKFLOW/UI_SPECS primeiro;
   - capabilities, contratos de áudio, processos, CUDA/VRAM e falhas.
9. **Parakeet v3 + Groq reasoning + XTTS v2 — pendente**
   - adapters tests-first e composição turn-based/realtime;
   - seleção pela UI, métricas e logs;
   - testes offline de contrato e smokes reais de cada estágio e do conjunto.
10. **Auditoria final ampliada — pendente**
    - validar Gemini e cascata, CPU/device errors, CUDA, downloads, cancelamento,
      segurança e documentação; commit final coerente.

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
