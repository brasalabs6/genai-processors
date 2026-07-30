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
