"""Small provider-neutral contracts; intentionally no model SDK dependencies."""

from dataclasses import dataclass
from typing import Literal


class CapabilityError(ValueError):
  """A requested feature cannot be provided by the selected backend."""


@dataclass(frozen=True)
class ProviderCapabilities:
  """What one configured backend promises to support."""

  provider_id: str
  input_modalities: frozenset[str]
  output_modalities: frozenset[str]
  barge_in: bool = False
  native_audio: bool = False

  def __post_init__(self) -> None:
    if not self.provider_id:
      raise ValueError('provider_id must be non-empty')
    if not self.input_modalities or not self.output_modalities:
      raise ValueError('input_modalities and output_modalities are required')


@dataclass(frozen=True)
class ConversationNeeds:
  """Explicit product requirements; missing capabilities are never hidden."""

  input_modalities: frozenset[str] = frozenset({'text'})
  output_modalities: frozenset[str] = frozenset({'text'})
  require_barge_in: bool = False
  video_max_fps: float = 2.0
  video_max_age_ms: int = 2000

  def __post_init__(self) -> None:
    if self.video_max_fps <= 0 or self.video_max_fps > 60:
      raise ValueError('video_max_fps must be within (0, 60]')
    if self.video_max_age_ms <= 0:
      raise ValueError('video_max_age_ms must be positive')

  def validate(self, capability: ProviderCapabilities) -> None:
    missing_input = self.input_modalities - capability.input_modalities
    missing_output = self.output_modalities - capability.output_modalities
    if missing_input or missing_output:
      raise CapabilityError(
          f'{capability.provider_id}: unsupported modalities '
          f'input={sorted(missing_input)}, output={sorted(missing_output)}'
      )
    if self.require_barge_in and not capability.barge_in:
      raise CapabilityError(
          f'{capability.provider_id}: barge-in is not supported'
      )


@dataclass(frozen=True)
class SourceSettings:
  """Ingress overflow: only replaceable image/telemetry may be discarded."""

  name: str
  modality: Literal['audio', 'image', 'text', 'telemetry', 'control']
  capacity: int = 8
  overflow: Literal['block', 'drop_oldest'] = 'block'

  def __post_init__(self) -> None:
    if not self.name:
      raise ValueError('source name is required')
    if self.capacity < 1:
      raise ValueError('capacity must be >= 1')
    if self.overflow == 'drop_oldest' and self.modality not in (
        'image',
        'telemetry',
    ):
      raise ValueError('audio, text and control streams must not drop parts')
