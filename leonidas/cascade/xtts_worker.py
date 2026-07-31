"""Private JSON-lines XTTS worker executed by the isolated runtime."""

import base64
import contextlib
import json
import sys
from typing import Any


def _respond(value: dict[str, Any]) -> None:
  sys.stdout.write(json.dumps(value, ensure_ascii=True) + '\n')
  sys.stdout.flush()


def _runtime_details(device: str) -> dict[str, Any]:
  details: dict[str, Any] = {'device': device}
  try:
    import torch

    if device.startswith('cuda') and torch.cuda.is_available():
      index = torch.cuda.current_device()
      details.update(
          {
              'gpu_name': torch.cuda.get_device_name(index),
              'memory_allocated_mib': round(
                  torch.cuda.memory_allocated(index) / 1024 / 1024
              ),
              'memory_reserved_mib': round(
                  torch.cuda.memory_reserved(index) / 1024 / 1024
              ),
          }
      )
  except (ImportError, RuntimeError):
    pass
  return details


def main() -> int:
  engine = None
  model_id = None
  device = None
  for line in sys.stdin:
    request_id = None
    try:
      request = json.loads(line)
      request_id = request['id']
      operation = request.get('op', 'synthesize')
      requested_model = request['model_id']
      requested_device = request['device']
      if engine is None:
        _respond(
            {
                'type': 'event',
                'id': request_id,
                'phase': 'loading_weights',
            }
        )
        with contextlib.redirect_stdout(sys.stderr):
          from TTS.api import TTS

          engine = TTS(model_name=requested_model, progress_bar=False).to(
              requested_device
          )
        model_id = requested_model
        device = requested_device
      elif (model_id, device) != (requested_model, requested_device):
        raise ValueError('XTTS worker model/device cannot change in place')
      if operation == 'load':
        _respond({'type': 'event', 'id': request_id, 'phase': 'warming'})
        with contextlib.redirect_stdout(sys.stderr):
          engine.tts(
              text='Pronto.',
              speaker_wav=request['speaker_wav'],
              language=request['language'],
          )
        _respond(
            {
                'type': 'result',
                'id': request_id,
                **_runtime_details(device),
            }
        )
        continue
      if operation != 'synthesize':
        raise ValueError(f'Unsupported XTTS operation: {operation!r}')
      with contextlib.redirect_stdout(sys.stderr):
        waveform = engine.tts(
            text=request['text'],
            speaker_wav=request['speaker_wav'],
            language=request['language'],
        )
      import numpy as np

      samples = np.clip(np.asarray(waveform, dtype=np.float32), -1.0, 1.0)
      pcm = (samples * 32767).astype('<i2').tobytes()
      _respond(
          {
              'type': 'result',
              'id': request_id,
              'audio': base64.b64encode(pcm).decode('ascii'),
          }
      )
    except Exception as exc:  # Worker boundary must serialize all failures.
      _respond(
          {
              'type': 'result',
              'id': request_id,
              'error': type(exc).__name__,
              'message': 'XTTS synthesis failed',
          }
      )
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
