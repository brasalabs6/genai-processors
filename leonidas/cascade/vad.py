"""Deterministic WebRTC-VAD endpointing for 16 kHz mono PCM16."""

import array
import collections
import dataclasses
import math
import sys
from typing import Callable


FRAME_BYTES = 960


@dataclasses.dataclass(frozen=True)
class EndpointEvent:
  kind: str
  audio: bytes = b''


@dataclasses.dataclass(frozen=True)
class FrameDecision:
  speech: bool
  raw_speech: bool
  level_dbfs: float
  threshold_dbfs: float
  calibrating: bool = False


class AdaptiveSpeechGate:
  """Combines aggressive WebRTC VAD with an adaptive energy floor."""

  def __init__(
      self,
      *,
      is_speech: Callable[[bytes], bool] | None = None,
      calibration_frames: int = 10,
      noise_window_frames: int = 67,
      noise_margin_db: float = 10.0,
      minimum_threshold_dbfs: float = -52.0,
      maximum_threshold_dbfs: float = -32.0,
  ):
    if is_speech is None:
      import webrtcvad

      detector = webrtcvad.Vad(3)
      is_speech = lambda frame: detector.is_speech(frame, 16000)
    self._is_speech = is_speech
    self._calibration_frames = calibration_frames
    self._noise_margin_db = noise_margin_db
    self._minimum_threshold_dbfs = minimum_threshold_dbfs
    self._maximum_threshold_dbfs = maximum_threshold_dbfs
    self._levels: collections.deque[float] = collections.deque(
        maxlen=noise_window_frames
    )
    self._frames_seen = 0

  @staticmethod
  def _level_dbfs(frame: bytes) -> float:
    samples = array.array('h')
    samples.frombytes(frame)
    if sys.byteorder != 'little':
      samples.byteswap()
    if not samples:
      return -96.0
    mean_square = sum(float(value) * value for value in samples) / len(samples)
    if mean_square <= 0:
      return -96.0
    return max(-96.0, 20.0 * math.log10(math.sqrt(mean_square) / 32768.0))

  def _noise_floor(self) -> float:
    if not self._levels:
      return -62.0
    ordered = sorted(self._levels)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.2))
    return ordered[index]

  def classify(self, frame: bytes) -> FrameDecision:
    if len(frame) != FRAME_BYTES:
      raise ValueError('VAD requires exactly 960-byte PCM16 16 kHz frames')
    level = self._level_dbfs(frame)
    raw_speech = self._is_speech(frame)
    calibrating = self._frames_seen < self._calibration_frames
    self._frames_seen += 1
    if calibrating:
      self._levels.append(level)
    threshold = max(
        self._minimum_threshold_dbfs,
        min(
            self._maximum_threshold_dbfs,
            self._noise_floor() + self._noise_margin_db,
        ),
    )
    speech = not calibrating and raw_speech and level >= threshold
    if not speech:
      self._levels.append(level)
    return FrameDecision(speech, raw_speech, level, threshold, calibrating)


class EndpointDetector:
  """Collects 30 ms frames into bounded speech utterances."""

  def __init__(
      self,
      *,
      is_speech: Callable[[bytes], bool] | None = None,
      speech_gate: AdaptiveSpeechGate | None = None,
      start_frames: int = 4,
      start_window_frames: int = 6,
      end_frames: int = 15,
      pre_roll_frames: int = 6,
      max_frames: int = 1000,
      minimum_voiced_frames: int | None = None,
      minimum_voiced_ratio: float = 0.12,
  ):
    if speech_gate is not None and is_speech is not None:
      raise ValueError('Pass speech_gate or is_speech, not both')
    self._speech_gate = speech_gate
    self._is_speech = is_speech
    if speech_gate is None and is_speech is None:
      self._speech_gate = AdaptiveSpeechGate()
    self._start_frames = start_frames
    self._end_frames = end_frames
    self._max_frames = max_frames
    self._minimum_voiced_frames = minimum_voiced_frames or start_frames
    self._minimum_voiced_ratio = minimum_voiced_ratio
    self._pre_roll: collections.deque[bytes] = collections.deque(
        maxlen=pre_roll_frames
    )
    self._start_window: collections.deque[tuple[bytes, bool]] = (
        collections.deque(maxlen=start_window_frames)
    )
    self._utterance: list[bytes] = []
    self._speaking = False
    self._silence_frames = 0
    self._voiced_frames = 0
    self._raw_rejection_active = False

  def _classify(self, frame: bytes) -> FrameDecision:
    if self._speech_gate is not None:
      return self._speech_gate.classify(frame)
    speech = bool(self._is_speech and self._is_speech(frame))
    return FrameDecision(speech, speech, 0.0, 0.0)

  def push(self, frame: bytes) -> list[EndpointEvent]:
    if len(frame) != FRAME_BYTES:
      raise ValueError('VAD requires exactly 960-byte PCM16 16 kHz frames')
    decision = self._classify(frame)
    speech = decision.speech
    if not self._speaking:
      events: list[EndpointEvent] = []
      rejected_raw = (
          decision.raw_speech and not speech and not decision.calibrating
      )
      if rejected_raw and not self._raw_rejection_active:
        events.append(EndpointEvent('candidate_rejected'))
      self._raw_rejection_active = rejected_raw
      if len(self._start_window) == self._start_window.maxlen:
        previous, _ = self._start_window.popleft()
        self._pre_roll.append(previous)
      self._start_window.append((frame, speech))
      if sum(value for _, value in self._start_window) < self._start_frames:
        return events
      self._speaking = True
      self._utterance = [*self._pre_roll]
      self._utterance.extend(value for value, _ in self._start_window)
      self._voiced_frames = sum(value for _, value in self._start_window)
      self._start_window.clear()
      self._silence_frames = 0
      self._raw_rejection_active = False
      return [*events, EndpointEvent('start')]

    self._utterance.append(frame)
    self._voiced_frames += int(speech)
    self._silence_frames = 0 if speech else self._silence_frames + 1
    if (
        self._silence_frames < self._end_frames
        and len(self._utterance) < self._max_frames
    ):
      return []
    audio = b''.join(self._utterance[: self._max_frames])
    accepted = self._accept_utterance()
    self._reset()
    events = [EndpointEvent('end')]
    events.append(
        EndpointEvent('utterance', audio)
        if accepted
        else EndpointEvent('candidate_rejected')
    )
    return events

  def flush(self) -> list[EndpointEvent]:
    if not self._speaking or not self._utterance:
      self._reset()
      return []
    audio = b''.join(self._utterance[: self._max_frames])
    accepted = self._accept_utterance()
    self._reset()
    events = [EndpointEvent('end')]
    events.append(
        EndpointEvent('utterance', audio)
        if accepted
        else EndpointEvent('candidate_rejected')
    )
    return events

  def _accept_utterance(self) -> bool:
    total = len(self._utterance)
    return bool(
        total
        and self._voiced_frames >= self._minimum_voiced_frames
        and self._voiced_frames / total >= self._minimum_voiced_ratio
    )

  def _reset(self) -> None:
    self._pre_roll.clear()
    self._start_window.clear()
    self._utterance = []
    self._speaking = False
    self._silence_frames = 0
    self._voiced_frames = 0
    self._raw_rejection_active = False
