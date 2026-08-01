"""Composition for the local Codex app-server realtime backend."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from genai_processors import processor

from leonidas import codex_app_server
from leonidas import codex_auth
from leonidas import config


async def _open_client() -> tuple[
    codex_app_server.CodexRealtimeClient,
    Any,
]:
  command = os.environ.get('LEONIDAS_CODEX_BIN', 'codex')
  environment = codex_auth.subprocess_environment()
  process = await asyncio.create_subprocess_exec(
      command,
      'app-server',
      '--listen',
      'stdio://',
      '-c',
      'features.realtime_conversation=true',
      stdin=asyncio.subprocess.PIPE,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.DEVNULL,
      env=environment,
  )
  if process.stdin is None or process.stdout is None:
    process.kill()
    await process.wait()
    raise RuntimeError('Codex app-server did not expose stdio pipes')

  async def send_line(line: str) -> None:
    process.stdin.write((line + '\n').encode('utf-8'))
    await process.stdin.drain()

  async def receive_line() -> str | None:
    line = await process.stdout.readline()
    if not line:
      return None
    return line.decode('utf-8')

  rpc = codex_app_server.JsonlRpcClient(send_line, receive_line)
  client = codex_app_server.CodexRealtimeClient(
      rpc, audio_mimetype='audio/pcm;rate=24000'
  )
  await client.initialize(client_name='leonidas', client_version='0.1.0')

  async def cleanup() -> None:
    await client.close()
    if process.returncode is None:
      process.terminate()
      try:
        await asyncio.wait_for(process.wait(), timeout=2)
      except asyncio.TimeoutError:
        process.kill()
        await process.wait()

  return client, cleanup


def create(agent_config: config.AgentConfig) -> processor.Processor:
  agent_config.validate()
  if agent_config.pipeline_id != 'codex_realtime':
    raise ValueError('Codex pipeline received an incompatible configuration')
  return codex_app_server.CodexRealtimeProcessor(
      objective=agent_config.objective,
      model=agent_config.model_id,
      voice=agent_config.voice_name,
      version=os.environ.get('LEONIDAS_CODEX_REALTIME_VERSION', 'v3'),
      client_factory=_open_client,
  )
