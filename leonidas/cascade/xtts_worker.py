"""Private JSON-lines XTTS worker executed by the isolated runtime."""

import base64
import contextlib
import json
import sys
from typing import Any


def _respond(value: dict[str, Any]) -> None:
  sys.stdout.write(json.dumps(value, ensure_ascii=True) + '\n')
  sys.stdout.flush()


def main() -> int:
  engine = None
  model_id = None
  device = None
  for line in sys.stdin:
    request_id = None
    try:
      request = json.loads(line)
      request_id = request['id']
      requested_model = request['model_id']
      requested_device = request['device']
      if engine is None:
        with contextlib.redirect_stdout(sys.stderr):
          from TTS.api import TTS

          engine = TTS(model_name=requested_model, progress_bar=False).to(
              requested_device
          )
        model_id = requested_model
        device = requested_device
      elif (model_id, device) != (requested_model, requested_device):
        raise ValueError('XTTS worker model/device cannot change in place')
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
              'id': request_id,
              'audio': base64.b64encode(pcm).decode('ascii'),
          }
      )
    except Exception as exc:  # Worker boundary must serialize all failures.
      _respond(
          {
              'id': request_id,
              'error': type(exc).__name__,
              'message': 'XTTS synthesis failed',
          }
      )
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
