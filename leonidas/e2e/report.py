"""Redacted machine and human empirical reports."""

import json
from pathlib import Path
from typing import Iterable

from leonidas.e2e import runner


def write(
    root: Path,
    results: Iterable[runner.EmpiricalResult],
    *,
    run_id: str,
) -> tuple[Path, Path]:
  root.mkdir(parents=True, exist_ok=True)
  values = list(results)
  payload = {
      'schema_version': 1,
      'run_id': run_id,
      'passed': bool(values) and all(value.passed for value in values),
      'results': [value.to_dict() for value in values],
  }
  json_path = root / f'{run_id}.json'
  markdown_path = root / f'{run_id}.md'
  json_path.write_text(
      json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
  )
  lines = [
      f'# Leonidas empirical run {run_id}',
      '',
      f"Overall: {'PASS' if payload['passed'] else 'FAIL'}",
      '',
      '| Model | Scenario | Result | Audio | TTFA | Error |',
      '|---|---|---|---:|---:|---|',
  ]
  for value in values:
    ttfa = 'n/a' if value.ttfa_ms is None else f'{value.ttfa_ms:.0f} ms'
    lines.append(
        f'| {value.model_id} | {value.scenario_id} | '
        f"{'PASS' if value.passed else 'FAIL'} | "
        f'{value.audio_seconds:.2f} s | {ttfa} | '
        f'{value.error_code or "—"} |'
    )
  markdown_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
  return json_path, markdown_path
