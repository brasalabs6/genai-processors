"""Opt-in real Codex app-server authentication and realtime smoke test."""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from leonidas import codex_app_server
from leonidas import codex_auth
from leonidas.pipelines import codex_realtime


async def run(version: str) -> None:
  started = time.perf_counter()
  auth_file = codex_auth.validate_auth_file()
  client, cleanup = await codex_realtime._open_client()
  try:
    await client.start_realtime(
        objective='Responda brevemente em português.',
        model='gpt-realtime-1.5',
        version=version,
    )
    await client.append_text('Diga apenas: teste concluído.')
    await client.stop_realtime()
  finally:
    await cleanup()
  print(
      'codex_smoke_ok=true'
      f' auth_file={auth_file}'
      f' version={version}'
      f' elapsed_seconds={time.perf_counter() - started:.2f}'
  )


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--version',
      default=os.environ.get('LEONIDAS_CODEX_REALTIME_VERSION', 'v3'),
      choices=('v1', 'v2', 'v3'),
  )
  args = parser.parse_args()
  if os.environ.get('LEONIDAS_RUN_CODEX_E2E') != '1':
    print('codex_smoke_skipped=true set LEONIDAS_RUN_CODEX_E2E=1 to run')
    return 0
  try:
    asyncio.run(run(args.version))
  except (
      codex_auth.CodexAuthError,
      codex_app_server.CodexProtocolError,
  ) as exc:
    print(f'codex_smoke_failed=true error_type={type(exc).__name__}')
    return 2
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
