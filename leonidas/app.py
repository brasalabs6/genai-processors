"""Leonidas standalone application composition root."""

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys

from leonidas import api
from leonidas import config
from leonidas import http_server
from leonidas import logging_setup
from leonidas import runtime
from leonidas import telemetry
from leonidas import voice_preview
from leonidas import websocket_server
from leonidas.cascade import resources
from leonidas.pipelines import registry


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description='Run the Leonidas local agent')
  parser.add_argument('--web-port', type=int, default=8000)
  parser.add_argument('--websocket-port', type=int, default=8765)
  parser.add_argument('--web-root', type=Path, default=ROOT / 'webui' / 'dist')
  parser.add_argument('--log-dir', type=Path, default=REPOSITORY_ROOT / 'logs')
  parser.add_argument('--runtime-dir', type=Path, default=ROOT / '.runtime')
  parser.add_argument('--debug', action='store_true')
  return parser


def validate_runtime(
    web_root: Path,
    google_api_key: str | None,
    groq_api_key: str | None,
) -> None:
  if not google_api_key and not groq_api_key:
    raise ValueError('GOOGLE_API_KEY or GROQ_API_KEY is required')
  if not (web_root / 'index.html').is_file():
    raise FileNotFoundError(
        f'Vite build not found at {web_root}. Run `npm run build` from '
        '`leonidas/webui` first.'
    )


async def run(
    args: argparse.Namespace,
    google_api_key: str | None,
    groq_api_key: str | None,
) -> None:
  loop = asyncio.get_running_loop()
  metrics = telemetry.MetricsStore()
  log_path, logs, log_bus, handlers = logging_setup.install(
      args.log_dir.resolve(), debug=args.debug
  )
  store = config.ConfigStore(args.runtime_dir.resolve() / 'config.json')
  voices = {'leonidas': args.runtime_dir.resolve() / 'voices' / 'leonidas.wav'}
  cascade_resources = resources.CascadeResources(voices=voices)
  pipelines = registry.PipelineRegistry(
      google_api_key,
      groq_api_key,
      voices=voices,
      cascade_resources=cascade_resources,
      metrics=metrics,
  )
  manager = runtime.SessionManager(
      store,
      pipelines.create,
      metrics=metrics,
      pipeline_preparer=pipelines.prepare,
      requires_preparation=pipelines.requires_preparation,
  )
  preview = voice_preview.VoicePreviewRouter(
      google_api_key=google_api_key,
      voices=voices,
      cascade_resources=cascade_resources,
  )
  control_api = api.ControlApi(
      config_store=store,
      session=manager,
      metrics=metrics,
      logs=logs,
      voice_preview=preview,
      resources=cascade_resources.snapshot,
  )
  httpd = http_server.create_server(
      host='127.0.0.1',
      port=args.web_port,
      web_root=args.web_root.resolve(),
      control_api=control_api,
      event_loop=loop,
      log_bus=log_bus,
  )
  http_thread = http_server.serve_in_thread(httpd)
  print(f'Leonidas WebUI: http://127.0.0.1:{args.web_port}')
  print(
      'Leonidas WebSocket: ' f'ws://127.0.0.1:{args.websocket_port}/api/v1/live'
  )
  print(f'Leonidas log: {log_path}')
  logging.info(
      'Leonidas ready web_port=%d websocket_port=%d',
      args.web_port,
      args.websocket_port,
  )
  try:
    await websocket_server.run(
        manager,
        metrics,
        host='127.0.0.1',
        port=args.websocket_port,
        allowed_origins=websocket_server.local_origins(args.web_port),
        resources=cascade_resources,
    )
  finally:
    await manager.stop()
    await preview.close()
    await pipelines.close()
    await cascade_resources.close()
    httpd.shutdown()
    httpd.server_close()
    http_thread.join(timeout=2)
    for handler in handlers:
      logging.getLogger().removeHandler(handler)
      handler.close()


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  google_api_key = os.environ.get('GOOGLE_API_KEY')
  groq_api_key = os.environ.get('GROQ_API_KEY')
  try:
    validate_runtime(args.web_root.resolve(), google_api_key, groq_api_key)
    asyncio.run(run(args, google_api_key, groq_api_key))
  except KeyboardInterrupt:
    return 130
  except (ValueError, FileNotFoundError) as exc:
    print(f'Leonidas startup error: {exc}', file=sys.stderr)
    return 2
  return 0
