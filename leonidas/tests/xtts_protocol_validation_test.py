import base64
from pathlib import Path
import sys
import tempfile
import unittest

from leonidas.cascade import xtts_process


class XttsProtocolValidationTest(unittest.IsolatedAsyncioTestCase):

  async def test_transient_worker_exit_is_retried_once(self):
    worker_source = """
import base64
import json
from pathlib import Path
import sys
marker = Path('crash-attempt.txt')
for line in sys.stdin:
  request = json.loads(line)
  count = int(marker.read_text() if marker.exists() else '0') + 1
  marker.write_text(str(count))
  if count == 1:
    raise SystemExit(1)
  print(json.dumps({'id': request['id'], 'audio': base64.b64encode(b'pcm').decode()}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'crashing_xtts.py').write_text(worker_source, encoding='utf-8')
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      tts_home = root / 'tts'
      agreement = (
          tts_home
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('accepted', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=tts_home,
          worker_module='crashing_xtts',
          worker_cwd=root,
          timeout=1,
      )

      pcm = await adapter.synthesize(
          'recuperar uma vez', voice_id='leonidas', language='pt'
      )
      await adapter.close()

    self.assertEqual(pcm, b'pcm')

  async def test_sigkill_is_reported_as_resource_error_without_retrying(self):
    worker_source = """
import json
import os
import signal
import sys
for line in sys.stdin:
  request = json.loads(line)
  os.kill(os.getpid(), signal.SIGKILL)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'killed_xtts.py').write_text(worker_source, encoding='utf-8')
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      tts_home = root / 'tts'
      agreement = (
          tts_home
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('accepted', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=tts_home,
          worker_module='killed_xtts',
          worker_cwd=root,
          timeout=1,
      )

      with self.assertRaisesRegex(
          xtts_process.XttsResourceError, 'OOM|SIGKILL'
      ):
        await adapter.synthesize(
            'não deve repetir', voice_id='leonidas', language='pt'
        )
      await adapter.close()

  async def test_invalid_base64_restarts_worker_before_next_synthesis(self):
    worker_source = """
import base64
import json
from pathlib import Path
import sys
marker = Path('audio-attempt.txt')
for line in sys.stdin:
  request = json.loads(line)
  count = int(marker.read_text() if marker.exists() else '0') + 1
  marker.write_text(str(count))
  audio = 'not-base64!' if count == 1 else base64.b64encode(b'pcm').decode()
  print(json.dumps({'id': request['id'], 'audio': audio}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'invalid_audio_xtts.py').write_text(
          worker_source, encoding='utf-8'
      )
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      tts_home = root / 'tts'
      agreement = (
          tts_home
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('accepted', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=tts_home,
          worker_module='invalid_audio_xtts',
          worker_cwd=root,
          timeout=1,
      )

      with self.assertRaises(ValueError):
        await adapter.synthesize('primeira', voice_id='leonidas', language='pt')
      pcm = await adapter.synthesize(
          'segunda', voice_id='leonidas', language='pt'
      )
      await adapter.close()

    self.assertEqual(pcm, b'pcm')
    self.assertEqual(base64.b64decode(base64.b64encode(pcm)), b'pcm')


if __name__ == '__main__':
  unittest.main()
