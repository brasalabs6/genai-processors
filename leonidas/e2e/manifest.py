"""Versioned empirical scenario manifest."""

import dataclasses
import json
from pathlib import Path
import re
from typing import Any, Mapping


_SAFE_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,79}$')


@dataclasses.dataclass(frozen=True)
class Scenario:
  id: str
  description: str
  image_prompt: str
  audio_script: str
  expected_terms: tuple[str, ...]
  timeout_seconds: float
  minimum_audio_seconds: float

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> 'Scenario':
    scenario_id = str(value['id'])
    if not _SAFE_ID.fullmatch(scenario_id):
      raise ValueError('scenario id must be path-safe')
    result = cls(
        id=scenario_id,
        description=str(value['description']).strip(),
        image_prompt=str(value['image_prompt']).strip(),
        audio_script=str(value['audio_script']).strip(),
        expected_terms=tuple(
            str(term).casefold() for term in value['expected_terms']
        ),
        timeout_seconds=float(value['timeout_seconds']),
        minimum_audio_seconds=float(value['minimum_audio_seconds']),
    )
    if (
        not result.description
        or not result.image_prompt
        or not result.audio_script
    ):
      raise ValueError('scenario text fields must not be empty')
    if not 20 <= result.timeout_seconds <= 120:
      raise ValueError('timeout_seconds must be between 20 and 120')
    if not 0.25 <= result.minimum_audio_seconds <= 10:
      raise ValueError('minimum_audio_seconds is out of range')
    return result


def load(path: Path) -> tuple[Scenario, ...]:
  payload = json.loads(path.read_text(encoding='utf-8'))
  if payload.get('schema_version') != 1:
    raise ValueError('Unsupported scenario schema_version')
  scenarios = tuple(Scenario.from_dict(item) for item in payload['scenarios'])
  ids = [item.id for item in scenarios]
  if not scenarios or len(ids) != len(set(ids)):
    raise ValueError('Scenario ids must be non-empty and unique')
  return scenarios
