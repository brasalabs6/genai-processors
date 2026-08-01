#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime="${repository_root}/.venv-diarization"
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

if [[ ! -x "${runtime}/bin/python" ]]; then
  python3 -m venv "${runtime}"
fi

"${runtime}/bin/python" -m pip install --upgrade pip
# Keep Torch isolated from the Parakeet/Transformers 5 environment. Pyannote
# 3.4 accepts Torch 2.6 and does not force a second CUDA stack in the venv.
"${runtime}/bin/python" -m pip install \
  'torch==2.6.0' 'torchaudio==2.6.0' \
  --index-url "${torch_index}"
"${runtime}/bin/python" -m pip install 'pyannote.audio==3.4.0'
"${runtime}/bin/python" -m pip check
"${runtime}/bin/python" -c \
  'from pyannote.audio import Pipeline; import torch; print("Diarization runtime OK, CUDA:", torch.cuda.is_available())'

echo "Runtime criado em ${runtime} (canal Torch: ${torch_channel})"
echo "O modelo Hugging Face ainda exige login/aceite de acesso no host."
echo "Depois, execute:"
echo "  LEONIDAS_RUN_DIARIZATION_E2E=1 ${repository_root}/.venv/bin/python -m leonidas.e2e.diarization_smoke"
