import asyncio
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import httpx
import numpy as np

from genai_processors import content_api
from leonidas import telemetry
from leonidas.cascade import diarization
from leonidas.cascade import groq_reasoning
from leonidas.cascade import parakeet
from leonidas.cascade import parakeet_process
from leonidas.cascade import pipeline
from leonidas.cascade import resources
from leonidas.cascade import vad
from leonidas.cascade import xtts
from leonidas.cascade import xtts_process


class EndpointDetectorTest(unittest.TestCase):

  @staticmethod
  def _frame(amplitude: float) -> bytes:
    samples = np.full(480, int(32767 * amplitude), dtype='<i2')
    return samples.tobytes()

  def test_hybrid_gate_rejects_digital_silence_and_constant_noise(self):
    silence_gate = vad.AdaptiveSpeechGate(is_speech=lambda _frame: True)
    noise_gate = vad.AdaptiveSpeechGate(is_speech=lambda _frame: True)

    decisions = [silence_gate.classify(self._frame(0.0)) for _ in range(30)]
    decisions += [noise_gate.classify(self._frame(0.01)) for _ in range(70)]

    self.assertFalse(any(item.speech for item in decisions))
    self.assertTrue(any(item.raw_speech for item in decisions))

  def test_hybrid_gate_preserves_short_speech_after_calibration(self):
    gate = vad.AdaptiveSpeechGate(
        is_speech=lambda frame: frame != self._frame(0)
    )
    detector = vad.EndpointDetector(speech_gate=gate)
    silence = self._frame(0)
    speech = self._frame(0.2)

    events = []
    for frame in ([silence] * 10) + ([speech] * 4) + ([silence] * 15):
      events.extend(detector.push(frame))

    self.assertIn('start', [event.kind for event in events])
    utterances = [event for event in events if event.kind == 'utterance']
    self.assertEqual(len(utterances), 1)
    self.assertGreater(len(utterances[0].audio), 0)

  def test_hybrid_gate_does_not_start_for_a_single_click(self):
    gate = vad.AdaptiveSpeechGate(
        is_speech=lambda frame: frame != self._frame(0)
    )
    detector = vad.EndpointDetector(speech_gate=gate)
    silence = self._frame(0)

    events = []
    for frame in ([silence] * 10) + [self._frame(0.8)] + ([silence] * 12):
      events.extend(detector.push(frame))

    self.assertNotIn('start', [event.kind for event in events])
    self.assertNotIn('utterance', [event.kind for event in events])

  def test_hybrid_endpoint_reports_one_rejected_noise_burst(self):
    gate = vad.AdaptiveSpeechGate(is_speech=lambda _frame: True)
    detector = vad.EndpointDetector(speech_gate=gate)
    noise = self._frame(0.01)

    events = []
    for _ in range(30):
      events.extend(detector.push(noise))

    self.assertEqual([event.kind for event in events], ['candidate_rejected'])

  def test_arbitrary_stream_alignment_does_not_split_a_natural_pause(self):
    silence = self._frame(0)
    speech = self._frame(0.2)
    detector = vad.EndpointDetector(
        speech_gate=vad.AdaptiveSpeechGate(
            is_speech=lambda frame: frame != silence
        )
    )
    # Five seconds is not divisible by a 30 ms VAD frame. Keep the remainder
    # to reproduce arbitrary microphone alignment.
    stream = (b'\0' * (16000 * 2 * 5)) + (speech * 8) + (silence * 12)
    stream += (speech * 8) + (silence * 15)

    events = []
    for offset in range(0, len(stream) - vad.FRAME_BYTES + 1, vad.FRAME_BYTES):
      events.extend(detector.push(stream[offset : offset + vad.FRAME_BYTES]))
    events.extend(detector.flush())

    self.assertEqual([event.kind for event in events].count('start'), 1)
    self.assertEqual([event.kind for event in events].count('utterance'), 1)

  def test_emits_bounded_utterance_after_speech_and_silence(self):
    speech = b'\x01\x00' * 480
    silence = b'\x00\x00' * 480
    detector = vad.EndpointDetector(
        is_speech=lambda frame: frame == speech,
        start_frames=3,
        end_frames=3,
        pre_roll_frames=1,
        max_frames=20,
    )

    events = []
    for frame in [silence, speech, speech, speech, speech, silence] + [
        silence,
        silence,
    ]:
      events.extend(detector.push(frame))

    self.assertEqual(events[0].kind, 'start')
    self.assertEqual(events[-1].kind, 'utterance')
    self.assertGreater(len(events[-1].audio), 0)
    self.assertLessEqual(len(events[-1].audio), 20 * 960)

  def test_rejects_non_pcm16_30ms_frames(self):
    detector = vad.EndpointDetector(is_speech=lambda _: False)
    with self.assertRaisesRegex(ValueError, '960'):
      detector.push(b'invalid')


class ParakeetAdapterTest(unittest.IsolatedAsyncioTestCase):

  def test_normalizes_decoder_special_tokens_and_punctuation(self):
    self.assertEqual(
        parakeet.normalize_transcript(
            '<blank><blank> Leônidas<blank>, diga <unk> oi!'
        ),
        'Leônidas, diga oi!',
    )

  async def test_casts_floating_inputs_to_the_cuda_model_dtype(self):
    class FloatInput:

      def __init__(self):
        self.dtype = 'float32'

      def is_floating_point(self):
        return True

      def to(self, *, dtype):
        self.dtype = dtype
        return self

    class Inputs(dict):

      def to(self, device):
        self.device = device
        return self

    class Processor:

      def __call__(self, *_args, **_kwargs):
        return Inputs(input_features=FloatInput())

      def batch_decode(self, _ids):
        return ['texto']

    class Model:
      dtype = 'float16'

      def generate(self, **kwargs):
        self.input_dtype = kwargs['input_features'].dtype
        return [1]

    model = Model()
    adapter = parakeet.ParakeetTranscriber(
        device='cuda',
        loader=lambda _model, _device: (Processor(), model),
    )

    await adapter.transcribe(b'\x00\x00' * 480)

    self.assertEqual(model.input_dtype, 'float16')

  async def test_converts_pcm16_and_decodes_transcription_off_event_loop(self):
    class Inputs(dict):

      def to(self, _device):
        return self

    class Processor:

      def __call__(self, audio, sampling_rate, return_tensors):
        self.audio = audio
        self.sampling_rate = sampling_rate
        self.return_tensors = return_tensors
        return Inputs(input_values='samples')

      def batch_decode(self, _ids):
        return ['Leonidas ouviu a frase.']

    class Result:
      sequences = [1]

    class Model:

      def generate(self, **kwargs):
        self.kwargs = kwargs
        return Result()

    processor = Processor()
    model = Model()
    adapter = parakeet.ParakeetTranscriber(
        device='cpu', loader=lambda _model, _device: (processor, model)
    )

    result = await adapter.transcribe(b'\xff\x7f\x00\x80')

    self.assertEqual(result, 'Leonidas ouviu a frase.')
    self.assertEqual(processor.sampling_rate, 16000)
    self.assertEqual(processor.return_tensors, 'pt')
    np.testing.assert_allclose(processor.audio, [32767 / 32768, -1.0])

  async def test_serializes_inference_and_loads_the_model_once(self):
    concurrent = 0
    maximum = 0
    loader_calls = 0
    guard = threading.Lock()

    class Inputs(dict):

      def to(self, _device):
        return self

    class Processor:

      def __call__(self, *_args, **_kwargs):
        return Inputs(input_values='samples')

      def batch_decode(self, _ids):
        return ['texto']

    class Result:
      sequences = [1]

    class Model:

      def generate(self, **_kwargs):
        nonlocal concurrent, maximum
        with guard:
          concurrent += 1
          maximum = max(maximum, concurrent)
        time.sleep(0.05)
        with guard:
          concurrent -= 1
        return Result()

    def loader(_model, _device):
      nonlocal loader_calls
      loader_calls += 1
      time.sleep(0.05)
      return Processor(), Model()

    adapter = parakeet.ParakeetTranscriber(device='cpu', loader=loader)
    await asyncio.gather(
        adapter.transcribe(b'\x00\x00' * 480),
        adapter.transcribe(b'\x00\x00' * 480),
    )

    self.assertEqual(loader_calls, 1)
    self.assertEqual(maximum, 1)


class ParakeetWorkerTest(unittest.IsolatedAsyncioTestCase):

  async def test_worker_reports_load_progress_and_transcribes(self):
    worker_source = """
import base64
import json
import sys
for line in sys.stdin:
  request = json.loads(line)
  if request['op'] == 'load':
    print(json.dumps({'type': 'event', 'id': request['id'], 'phase': 'warming'}), flush=True)
    print(json.dumps({'type': 'result', 'id': request['id'], 'device': 'cpu'}), flush=True)
  else:
    assert base64.b64decode(request['audio']) == b'pcm'
    print(json.dumps({'type': 'result', 'id': request['id'], 'text': 'fala teste'}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'fake_parakeet_worker.py').write_text(
          worker_source, encoding='utf-8'
      )
      adapter = parakeet_process.ParakeetWorkerTranscriber(
          device='cpu',
          python=Path(sys.executable),
          worker_module='fake_parakeet_worker',
          worker_cwd=root,
      )
      phases = []

      async def progress(phase):
        phases.append(phase)

      details = await adapter.load(progress=progress)
      transcript = await adapter.transcribe(b'pcm')
      await adapter.close()

    self.assertEqual(phases, ['warming'])
    self.assertEqual(details['device'], 'cpu')
    self.assertNotIn('id', details)
    self.assertNotIn('type', details)
    self.assertEqual(transcript, 'fala teste')


class GroqReasonerTest(unittest.IsolatedAsyncioTestCase):

  async def test_sends_allowlisted_reasoning_effort_without_logging_secret(
      self,
  ):
    captured = {}

    async def handler(request):
      captured['authorization'] = request.headers['Authorization']
      captured['json'] = __import__('json').loads(request.content)
      return httpx.Response(
          200,
          json={'choices': [{'message': {'content': 'Resposta útil.'}}]},
      )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reasoner = groq_reasoning.GroqReasoner(
        api_key='private-test-key', client=client
    )
    try:
      result = await reasoner.respond(
          objective='Ajude em português.',
          history=[('user', 'Olá')],
          prompt='O que você ouviu?',
          model_id='openai/gpt-oss-20b',
          reasoning_effort='medium',
      )
    finally:
      await reasoner.close()

    self.assertEqual(result, 'Resposta útil.')
    self.assertEqual(captured['json']['reasoning_effort'], 'medium')
    self.assertEqual(captured['json']['model'], 'openai/gpt-oss-20b')
    self.assertEqual(captured['authorization'], 'Bearer private-test-key')


class XttsAdapterTest(unittest.IsolatedAsyncioTestCase):

  async def test_synthesizes_pcm16_with_allowlisted_reference(self):
    class Engine:

      def to(self, device):
        self.device = device
        return self

      def tts(self, text, speaker_wav, language):
        self.arguments = (text, speaker_wav, language)
        return np.array([-1.0, 0.0, 0.5, 1.0], dtype=np.float32)

    engine = Engine()
    with tempfile.TemporaryDirectory() as temp_dir:
      voice = Path(temp_dir) / 'leonidas.wav'
      voice.write_bytes(b'RIFF-demo')
      adapter = xtts.XttsSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          engine_factory=lambda _model: engine,
      )
      pcm = await adapter.synthesize('Olá!', voice_id='leonidas', language='pt')

    self.assertEqual(engine.device, 'cpu')
    self.assertEqual(engine.arguments[2], 'pt')
    self.assertEqual(len(pcm), 8)
    self.assertEqual(
        np.frombuffer(pcm, dtype='<i2').tolist(), [-32767, 0, 16383, 32767]
    )

  async def test_rejects_unknown_voice_before_model_loading(self):
    adapter = xtts.XttsSynthesizer(
        device='cpu', voices={}, engine_factory=lambda _: self.fail()
    )
    with self.assertRaisesRegex(ValueError, 'voice_id'):
      await adapter.synthesize('Olá', voice_id='missing', language='pt')

  def test_worker_runtime_requires_explicit_license_agreement(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      python = root / 'python'
      voice = root / 'voice.wav'
      python.write_bytes(b'executable')
      voice.write_bytes(b'RIFF-demo')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=python,
          tts_home=root / 'tts',
      )

      with self.assertRaisesRegex(RuntimeError, 'CPML') as raised:
        adapter.validate_runtime()
      self.assertIn('--use_cuda --out_path', str(raised.exception))
      self.assertNotIn('--use_cuda true', str(raised.exception))

  async def test_worker_process_contract_returns_pcm_and_stops_cleanly(self):
    worker_source = """
import base64
import json
import sys
for line in sys.stdin:
  request = json.loads(line)
  print(json.dumps({'id': request['id'], 'audio': base64.b64encode(b'x' * 70000).decode()}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'fake_xtts_worker.py').write_text(worker_source, encoding='utf-8')
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      agreement = (
          root
          / 'tts'
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('test agreement fixture', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=root / 'tts',
          worker_module='fake_xtts_worker',
          worker_cwd=root,
      )

      pcm = await adapter.synthesize('Olá', voice_id='leonidas', language='pt')
      await adapter.close()

    self.assertEqual(pcm, b'x' * 70000)

  async def test_worker_load_reports_progress_and_runtime_details(self):
    worker_source = """
import json
import sys
for line in sys.stdin:
  request = json.loads(line)
  print(json.dumps({'type': 'event', 'id': request['id'], 'phase': 'warming'}), flush=True)
  print(json.dumps({'type': 'result', 'id': request['id'], 'device': 'cpu'}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'fake_xtts_load_worker.py').write_text(
          worker_source, encoding='utf-8'
      )
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      agreement = (
          root
          / 'tts'
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('test agreement fixture', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=root / 'tts',
          worker_module='fake_xtts_load_worker',
          worker_cwd=root,
      )
      phases = []

      async def progress(phase):
        phases.append(phase)

      details = await adapter.load(progress=progress)
      await adapter.close()

    self.assertEqual(phases, ['warming'])
    self.assertEqual(details['device'], 'cpu')
    self.assertNotIn('id', details)
    self.assertNotIn('type', details)

  async def test_worker_timeout_is_bounded_and_cleanup_remains_possible(self):
    worker_source = """
import base64
import json
import sys
import time
for line in sys.stdin:
  request = json.loads(line)
  time.sleep(0.2)
  print(json.dumps({'id': request['id'], 'audio': base64.b64encode(b'pcm').decode()}), flush=True)
"""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      (root / 'slow_xtts_worker.py').write_text(worker_source, encoding='utf-8')
      voice = root / 'voice.wav'
      voice.write_bytes(b'RIFF-demo')
      agreement = (
          root
          / 'tts'
          / 'tts_models--multilingual--multi-dataset--xtts_v2'
          / 'tos_agreed.txt'
      )
      agreement.parent.mkdir(parents=True)
      agreement.write_text('test agreement fixture', encoding='utf-8')
      adapter = xtts_process.XttsWorkerSynthesizer(
          device='cpu',
          voices={'leonidas': voice},
          python=Path(sys.executable),
          tts_home=root / 'tts',
          worker_module='slow_xtts_worker',
          worker_cwd=root,
          timeout=0.05,
      )

      with self.assertRaises(TimeoutError):
        await adapter.synthesize('Olá', voice_id='leonidas', language='pt')
      await adapter.close()


class CascadeResourcesTest(unittest.IsolatedAsyncioTestCase):

  async def test_prepare_loads_components_sequentially_and_publishes_status(
      self,
  ):
    order = []
    availability = mock.patch.object(
        diarization,
        'availability',
        return_value={'state': 'unavailable'},
    )
    availability.start()
    self.addCleanup(availability.stop)

    class Resource:

      def __init__(self, name):
        self.name = name

      async def load(self, progress=None):
        order.append(f'{self.name}:start')
        if progress is not None:
          await progress('warming')
        order.append(f'{self.name}:ready')
        return {
            'device': 'cuda',
            'gpu_name': 'Test GPU',
            'memory_allocated_mib': 100,
            'memory_reserved_mib': 120,
        }

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cuda',
        transcriber_factory=lambda **_kwargs: Resource('stt'),
        synthesizer_factory=lambda **_kwargs: Resource('tts'),
    )
    snapshots = []
    pool.add_listener(snapshots.append)

    await pool.ensure_ready('stt-model', 'tts-model', 'auto')

    self.assertEqual(
        order, ['stt:start', 'stt:ready', 'tts:start', 'tts:ready']
    )
    self.assertEqual(pool.snapshot()['overall_state'], 'ready')
    self.assertEqual(
        [item['state'] for item in pool.snapshot()['components']],
        ['ready', 'ready', 'unavailable'],
    )
    self.assertTrue(
        any(item['overall_state'] == 'loading' for item in snapshots)
    )

  async def test_prepare_loads_optional_diarizer_when_enabled(self):
    order = []

    class Resource:

      def __init__(self, name):
        self.name = name
        self.device = 'cpu'

      async def load(self, progress=None):
        order.append(f'{self.name}:start')
        if progress is not None:
          await progress('warming')
        order.append(f'{self.name}:ready')
        return {'device': self.device}

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=lambda **_kwargs: Resource('stt'),
        synthesizer_factory=lambda **_kwargs: Resource('tts'),
        diarizer_factory=lambda **_kwargs: Resource('diarization'),
    )

    snapshot = await pool.ensure_ready(
        'stt-model',
        'tts-model',
        'cpu',
        diarization_enabled=True,
    )

    self.assertEqual(
        order,
        [
            'stt:start',
            'stt:ready',
            'tts:start',
            'tts:ready',
            'diarization:start',
            'diarization:ready',
        ],
    )
    self.assertEqual(
        [item['state'] for item in snapshot['components']],
        ['ready', 'ready', 'ready'],
    )
    await pool.close()

  async def test_status_listener_failure_cannot_abort_model_loading(self):
    class Resource:

      async def load(self, progress=None):
        del progress
        return {'device': 'cpu'}

    async def disconnected_listener(_snapshot):
      raise ConnectionError('browser disconnected')

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=lambda **_kwargs: Resource(),
        synthesizer_factory=lambda **_kwargs: Resource(),
    )
    pool.add_listener(disconnected_listener)

    await pool.ensure_ready('stt', 'tts', 'cpu')

    self.assertEqual(pool.snapshot()['overall_state'], 'ready')

  async def test_prepare_is_shared_and_reused(self):
    calls = 0

    class Resource:

      async def load(self, progress=None):
        del progress
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {'device': 'cpu'}

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=lambda **_kwargs: Resource(),
        synthesizer_factory=lambda **_kwargs: Resource(),
    )

    await asyncio.gather(
        pool.ensure_ready('stt', 'tts', 'auto'),
        pool.ensure_ready('stt', 'tts', 'cpu'),
    )
    await pool.ensure_ready('stt', 'tts', 'auto')

    self.assertEqual(calls, 2)

  async def test_different_configuration_waits_then_prepares_its_own_models(
      self,
  ):
    loaded = []

    class Resource:

      def __init__(self, model_id):
        self.model_id = model_id

      async def load(self, progress=None):
        del progress
        loaded.append(self.model_id)
        await asyncio.sleep(0)
        return {'device': 'cpu'}

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cpu',
        transcriber_factory=lambda **kwargs: Resource(kwargs['model_id']),
        synthesizer_factory=lambda **kwargs: Resource(kwargs['model_id']),
    )

    await asyncio.gather(
        pool.ensure_ready('stt-a', 'tts-a', 'cpu'),
        pool.ensure_ready('stt-b', 'tts-b', 'cpu'),
    )

    self.assertEqual(loaded, ['stt-a', 'tts-a', 'stt-b', 'tts-b'])

  async def test_auto_and_explicit_device_share_local_model_instances(self):
    transcribers = []
    synthesizers = []

    def transcriber_factory(*, model_id, device):
      value = object()
      transcribers.append((model_id, device, value))
      return value

    class Synthesizer:

      async def close(self):
        self.closed = True

    def synthesizer_factory(*, model_id, device, voices):
      del voices
      value = Synthesizer()
      synthesizers.append((model_id, device, value))
      return value

    pool = resources.CascadeResources(
        voices={},
        device_resolver=lambda _requested: 'cuda',
        transcriber_factory=transcriber_factory,
        synthesizer_factory=synthesizer_factory,
    )

    first_stt = pool.transcriber('model-stt', 'auto')
    second_stt = pool.transcriber('model-stt', 'cuda')
    first_tts = pool.synthesizer('model-tts', 'auto')
    second_tts = pool.synthesizer('model-tts', 'cuda')
    await pool.close()

    self.assertIs(first_stt, second_stt)
    self.assertIs(first_tts, second_tts)
    self.assertEqual(len(transcribers), 1)
    self.assertEqual(len(synthesizers), 1)
    self.assertTrue(first_tts.closed)


class CascadeProcessorTest(unittest.IsolatedAsyncioTestCase):

  async def test_rejected_noise_never_reaches_stt_or_interrupts(self):
    class Unused:

      async def transcribe(self, _audio):
        self.fail('STT must not run for rejected noise')

      async def respond(self, **_kwargs):
        self.fail('Groq must not run for rejected noise')

      async def synthesize(self, _text, **_kwargs):
        self.fail('XTTS must not run for rejected noise')

      def fail(self, message):
        raise AssertionError(message)

    noise = np.full(480, int(32767 * 0.01), dtype='<i2').tobytes()
    endpoint = vad.EndpointDetector(
        speech_gate=vad.AdaptiveSpeechGate(is_speech=lambda _frame: True)
    )
    metrics = telemetry.MetricsStore()

    async def inputs():
      yield content_api.ProcessorPart(
          noise * 30,
          mimetype='audio/pcm;rate=16000',
          metadata={'audio_stream_end': True},
      )

    unused = Unused()
    cascade = pipeline.CascadeProcessor(
        transcriber=unused,
        reasoner=unused,
        synthesizer=unused,
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
        endpoint_detector=endpoint,
        metrics=metrics,
    )

    output = [part async for part in cascade(inputs())]

    self.assertEqual(output, [])
    self.assertEqual(
        metrics.snapshot()['counters']['vad_candidates_rejected'], 1
    )

  async def test_turn_publishes_stages_and_stage_latencies(self):
    class Transcriber:

      async def transcribe(self, _audio):
        return 'não usado'

    class Reasoner:

      async def respond(self, **_kwargs):
        return 'Resposta.'

    class Synthesizer:

      async def synthesize(self, _text, **_kwargs):
        return b'\x00\x00' * 1200

    async def inputs():
      yield content_api.ProcessorPart('Teste')

    metrics = telemetry.MetricsStore()
    cascade = pipeline.CascadeProcessor(
        transcriber=Transcriber(),
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
        metrics=metrics,
    )

    output = [part async for part in cascade(inputs())]
    stages = [
        part.get_metadata('agent_state')
        for part in output
        if part.mimetype == 'application/x-state'
    ]

    self.assertEqual(
        stages, ['thinking', 'synthesizing', 'speaking', 'listening']
    )
    observed = metrics.snapshot()['metrics']
    self.assertIn('groq_reasoning_ms', observed)
    self.assertIn('local_tts_ms', observed)

  async def test_text_turn_emits_text_audio_and_completion_contract(self):
    class Transcriber:

      async def transcribe(self, _audio):
        return 'não usado'

    class Reasoner:

      async def respond(self, **kwargs):
        self.kwargs = kwargs
        return 'Estou pronto para ajudar.'

    class Synthesizer:

      async def synthesize(self, text, **kwargs):
        self.text = text
        return b'\x01\x00' * 2400

    async def inputs():
      yield content_api.ProcessorPart('Você está aí?', role='user')

    cascade = pipeline.CascadeProcessor(
        transcriber=Transcriber(),
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Converse em português.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
    )
    output = [part async for part in cascade(inputs())]

    self.assertTrue(
        any(
            content_api.is_text(part.mimetype)
            and part.text == 'Estou pronto para ajudar.'
            for part in output
        )
    )
    audio = [part for part in output if part.mimetype == 'audio/pcm;rate=24000']
    self.assertGreater(len(audio), 1)
    self.assertTrue(output[-1].get_metadata('generation_complete'))

  async def test_diarization_contract_emits_two_synthetic_speakers(self):
    class Transcriber:

      async def transcribe(self, _audio):
        return 'duas pessoas falando'

    class Reasoner:

      async def respond(self, **_kwargs):
        return 'Entendi as duas vozes.'

    class Synthesizer:

      async def synthesize(self, _text, **_kwargs):
        return b'\x00\x00' * 1200

    class SyntheticDiarizer:

      async def diarize(self, audio, *, sample_rate):
        self.audio = audio
        self.sample_rate = sample_rate
        midpoint = len(audio) / (sample_rate * 2) / 2
        return [
            diarization.SpeakerSegment('SPEAKER_00', 0.0, midpoint, 0.91),
            diarization.SpeakerSegment(
                'SPEAKER_01', midpoint, midpoint * 2, 0.88
            ),
        ]

    first_speaker = np.full(480, 5000, dtype='<i2').tobytes()
    second_speaker = np.full(480, -5000, dtype='<i2').tobytes()
    endpoint = vad.EndpointDetector(
        is_speech=lambda frame: bool(frame.strip(b'\x00')),
        start_frames=1,
        end_frames=1,
        pre_roll_frames=0,
    )

    async def inputs():
      yield content_api.ProcessorPart(
          first_speaker + second_speaker + b'\x00\x00' * 480,
          mimetype='audio/pcm;rate=16000',
      )

    synthetic = SyntheticDiarizer()
    cascade = pipeline.CascadeProcessor(
        transcriber=Transcriber(),
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
        endpoint_detector=endpoint,
        diarizer=synthetic,
    )
    output = [part async for part in cascade(inputs())]

    diarization_parts = [
        part for part in output if part.substream_name == 'diarization'
    ]
    self.assertEqual(len(diarization_parts), 1)
    self.assertEqual(synthetic.sample_rate, 16000)
    segments = diarization_parts[0].get_metadata('speaker_segments')
    self.assertEqual(
        [item['speaker_id'] for item in segments],
        [
            'SPEAKER_00',
            'SPEAKER_01',
        ],
    )
    self.assertEqual([item['confidence'] for item in segments], [0.91, 0.88])
    self.assertEqual(segments[0]['start'], 0.0)
    self.assertGreater(segments[0]['end'], segments[0]['start'])
    self.assertEqual(segments[1]['start'], segments[0]['end'])
    self.assertGreater(segments[1]['end'], segments[1]['start'])

  async def test_audio_frames_are_reassembled_across_websocket_chunks(self):
    utterance = b'\x01\x00' * 480
    endpoint = vad.EndpointDetector(
        is_speech=lambda frame: bool(frame.strip(b'\x00')),
        start_frames=1,
        end_frames=1,
        pre_roll_frames=0,
    )

    class Transcriber:

      async def transcribe(self, audio):
        self.audio = audio
        return 'fala detectada'

    class Reasoner:

      async def respond(self, **_kwargs):
        return 'Resposta.'

    class Synthesizer:

      async def synthesize(self, _text, **_kwargs):
        return b'\x00\x00' * 1200

    transcriber = Transcriber()

    async def inputs():
      payload = utterance + (b'\x00\x00' * 480)
      yield content_api.ProcessorPart(
          payload[:701], mimetype='audio/pcm;rate=16000'
      )
      yield content_api.ProcessorPart(
          payload[701:], mimetype='audio/pcm;rate=16000'
      )

    cascade = pipeline.CascadeProcessor(
        transcriber=transcriber,
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
        endpoint_detector=endpoint,
    )
    output = [part async for part in cascade(inputs())]

    self.assertIn(
        'fala detectada',
        [part.text for part in output if content_api.is_text(part.mimetype)],
    )
    self.assertEqual(transcriber.audio[:960], utterance)

  async def test_rejects_vision_and_wrong_audio_format_explicitly(self):
    class Unused:

      async def transcribe(self, _audio):
        return ''

      async def respond(self, **_kwargs):
        return ''

      async def synthesize(self, _text, **_kwargs):
        return b''

    cascade = pipeline.CascadeProcessor(
        transcriber=Unused(),
        reasoner=Unused(),
        synthesizer=Unused(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
    )

    async def image_input():
      yield content_api.ProcessorPart(b'image', mimetype='image/jpeg')

    with self.assertRaisesRegex(ValueError, 'vision'):
      _ = [part async for part in cascade(image_input())]

    async def bad_audio_input():
      yield content_api.ProcessorPart(
          b'\x00\x00' * 480, mimetype='audio/pcm;rate=24000'
      )

    with self.assertRaisesRegex(ValueError, '16000'):
      _ = [part async for part in cascade(bad_audio_input())]

  async def test_barge_in_is_emitted_before_blocking_tts_cleanup_finishes(self):
    started = asyncio.Event()
    release_cleanup = asyncio.Event()

    class Transcriber:

      async def transcribe(self, _audio):
        return ''

    class Reasoner:

      async def respond(self, **_kwargs):
        return 'Resposta longa.'

    class Synthesizer:

      async def synthesize(self, _text, **_kwargs):
        started.set()
        try:
          await asyncio.Future()
        except asyncio.CancelledError:
          await release_cleanup.wait()
          raise

    endpoint = vad.EndpointDetector(
        is_speech=lambda _frame: True,
        start_frames=1,
        pre_roll_frames=0,
    )

    async def inputs():
      yield content_api.ProcessorPart('Comece a responder.')
      await started.wait()
      yield content_api.ProcessorPart(
          b'\x01\x00' * 480, mimetype='audio/pcm;rate=16000'
      )

    metrics = telemetry.MetricsStore()
    cascade = pipeline.CascadeProcessor(
        transcriber=Transcriber(),
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
        endpoint_detector=endpoint,
        metrics=metrics,
    )
    stream = cascade(inputs()).__aiter__()
    first = None
    interrupted = None
    while interrupted is None:
      part = await asyncio.wait_for(anext(stream), 1)
      if content_api.is_text(part.mimetype) and part.text:
        first = part
      if part.get_metadata('interrupted'):
        interrupted = part

    self.assertIsNotNone(first)
    self.assertEqual(first.text, 'Resposta longa.')
    self.assertTrue(interrupted.get_metadata('interrupted'))
    release_cleanup.set()
    _ = [part async for part in stream]
    counters = metrics.snapshot()['counters']
    self.assertEqual(counters['vad_utterances_started'], 1)
    self.assertEqual(counters['turn_interruptions'], 1)
    self.assertEqual(counters['local_tts_cancelled'], 1)

  async def test_failed_turn_is_retrieved_and_stops_the_session(self):
    calls = 0

    class Transcriber:

      async def transcribe(self, _audio):
        return ''

    class Reasoner:

      async def respond(self, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
          raise RuntimeError('provider failed')
        return 'should not run'

    class Synthesizer:

      async def synthesize(self, _text, **_kwargs):
        return b''

    async def inputs():
      yield content_api.ProcessorPart('primeiro turno')
      await asyncio.sleep(0.01)
      yield content_api.ProcessorPart('segundo turno')

    cascade = pipeline.CascadeProcessor(
        transcriber=Transcriber(),
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
    )

    with self.assertRaisesRegex(RuntimeError, 'provider failed'):
      _ = [part async for part in cascade(inputs())]
    self.assertEqual(calls, 1)

  async def test_failed_turn_wakes_an_idle_realtime_input_stream(self):
    class Transcriber:

      async def transcribe(self, _audio):
        return ''

    class Reasoner:

      async def respond(self, **_kwargs):
        raise RuntimeError('provider failed while input remained open')

    class Synthesizer:

      async def synthesize(self, _text, **_kwargs):
        return b''

    async def inputs():
      yield content_api.ProcessorPart('turno único')
      await asyncio.Future()

    cascade = pipeline.CascadeProcessor(
        transcriber=Transcriber(),
        reasoner=Reasoner(),
        synthesizer=Synthesizer(),
        objective='Ajude.',
        model_id='openai/gpt-oss-20b',
        reasoning_effort='medium',
        voice_id='leonidas',
    )
    stream = cascade(inputs()).__aiter__()

    state = await asyncio.wait_for(anext(stream), 1)
    self.assertEqual(state.get_metadata('agent_state'), 'thinking')
    with self.assertRaisesRegex(RuntimeError, 'input remained open'):
      await asyncio.wait_for(anext(stream), 1)


if __name__ == '__main__':
  unittest.main()
