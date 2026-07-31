import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

from leonidas.cascade import parakeet_process
from leonidas.cascade import transcript_filter
from leonidas.cascade import xtts_process


class TranscriptFilterTest(unittest.TestCase):

  def test_rejects_evidenced_short_english_hallucinations(self):
    for value in ('Yeah.', 'you', 'Me', 'Mm.', 'okay'):
      with self.subTest(value=value):
        self.assertTrue(
            transcript_filter.is_probable_short_artifact(
                value, audio_duration_seconds=0.7, language='pt'
            )
        )

  def test_preserves_portuguese_acknowledgements_and_longer_speech(self):
    for value in ('sim', 'não', 'aham', 'claro'):
      with self.subTest(value=value):
        self.assertFalse(
            transcript_filter.is_probable_short_artifact(
                value, audio_duration_seconds=0.5, language='pt'
            )
        )
    self.assertFalse(
        transcript_filter.is_probable_short_artifact(
            'Yeah, eu entendi a pergunta.',
            audio_duration_seconds=1.8,
            language='pt',
        )
    )


class WorkerRecoveryTest(unittest.IsolatedAsyncioTestCase):

  async def test_xtts_timeout_restarts_worker_and_next_request_succeeds(self):
    worker_source = """
import base64
import json
from pathlib import Path
import sys
import time
marker = Path('attempt.txt')
for line in sys.stdin:
  request = json.loads(line)
  count = int(marker.read_text() if marker.exists() else '0') + 1
  marker.write_text(str(count))
  if count == 1:
    time.sleep(5)
  print(json.dumps({'id': request['id'], 'audio': base64.b64encode(b'pcm').decode()}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'recovering_xtts.py').write_text(worker_source, encoding='utf-8')
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      agreement = (
          root
          / 'tts'
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('accepted', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=root / 'tts',
          worker_module='recovering_xtts',
          worker_cwd=root,
          timeout=0.05,
      )
      with self.assertRaises(TimeoutError):
        await adapter.synthesize('primeira', voice_id='leonidas', language='pt')
      pcm = await adapter.synthesize(
          'segunda', voice_id='leonidas', language='pt'
      )
      await adapter.close()
    self.assertEqual(pcm, b'pcm')

  async def test_parakeet_timeout_restarts_worker_and_next_request_succeeds(self):
    worker_source = """
import json
from pathlib import Path
import sys
import time
marker = Path('attempt.txt')
for line in sys.stdin:
  request = json.loads(line)
  count = int(marker.read_text() if marker.exists() else '0') + 1
  marker.write_text(str(count))
  if count == 1:
    time.sleep(5)
  print(json.dumps({'id': request['id'], 'text': 'fala recuperada'}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'recovering_parakeet.py').write_text(
          worker_source, encoding='utf-8'
      )
      adapter = parakeet_process.ParakeetWorkerTranscriber(
          device='cpu',
          python=Path(sys.executable),
          worker_module='recovering_parakeet',
          worker_cwd=root,
          timeout=0.05,
      )
      with self.assertRaises(TimeoutError):
        await adapter.transcribe(b'first')
      transcript = await adapter.transcribe(b'second')
      await adapter.close()
    self.assertEqual(transcript, 'fala recuperada')


if __name__ == '__main__':
  unittest.main()
