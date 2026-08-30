"""Redacted environment preflight for the Leonidas cascade."""

import argparse
import os
from pathlib import Path
import subprocess
from typing import Any

from leonidas.cascade import prepare_voice
from leonidas.cascade import xtts_process


def _arguments() -> argparse.Namespace:
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--device', choices=('auto', 'cpu', 'cuda'), default='auto'
  )
  return parser.parse_args()


def _load_torch() -> tuple[Any | None, str | None]:
  try:
    import torch  # pylint: disable=g-import-not-at-top

    return torch, None
  except (ImportError, OSError) as exc:
    return None, type(exc).__name__


def main() -> int:
  args = _arguments()
  repository = Path(__file__).resolve().parents[2]
  xtts_python = repository / '.venv-xtts' / 'bin' / 'python'
  voice = prepare_voice.DEFAULT_OUTPUT
  agreement = (
      Path(os.environ.get('TTS_HOME', Path.home() / '.local/share/tts'))
      / 'tts_models--multilingual--multi-dataset--xtts_v2'
      / 'tos_agreed.txt'
  )
  torch, torch_error = _load_torch()
  cuda_available = bool(torch is not None and torch.cuda.is_available())
  resolved_device = (
      'cuda' if args.device == 'auto' and cuda_available else args.device
  )
  if resolved_device == 'auto':
    resolved_device = 'cpu'
  device_ready = bool(
      torch is not None and (resolved_device == 'cpu' or cuda_available)
  )
  checks = {
      'groq_key': bool(os.environ.get('GROQ_API_KEY')),
      'torch_runtime': torch is not None,
      'requested_device': device_ready,
      'xtts_runtime': xtts_python.is_file(),
      'voice_reference': voice.is_file(),
      'xtts_license_agreement': agreement.is_file(),
  }
  available_memory = xtts_process.XttsWorkerSynthesizer._available_memory_mib()
  minimum_memory = xtts_process.DEFAULT_MIN_AVAILABLE_MEMORY_MIB
  if available_memory is not None:
    print(
        f'memory_available_mib={available_memory} '
        f'memory_required_mib={minimum_memory}'
    )
    checks['system_memory'] = available_memory >= minimum_memory
  print(f'requested_device={args.device!r} resolved_device={resolved_device!r}')
  if torch_error is not None:
    print(f'torch_error_type={torch_error!r}')
  if cuda_available and torch is not None:
    properties = torch.cuda.get_device_properties(0)
    print(
        f'gpu={properties.name!r} '
        f'vram_gib={properties.total_memory / 2**30:.2f} '
        f'torch={torch.__version__}'
    )
  elif torch is not None:
    print(f'cpu_runtime=ok torch={torch.__version__!r}')
  if checks['xtts_runtime']:
    try:
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
      else:
        print('xtts_import_error=nonzero_exit')
    except subprocess.TimeoutExpired:
      checks['xtts_import'] = False
      print('xtts_import_error=timeout')
    except OSError as exc:
      checks['xtts_import'] = False
      print(f'xtts_import_error={type(exc).__name__!r}')
  for name, passed in checks.items():
    print(f'{name}={"ok" if passed else "missing"}')
  return 0 if all(checks.values()) else 2


if __name__ == '__main__':
  raise SystemExit(main())
