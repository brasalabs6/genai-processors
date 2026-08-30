"""Opt-in real Codex app-server text-turn smoke test."""

from __future__ import annotations

import asyncio
import argparse
import os
import time

from leonidas import codex_app_server
from leonidas import codex_auth
from leonidas.pipelines import codex_realtime


async def run(turns: int) -> None:
  if turns < 1:
    raise ValueError('turns must be positive')
  started = time.perf_counter()
  client, cleanup = await codex_realtime._open_text_client()
  try:
    await client.start_thread('Responda brevemente em português.')
    responses = []
    for index in range(turns):
      responses.append(
          await client.respond(f'Responda apenas com teste {index + 1}.')
      )
  finally:
    await cleanup()
  if any(not response.strip() for response in responses):
    raise codex_app_server.CodexProtocolError(
        'Codex text turn returned an empty response'
    )
  print(
      'codex_text_smoke_ok=true'
      f' turns={turns} response_chars={sum(map(len, responses))}'
      f' elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--turns',
      type=int,
      default=int(os.environ.get('LEONIDAS_CODEX_TEXT_TURNS', '2')),
  )
  if os.environ.get('LEONIDAS_RUN_CODEX_TEXT_E2E') != '1':
    print(
        'codex_text_smoke_skipped=true '
        'set LEONIDAS_RUN_CODEX_TEXT_E2E=1 to run'
    )
    return 0
  try:
    asyncio.run(run(parser.parse_args().turns))
  except (
      codex_auth.CodexAuthError,
      codex_app_server.CodexProtocolError,
  ) as exc:
    print(f'codex_text_smoke_failed=true error_type={type(exc).__name__}')
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
