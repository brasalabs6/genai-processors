"""Typed Leonidas configuration and local persistence."""

import dataclasses
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

from leonidas import capabilities


DEFAULT_OBJECTIVE = (
    'Converse em português, ajude o usuário e use o que estiver visível na '
    'tela como contexto quando for relevante.'
)


class ConfigValidationError(ValueError):
  """Raised when an AgentConfig violates its schema or capabilities."""


class RevisionConflictError(ValueError):
  """Raised when a draft update is based on a stale revision."""


@dataclasses.dataclass(frozen=True)
class MediaConfig:
  frame_interval_ms: int = 1000
  max_width: int = 1280
  max_height: int = 720
  jpeg_quality: float = 0.75
  model_resolution: str = 'medium'


@dataclasses.dataclass(frozen=True)
class VadConfig:
  start_sensitivity: str | None = None
  end_sensitivity: str | None = None
  prefix_padding_ms: int | None = None
  silence_duration_ms: int | None = None


@dataclasses.dataclass(frozen=True)
class GenerationConfig:
  temperature: float | None = None
  thinking_level: str | None = None
  thinking_budget: int | None = None
  context_trigger_tokens: int | None = None
  context_target_tokens: int | None = None


@dataclasses.dataclass(frozen=True)
class AgentConfig:
  schema_version: int = 1
  pipeline_id: str = 'gemini_live'
  model_id: str = capabilities.DEFAULT_MODEL
  voice_name: str | None = None
  objective: str = DEFAULT_OBJECTIVE
  chattiness: float = 0.5
  performance_preset: str = 'balanced'
  media: MediaConfig = dataclasses.field(default_factory=MediaConfig)
  vad: VadConfig = dataclasses.field(default_factory=VadConfig)
  generation: GenerationConfig = dataclasses.field(
      default_factory=GenerationConfig
  )

  @classmethod
  def default(cls) -> 'AgentConfig':
    return cls()

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> 'AgentConfig':
    allowed = {field.name for field in dataclasses.fields(cls)}
    unknown = set(value) - allowed
    if unknown:
      raise ConfigValidationError(
          f'Unknown configuration fields: {sorted(unknown)}'
      )
    try:
      result = cls(
          schema_version=int(value.get('schema_version', 1)),
          pipeline_id=str(value.get('pipeline_id', 'gemini_live')),
          model_id=str(value.get('model_id', capabilities.DEFAULT_MODEL)),
          voice_name=value.get('voice_name'),
          objective=str(value.get('objective', DEFAULT_OBJECTIVE)),
          chattiness=float(value.get('chattiness', 0.5)),
          performance_preset=str(value.get('performance_preset', 'balanced')),
          media=MediaConfig(**dict(value.get('media', {}))),
          vad=VadConfig(**dict(value.get('vad', {}))),
          generation=GenerationConfig(**dict(value.get('generation', {}))),
      )
    except (TypeError, ValueError) as exc:
      raise ConfigValidationError(str(exc)) from exc
    result.validate()
    return result

  def to_dict(self) -> dict[str, Any]:
    return dataclasses.asdict(self)

  def with_updates(self, updates: Mapping[str, Any]) -> 'AgentConfig':
    merged = self.to_dict()
    for key, value in updates.items():
      if key in ('media', 'vad', 'generation') and isinstance(value, Mapping):
        merged[key].update(value)
      else:
        merged[key] = value
    if 'model_id' in updates and updates['model_id'] != self.model_id:
      profile = capabilities.resolve_model(str(updates['model_id']))
      if profile.thinking_field == 'thinking_level':
        merged['generation']['thinking_budget'] = None
      else:
        merged['generation']['thinking_level'] = None
    return self.from_dict(merged)

  def with_preset(self, preset: str) -> 'AgentConfig':
    if preset == 'balanced':
      media = MediaConfig()
      generation = GenerationConfig()
      vad = VadConfig()
    elif preset == 'low_latency':
      media = MediaConfig(500, 960, 540, 0.60, 'low')
      vad = VadConfig(end_sensitivity='high', silence_duration_ms=350)
      generation = (
          GenerationConfig(thinking_level='minimal')
          if self.model_id == capabilities.MODEL_LIVE_3_1
          else GenerationConfig(thinking_budget=0)
      )
    elif preset == 'quality':
      media = MediaConfig(1000, 1280, 720, 0.85, 'high')
      vad = VadConfig(end_sensitivity='low', silence_duration_ms=700)
      generation = (
          GenerationConfig(thinking_level='medium')
          if self.model_id == capabilities.MODEL_LIVE_3_1
          else GenerationConfig(thinking_budget=512)
      )
    else:
      raise ConfigValidationError(f'Unknown performance_preset: {preset!r}')
    result = dataclasses.replace(
        self,
        performance_preset=preset,
        media=media,
        vad=vad,
        generation=generation,
    )
    result.validate()
    return result

  def validate(self) -> None:
    if self.schema_version != 1:
      raise ConfigValidationError('schema_version must be 1')
    if self.pipeline_id != 'gemini_live':
      raise ConfigValidationError('pipeline_id must be gemini_live')
    try:
      profile = capabilities.resolve_model(self.model_id)
    except ValueError as exc:
      raise ConfigValidationError(str(exc)) from exc
    if (
        self.voice_name is not None
        and self.voice_name not in capabilities.VOICES
    ):
      raise ConfigValidationError('voice_name is not supported')
    if not 1 <= len(self.objective.strip()) <= 12000:
      raise ConfigValidationError(
          'objective must contain 1 to 12000 characters'
      )
    if not 0 <= self.chattiness <= 1:
      raise ConfigValidationError('chattiness must be between 0 and 1')
    if self.performance_preset not in ('low_latency', 'balanced', 'quality'):
      raise ConfigValidationError('performance_preset is invalid')
    if not 250 <= self.media.frame_interval_ms <= 10000:
      raise ConfigValidationError('media.frame_interval_ms is out of range')
    if not 160 <= self.media.max_width <= 1920:
      raise ConfigValidationError('media.max_width is out of range')
    if not 120 <= self.media.max_height <= 1080:
      raise ConfigValidationError('media.max_height is out of range')
    if not 0.3 <= self.media.jpeg_quality <= 0.95:
      raise ConfigValidationError('media.jpeg_quality is out of range')
    if self.media.model_resolution not in ('low', 'medium', 'high'):
      raise ConfigValidationError('media.model_resolution is invalid')
    if self.generation.temperature is not None and not (
        0 <= self.generation.temperature <= 2
    ):
      raise ConfigValidationError('generation.temperature is out of range')
    if profile.thinking_field == 'thinking_budget':
      if self.generation.thinking_level is not None:
        raise ConfigValidationError(
            'generation.thinking_level is unsupported by this model'
        )
    elif self.generation.thinking_budget is not None:
      raise ConfigValidationError(
          'generation.thinking_budget is unsupported by this model'
      )
    if self.generation.thinking_level not in (
        None,
        'minimal',
        'low',
        'medium',
        'high',
    ):
      raise ConfigValidationError('generation.thinking_level is invalid')
    for name in ('prefix_padding_ms', 'silence_duration_ms'):
      value = getattr(self.vad, name)
      if value is not None and not 0 <= value <= 10000:
        raise ConfigValidationError(f'vad.{name} is out of range')
    for name in ('start_sensitivity', 'end_sensitivity'):
      value = getattr(self.vad, name)
      if value not in (None, 'high', 'low'):
        raise ConfigValidationError(f'vad.{name} is invalid')
    trigger = self.generation.context_trigger_tokens
    target = self.generation.context_target_tokens
    if trigger is not None and trigger <= 0:
      raise ConfigValidationError('context_trigger_tokens must be positive')
    if target is not None and target <= 0:
      raise ConfigValidationError('context_target_tokens must be positive')
    if trigger is not None and target is not None and target >= trigger:
      raise ConfigValidationError(
          'context_target_tokens must be smaller than context_trigger_tokens'
      )


@dataclasses.dataclass(frozen=True)
class ConfigSnapshot:
  active: AgentConfig
  draft: AgentConfig
  revision: int
  dirty_fields: tuple[str, ...]

  def to_dict(self) -> dict[str, Any]:
    return {
        'active': self.active.to_dict(),
        'draft': self.draft.to_dict(),
        'revision': self.revision,
        'dirty_fields': list(self.dirty_fields),
    }


def _dirty_fields(active: AgentConfig, draft: AgentConfig) -> tuple[str, ...]:
  active_dict = active.to_dict()
  draft_dict = draft.to_dict()
  return tuple(
      key for key in active_dict if active_dict[key] != draft_dict[key]
  )


class ConfigStore:
  """Thread-safe revisioned store with atomic disk persistence."""

  def __init__(self, path: Path):
    self._path = path
    self._lock = threading.RLock()
    self._active = AgentConfig.default()
    self._draft = self._active
    self._revision = 0
    self._load()

  def _load(self) -> None:
    if not self._path.is_file():
      return
    try:
      payload = json.loads(self._path.read_text(encoding='utf-8'))
      self._active = AgentConfig.from_dict(payload['active'])
      self._draft = AgentConfig.from_dict(payload['draft'])
      self._revision = int(payload['revision'])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
      raise ConfigValidationError(
          f'Invalid persisted configuration: {exc}'
      ) from exc

  def _persist(self) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = self._path.with_suffix('.tmp')
    payload = {
        'active': self._active.to_dict(),
        'draft': self._draft.to_dict(),
        'revision': self._revision,
    }
    with temp_path.open('w', encoding='utf-8') as output:
      json.dump(payload, output, ensure_ascii=False, indent=2)
      output.flush()
      os.fsync(output.fileno())
    os.replace(temp_path, self._path)

  def snapshot(self) -> ConfigSnapshot:
    with self._lock:
      return ConfigSnapshot(
          self._active,
          self._draft,
          self._revision,
          _dirty_fields(self._active, self._draft),
      )

  def update_draft(
      self, updates: Mapping[str, Any], *, expected_revision: int
  ) -> ConfigSnapshot:
    with self._lock:
      if expected_revision != self._revision:
        raise RevisionConflictError(
            f'Expected revision {expected_revision}, current {self._revision}'
        )
      remaining = dict(updates)
      if 'model_id' in remaining:
        self._draft = self._draft.with_updates(
            {'model_id': remaining.pop('model_id')}
        )
      if 'performance_preset' in remaining:
        self._draft = self._draft.with_preset(
            str(remaining.pop('performance_preset'))
        )
      if remaining:
        self._draft = self._draft.with_updates(remaining)
      self._revision += 1
      self._persist()
      return self.snapshot()

  def promote_draft(self) -> tuple[AgentConfig, AgentConfig]:
    with self._lock:
      previous = self._active
      self._active = self._draft
      self._revision += 1
      self._persist()
      return previous, self._active

  def restore_active(self, previous: AgentConfig) -> ConfigSnapshot:
    with self._lock:
      self._active = previous
      self._draft = previous
      self._revision += 1
      self._persist()
      return self.snapshot()
