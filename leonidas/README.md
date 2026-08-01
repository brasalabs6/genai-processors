# Leonidas

Leonidas é o agente conversacional local derivado do Live Commentator. Consulte
`SPECS.md`, `WORKFLOW.md` e `UI_SPECS.md` antes de alterar seus contratos.

## Desenvolvimento

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,contrib]'
cd leonidas/webui
npm ci
npm run build
cd ../..
GOOGLE_API_KEY='...' .venv/bin/python -m leonidas
```

A UI é servida em `http://127.0.0.1:8000` e o WebSocket em
`ws://127.0.0.1:8765/api/v1/live`.

Nunca grave a chave em arquivos do repositório. O diretório `.runtime` contém
somente configuração local não sensível e é ignorado pelo Git.

## Teste empírico dos modelos Gemini

```bash
# Tenta imagem Gemini; use --synthetic-image somente quando a quota de imagem
# estiver indisponível. O áudio sempre é gerado pelo Gemini TTS.
.venv/bin/python -m leonidas.e2e.generate_assets --synthetic-image
.venv/bin/python -m leonidas.e2e.run --models all
```

Assets e relatórios ficam em `leonidas/.runtime/e2e` e não devem ser
versionados. O comando retorna falha se qualquer profile não entregar áudio
válido dentro dos thresholds documentados.

## Pipeline Parakeet + Groq + XTTS

O processo principal usa Transformers 5 para o Parakeet. XTTS fica em
`.venv-xtts` porque Coqui TTS 0.27.5 requer Transformers 4.57.6. Instale os
dois ambientes sem adicionar CUDA à dependência base:

```bash
.venv/bin/python -m pip install -e '.[dev,contrib,cascade]'
./leonidas/cascade/install_xtts.sh
.venv/bin/python -m leonidas.cascade.prepare_voice
```

XTTS v2 usa CPML e o downloader exige que uma pessoa confirme se possui licença
comercial ou aceita os termos não comerciais. Revise e responda ao prompt uma
vez; o agente não aceita termos automaticamente:

```bash
.venv-xtts/bin/python -m TTS.bin.synthesize \
  --model_name tts_models/multilingual/multi-dataset/xtts_v2 \
  --text 'Teste de voz do Leonidas.' \
  --speaker_wav leonidas/.runtime/voices/leonidas.wav \
  --language_idx pt \
  --use_cuda \
  --out_path /tmp/leonidas-xtts-test.wav
```

Depois do download/aceite, valide a composição real:

```bash
GROQ_API_KEY='...' .venv/bin/python -m leonidas.e2e.cascade_smoke --device cuda
GOOGLE_API_KEY='...' GROQ_API_KEY='...' .venv/bin/python -m leonidas
```

O primeiro smoke baixa o Parakeet para o cache Hugging Face. A referência de
voz, pesos, mídia e resultados permanecem fora do Git.

### Diarização opcional

A diarização roda em um terceiro runtime isolado para não substituir o Torch
validado do Parakeet. Instale-o somente quando essa capacidade for necessária:

```bash
./leonidas/cascade/install_diarization.sh auto
```

O script usa `torch==2.6.0`, `torchaudio==2.6.0` e
`pyannote.audio==3.4.0` em `.venv-diarization`; `cpu` e `cuda` também podem
ser passados explicitamente. O modelo
`pyannote/speaker-diarization-community-1` requer acesso Hugging Face e seus
termos próprios. Configure o login no ambiente do usuário, sem colocar token
no repositório, e valide sem substituir o resultado do STT:

```bash
LEONIDAS_RUN_DIARIZATION_E2E=1 \
  .venv/bin/python -m leonidas.e2e.diarization_smoke
```

Sem runtime, pesos ou acesso ao modelo, a API expõe `diarization` como
`unavailable` e a cascata Parakeet → Groq → XTTS continua funcionando com a
diarização desativada. A UI exibe o comando de instalação e não habilita o
checkbox automaticamente.
