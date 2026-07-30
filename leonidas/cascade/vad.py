"""Deterministic WebRTC-VAD endpointing for 16 kHz mono PCM16."""

import collections
import dataclasses
from typing import Callable


FRAME_BYTES = 960


@dataclasses.dataclass(frozen=True)
class EndpointEvent:
  kind: str
  audio: bytes = b''


class EndpointDetector:
  """Collects 30 ms frames into bounded speech utterances."""

  def __init__(
      self,
      *,
      is_speech: Callable[[bytes], bool] | None = None,
      start_frames: int = 3,
      end_frames: int = 15,
      pre_roll_frames: int = 10,
      max_frames: int = 1000,
  ):
    if is_speech is None:
      import webrtcvad

      detector = webrtcvad.Vad(2)
      is_speech = lambda frame: detector.is_speech(frame, 16000)
    self._is_speech = is_speech
    self._start_frames = start_frames
    self._end_frames = end_frames
    self._max_frames = max_frames
    self._pre_roll = collections.deque(maxlen=pre_roll_frames)
    self._candidate: list[bytes] = []
    self._utterance: list[bytes] = []
    self._speaking = False
    self._silence_frames = 0

  def push(self, frame: bytes) -> list[EndpointEvent]:
    if len(frame) != FRAME_BYTES:
      raise ValueError('VAD requires exactly 960-byte PCM16 16 kHz frames')
    speech = self._is_speech(frame)
    if not self._speaking:
      self._pre_roll.append(frame)
      if speech:
        self._candidate.append(frame)
      else:
        self._candidate.clear()
      if len(self._candidate) < self._start_frames:
        return []
      self._speaking = True
      self._utterance = list(self._pre_roll) or list(self._candidate)
      self._candidate.clear()
      self._silence_frames = 0
      return [EndpointEvent('start')]

    self._utterance.append(frame)
    self._silence_frames = 0 if speech else self._silence_frames + 1
    if (
        self._silence_frames < self._end_frames
        and len(self._utterance) < self._max_frames
    ):
      return []
    audio = b''.join(self._utterance[: self._max_frames])
    self._reset()
    return [EndpointEvent('end'), EndpointEvent('utterance', audio)]

  def flush(self) -> list[EndpointEvent]:
    if not self._speaking or not self._utterance:
      self._reset()
      return []
    audio = b''.join(self._utterance[: self._max_frames])
    self._reset()
    return [EndpointEvent('end'), EndpointEvent('utterance', audio)]

  def _reset(self) -> None:
    self._pre_roll.clear()
    self._candidate.clear()
    self._utterance = []
    self._speaking = False
    self._silence_frames = 0
