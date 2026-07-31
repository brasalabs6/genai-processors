"""Private JSON-lines worker for Parakeet v3."""

import base64
import contextlib
import json
import sys
from typing import Any


def _respond(value: dict[str, Any]) -> None:
  sys.stdout.write(json.dumps(value, ensure_ascii=True) + '\n')
  sys.stdout.flush()


def _memory_details(device: str) -> dict[str, Any]:
  if device != 'cuda':
    return {
        'device': device,
        'gpu_name': None,
        'memory_allocated_mib': None,
        'memory_reserved_mib': None,
    }
  import torch

  return {
      'device': device,
      'gpu_name': torch.cuda.get_device_name(0),
      'memory_allocated_mib': round(torch.cuda.memory_allocated() / 1048576, 1),
      'memory_reserved_mib': round(torch.cuda.memory_reserved() / 1048576, 1),
  }


def main() -> int:
  adapter = None
  model_id = None
  device = None
  for line in sys.stdin:
    request_id = None
    try:
      request = json.loads(line)
      request_id = request['id']
      requested_model = request['model_id']
      requested_device = request['device']
      if adapter is None:
        _respond(
            {'type': 'event', 'id': request_id, 'phase': 'loading_weights'}
        )
        with contextlib.redirect_stdout(sys.stderr):
          from leonidas.cascade import parakeet

          adapter = parakeet.ParakeetTranscriber(
              model_id=requested_model, device=requested_device
          )
          adapter._load()  # Worker owns the adapter's synchronous boundary.
        model_id = requested_model
        device = requested_device
      elif (model_id, device) != (requested_model, requested_device):
        raise ValueError('Parakeet worker model/device cannot change in place')
      if request['op'] == 'load':
        _respond({'type': 'event', 'id': request_id, 'phase': 'warming'})
        with contextlib.redirect_stdout(sys.stderr):
          adapter._transcribe(b'\x00\x00' * 16000)
        _respond(
            {'type': 'result', 'id': request_id, **_memory_details(device)}
        )
      elif request['op'] == 'transcribe':
        audio = base64.b64decode(request['audio'], validate=True)
        with contextlib.redirect_stdout(sys.stderr):
          text = adapter._transcribe(audio)
        _respond({'type': 'result', 'id': request_id, 'text': text})
      else:
        raise ValueError('Unknown Parakeet worker operation')
    except Exception as exc:
      _respond(
          {
              'type': 'result',
              'id': request_id,
              'error': type(exc).__name__,
              'message': 'Parakeet operation failed',
          }
      )
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
