#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime="${repository_root}/.venv-xtts"
requested_device="${1:-auto}"

case "${requested_device}" in
  auto)
    if command -v nvidia-smi >/dev/null 2>&1; then
      torch_channel="cu124"
    else
      torch_channel="cpu"
    fi
    ;;
  cpu)
    torch_channel="cpu"
    ;;
  cuda|cu124)
    torch_channel="cu124"
    ;;
  *)
    echo "Uso: $0 [auto|cpu|cuda|cu124]" >&2
    exit 2
    ;;
esac

torch_index="${LEONIDAS_TORCH_INDEX_URL:-https://download.pytorch.org/whl/${torch_channel}}"

# Keep the isolated runtime pins synchronized with pyproject.toml. This check
# fails before modifying the environment when either source drifts.
python3 - "${repository_root}/pyproject.toml" <<'PY'
import pathlib
import sys
import tomllib

payload = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
dependencies = set(payload['project']['optional-dependencies']['xtts'])
expected = {
    'coqui-tts==0.27.5',
    'torch>=2.6.0',
    'torchaudio>=2.6.0',
    'transformers==4.57.6',
}
if dependencies != expected:
  raise SystemExit(
      'XTTS dependency pins changed in pyproject.toml; update install_xtts.sh '
      'and its compatibility validation intentionally.'
  )
PY

python3 -m venv "${runtime}"
"${runtime}/bin/python" -m pip install --upgrade pip
"${runtime}/bin/python" -m pip install \
  'torch==2.6.0' 'torchaudio==2.6.0' \
  --index-url "${torch_index}"
"${runtime}/bin/python" -m pip install \
  'coqui-tts==0.27.5' 'transformers==4.57.6'
"${runtime}/bin/python" -m pip check
"${runtime}/bin/python" -c \
  'from TTS.api import TTS; import torch; print("XTTS runtime OK, CUDA:", torch.cuda.is_available())'

echo "Runtime criado em ${runtime} (canal Torch: ${torch_channel})"
echo "Os termos CPML do modelo ainda precisam ser aceitos explicitamente no primeiro download."
