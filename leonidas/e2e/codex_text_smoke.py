"""Opt-in real Codex app-server text-turn smoke test."""

from __future__ import annotations

import asyncio
import os
import time

from leonidas import codex_app_server
from leonidas import codex_auth
from leonidas.pipelines import codex_realtime


async def run() -> None:
  started = time.perf_counter()
  client, cleanup = await codex_realtime._open_text_client()
  try:
    await client.start_thread('Responda brevemente em português.')
    response = await client.respond('Responda apenas com a palavra teste.')
  finally:
    await cleanup()
  if not response.strip():
    raise codex_app_server.CodexProtocolError(
        'Codex text turn returned an empty response'
    )
  print(
      'codex_text_smoke_ok=true'
      f' response_chars={len(response)}'
      f' elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main() -> int:
  if os.environ.get('LEONIDAS_RUN_CODEX_TEXT_E2E') != '1':
    print(
        'codex_text_smoke_skipped=true '
        'set LEONIDAS_RUN_CODEX_TEXT_E2E=1 to run'
    )
    return 0
  try:
    asyncio.run(run())
  except (
      codex_auth.CodexAuthError,
      codex_app_server.CodexProtocolError,
  ) as exc:
    print(f'codex_text_smoke_failed=true error_type={type(exc).__name__}')
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
