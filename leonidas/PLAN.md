# Plano de execução — Leonidas

Versão: 20260730-0038

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
subprocesso persistente, com protocolo local privado, enquanto o processo
principal mantém Transformers 5 para Parakeet. Não usar monkey patch nem
rebaixar o Parakeet. O worker XTTS é encerrado com a aplicação e cache/pesos
continuam fora do Git.
10. **Auditoria final ampliada — concluído**
    - validar Gemini e cascata, CPU/device errors, CUDA, downloads, cancelamento,
      segurança e documentação; commit final coerente.
    - validações offline/live, memória simultânea e cleanup: aprovados;
    - stage revisado exclui artefatos privados e arquivos não relacionados;
      checkpoint final será o commit e a tag anotada `leonidas-v0.2.0`.

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
