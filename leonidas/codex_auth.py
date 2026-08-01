"""Safe discovery of local Codex authentication state."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
from typing import Any


class CodexAuthError(RuntimeError):
  """Authentication state is unavailable or cannot be safely consumed."""

  public_message = True


def _expired_known_tokens(tokens: Any) -> bool:
  if not isinstance(tokens, dict):
    return False
  expiries: list[float] = []
  for name in ('access_token', 'id_token'):
    token = tokens.get(name)
    if not isinstance(token, str) or token.count('.') != 2:
      continue
    try:
      payload = token.split('.')[1]
      payload += '=' * ((4 - len(payload) % 4) % 4)
      claims = json.loads(base64.urlsafe_b64decode(payload))
      if isinstance(claims.get('exp'), (int, float)):
        expiries.append(float(claims['exp']))
    except (ValueError, TypeError, json.JSONDecodeError):
      continue
  return bool(expiries) and all(expiry <= time.time() for expiry in expiries)


def auth_path() -> Path:
  configured = os.environ.get('LEONIDAS_CODEX_AUTH_FILE')
  if configured:
    return Path(configured).expanduser()
  codex_home = os.environ.get('CODEX_HOME')
  if codex_home:
    return Path(codex_home).expanduser() / 'auth.json'
  return Path.home() / '.codex' / 'auth.json'


def validate_auth_file(
    path: Path | None = None, *, require_api_key: bool = False
) -> Path:
  """Validates presence/shape while never returning or logging secret fields."""
  target = (path or auth_path()).expanduser().resolve()
  try:
    raw = target.read_text(encoding='utf-8')
    document: Any = json.loads(raw)
  except FileNotFoundError as exc:
    raise CodexAuthError(
        'Codex authentication file is missing; sign in with Codex first'
    ) from exc
  except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise CodexAuthError(
        'Codex authentication file is unreadable or invalid JSON'
    ) from exc
  if not isinstance(document, dict):
    raise CodexAuthError('Codex authentication file has an invalid shape')
  tokens = document.get('tokens')
  if _expired_known_tokens(tokens):
    raise CodexAuthError(
        'Codex authentication tokens are expired; sign in with Codex again'
    )
  if require_api_key and not isinstance(document.get('OPENAI_API_KEY'), str):
    raise CodexAuthError(
        'Codex realtime requires an OPENAI_API_KEY in auth.json; '
        'ChatGPT login tokens are not accepted by this backend'
    )
  if (
      not require_api_key
      and not isinstance(tokens, dict)
      and not document.get('OPENAI_API_KEY')
  ):
    raise CodexAuthError('Codex authentication file contains no usable login')
  return target


def subprocess_environment(
    path: Path | None = None,
    *,
    codex_home: Path | None = None,
    require_api_key: bool = True,
) -> dict[str, str]:
  """Returns a redaction-safe environment pointing Codex at auth.json."""
  target = path.expanduser() if path is not None else auth_path()
  validate_auth_file(target, require_api_key=require_api_key)
  document = json.loads(target.read_text(encoding='utf-8'))
  environment = os.environ.copy()
  # Keep the configured home path rather than resolving symlinks. This allows
  # tests and managed installations to expose auth.json without duplicating it.
  environment['CODEX_HOME'] = str((codex_home or target.parent).resolve())
  if isinstance(document.get('OPENAI_API_KEY'), str):
    environment['OPENAI_API_KEY'] = document['OPENAI_API_KEY']
  elif not require_api_key:
    environment.pop('OPENAI_API_KEY', None)
  return environment
