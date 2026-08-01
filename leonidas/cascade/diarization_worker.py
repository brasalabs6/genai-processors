"""JSONL worker for optional Pyannote diarization dependencies."""

from __future__ import annotations

import base64
import json
import sys
from typing import Any


def _write(value: dict[str, Any]) -> None:
  print(json.dumps(value, ensure_ascii=True), flush=True)


def _require_pipeline(pipeline: Any) -> Any:
  if pipeline is None:
    raise RuntimeError(
        'diarization model is unavailable or access is not authorized'
    )
  return pipeline


def main() -> int:
  pipeline = None
  for line in sys.stdin:
    request = json.loads(line)
    request_id = request.get('id')
    try:
      if request.get('op') == 'load':
        from pyannote.audio import Pipeline
        import torch

        _write({'id': request_id, 'type': 'event', 'phase': 'loading_weights'})
        pipeline = _require_pipeline(
            Pipeline.from_pretrained(request['model_id'])
        )
        device = request.get('device', 'auto')
        if device == 'auto':
          device = 'cuda' if torch.cuda.is_available() else 'cpu'
        pipeline.to(torch.device(device))
        details: dict[str, Any] = {
            'device': device,
            'model_id': request['model_id'],
        }
        if device == 'cuda':
          details.update(
              {
                  'gpu_name': torch.cuda.get_device_name(),
                  'memory_allocated_mib': round(
                      torch.cuda.memory_allocated() / 1024**2, 1
                  ),
                  'memory_reserved_mib': round(
                      torch.cuda.memory_reserved() / 1024**2, 1
                  ),
              }
          )
        _write({'id': request_id, 'type': 'event', 'phase': 'warming'})
        _write({'id': request_id, **details})
      elif request.get('op') == 'diarize':
        if pipeline is None:
          raise RuntimeError('worker is not loaded')
        import torch

        audio = base64.b64decode(request['audio'], validate=True)
        waveform = torch.frombuffer(audio, dtype=torch.int16).clone().float()
        waveform = (waveform / 32768.0).reshape(1, -1)
        annotation = pipeline(
            {'waveform': waveform, 'sample_rate': int(request['sample_rate'])}
        )
        segments = []
        for turn, _track, speaker in annotation.itertracks(yield_label=True):
          segments.append(
              {
                  'speaker_id': str(speaker),
                  'start': float(turn.start),
                  'end': float(turn.end),
                  'confidence': None,
              }
          )
        _write({'id': request_id, 'segments': segments})
      else:
        raise ValueError('unsupported operation')
    except Exception as exc:
      _write(
          {
              'id': request_id,
              'error': type(exc).__name__,
              'message': str(exc)[:500],
          }
      )
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
