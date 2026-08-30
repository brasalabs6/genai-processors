import sys
from pathlib import Path
import tempfile
import unittest

from leonidas.cascade import diarization_process


class DiarizationWorkerTest(unittest.IsolatedAsyncioTestCase):

  async def test_worker_load_and_diarize_contract(self):
    worker_source = """
import json
import sys
for line in sys.stdin:
  request = json.loads(line)
  if request['op'] == 'load':
    print(json.dumps({'id': request['id'], 'type': 'event', 'phase': 'warming'}), flush=True)
    print(json.dumps({'id': request['id'], 'device': 'cpu', 'model_id': request['model_id']}), flush=True)
  elif request['op'] == 'diarize':
    print(json.dumps({'id': request['id'], 'segments': [
      {'speaker_id': 'SPEAKER_00', 'start': 0.0, 'end': 0.5, 'confidence': 0.9},
      {'speaker_id': 'SPEAKER_01', 'start': 0.5, 'end': 1.0, 'confidence': 0.8},
    ]}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'fake_diarization_worker.py').write_text(
          worker_source, encoding='utf-8'
      )
      adapter = diarization_process.PyannoteWorkerDiarizer(
          python=Path(sys.executable),
          worker_module='fake_diarization_worker',
          worker_cwd=root,
          device='cpu',
      )
      phases = []

      async def progress(phase):
        phases.append(phase)

      details = await adapter.load(progress=progress)
      segments = await adapter.diarize(b'\x00\x00' * 16000, sample_rate=16000)
      await adapter.close()

    self.assertEqual(phases, ['warming'])
    self.assertEqual(details['device'], 'cpu')
    self.assertEqual(
        [item.speaker_id for item in segments],
        [
            'SPEAKER_00',
            'SPEAKER_01',
        ],
    )
    self.assertEqual(segments[1].start, 0.5)

  async def test_missing_runtime_fails_before_spawn(self):
    adapter = diarization_process.PyannoteWorkerDiarizer(
        python=Path('/tmp/leonidas-missing-diarization-python')
    )
    with self.assertRaisesRegex(
        diarization_process.DiarizationWorkerError, 'runtime is missing'
    ):
      await adapter.load()


if __name__ == '__main__':
  unittest.main()
