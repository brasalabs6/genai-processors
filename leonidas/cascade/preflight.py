"""Redacted environment preflight for the Leonidas cascade."""

import os
from pathlib import Path
import subprocess

import torch

from leonidas.cascade import prepare_voice


def main() -> int:
  repository = Path(__file__).resolve().parents[2]
  xtts_python = repository / '.venv-xtts' / 'bin' / 'python'
  voice = prepare_voice.DEFAULT_OUTPUT
  agreement = (
      Path(os.environ.get('TTS_HOME', Path.home() / '.local/share/tts'))
      / 'tts_models--multilingual--multi-dataset--xtts_v2'
      / 'tos_agreed.txt'
  )
  checks = {
      'groq_key': bool(os.environ.get('GROQ_API_KEY')),
      'cuda': torch.cuda.is_available(),
      'xtts_runtime': xtts_python.is_file(),
      'voice_reference': voice.is_file(),
      'xtts_license_agreement': agreement.is_file(),
  }
  if checks['cuda']:
    properties = torch.cuda.get_device_properties(0)
    print(
        f'gpu={properties.name!r} '
        f'vram_gib={properties.total_memory / 2**30:.2f} '
        f'torch={torch.__version__}'
    )
  if checks['xtts_runtime']:
    result = subprocess.run(
        [
            str(xtts_python),
            '-c',
            'import transformers; from TTS.api import TTS; '
            'print(transformers.__version__)',
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    checks['xtts_import'] = result.returncode == 0
    if result.returncode == 0:
      print(f'xtts_transformers={result.stdout.strip()!r}')
  for name, passed in checks.items():
    print(f'{name}={"ok" if passed else "missing"}')
  return 0 if all(checks.values()) else 2


if __name__ == '__main__':
  raise SystemExit(main())
