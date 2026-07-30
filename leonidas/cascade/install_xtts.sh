#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime="${repository_root}/.venv-xtts"
python3 -m venv "${runtime}"
"${runtime}/bin/python" -m pip install --upgrade pip
"${runtime}/bin/python" -m pip install \
  'torch==2.6.0' 'torchaudio==2.6.0' \
  --index-url https://download.pytorch.org/whl/cu124
"${runtime}/bin/python" -m pip install \
  'coqui-tts==0.27.5' 'transformers==4.57.6'
"${runtime}/bin/python" -c \
  'from TTS.api import TTS; import torch; print("XTTS runtime OK, CUDA:", torch.cuda.is_available())'

echo "Runtime criado em ${runtime}"
echo "Os termos CPML do modelo ainda precisam ser aceitos explicitamente no primeiro download."
