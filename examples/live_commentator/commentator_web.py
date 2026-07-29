# Copyright 2026 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Standalone HTTP and WebSocket launcher for the Live Commentator."""

import asyncio
import functools
from http import server as http_server
import os
from pathlib import Path
import threading
from typing import Any, Mapping

from absl import app
from absl import flags
from absl import logging
from genai_processors import processor
from genai_processors.dev import live_server

try:
  from . import commentator
except ImportError:
  import commentator  # type: ignore[no-redef]


_HOST = flags.DEFINE_string(
    'host',
    '127.0.0.1',
    'Local interface used by the standalone HTTP server.',
)
_WEB_PORT = flags.DEFINE_integer(
    'web_port',
    8000,
    'Port used by the standalone HTTP server.',
)
_WEBSOCKET_PORT = flags.DEFINE_integer(
    'websocket_port',
    8765,
    'Port used by the commentator WebSocket server.',
)
_WEB_ROOT = flags.DEFINE_string(
    'web_root',
    None,
    'Optional path to a built Vite directory. Defaults to webui/dist.',
)
_DEBUG = flags.DEFINE_bool(
    'debug',
    False,
    'Enable debug logging.',
)
_TRACE_DIR = flags.DEFINE_string(
    'trace_dir',
    None,
    'If set, enable tracing and write traces to this directory.',
)


class _StaticRequestHandler(http_server.SimpleHTTPRequestHandler):
  """Static handler with concise logging through absl."""

  def log_message(self, format_string: str, *args: Any) -> None:
    logging.info('WebUI: ' + format_string, *args)


class _ThreadingHTTPServer(http_server.ThreadingHTTPServer):
  daemon_threads = True
  allow_reuse_address = True


def default_web_root() -> Path:
  """Returns the default Vite build directory."""
  return (Path(__file__).parent / 'webui' / 'dist').resolve()


def validate_runtime(
    web_root: Path,
    environ: Mapping[str, str] = os.environ,
) -> None:
  """Validates required standalone runtime inputs."""
  if not environ.get('GOOGLE_API_KEY'):
    raise ValueError(
        'GOOGLE_API_KEY is required. Export it before starting the commentator.'
    )
  if not (web_root / 'index.html').is_file():
    raise FileNotFoundError(
        f'Vite build not found at {web_root}. Run `npm run build` from '
        '`examples/live_commentator/webui` first.'
    )


def create_static_server(
    web_root: Path,
    host: str,
    port: int,
) -> http_server.ThreadingHTTPServer:
  """Creates the standalone static HTTP server."""
  handler = functools.partial(
      _StaticRequestHandler,
      directory=str(web_root),
  )
  return _ThreadingHTTPServer((host, port), handler)


def create_live_commentator(
    config: dict[str, Any],
) -> processor.Processor:
  """Creates one Live Commentator pipeline for a WebSocket session."""
  chattiness = float(config.get('chattiness', 0.5))
  if not 0.0 <= chattiness <= 1.0:
    raise ValueError('chattiness must be between 0 and 1.')
  return commentator.create_live_commentator(
      api_key=os.environ['GOOGLE_API_KEY'],
      chattiness=chattiness,
      unsafe_string_list=None,
  )


async def run_standalone(
    *,
    host: str,
    web_port: int,
    websocket_port: int,
    web_root: Path,
    trace_dir: str | None = None,
) -> None:
  """Runs the static WebUI and commentator WebSocket server."""
  validate_runtime(web_root)
  static_server = create_static_server(web_root, host, web_port)
  static_thread = threading.Thread(
      target=static_server.serve_forever,
      name='live-commentator-http',
      daemon=True,
  )
  static_thread.start()
  ui_url = f'http://{host}:{web_port}/?wsPort={websocket_port}'
  print(f'Live Commentator WebUI: {ui_url}')
  print(f'Live Commentator WebSocket: ws://127.0.0.1:{websocket_port}')

  try:
    await live_server.run_server(
        create_live_commentator,
        port=websocket_port,
        trace_dir=trace_dir,
    )
  finally:
    static_server.shutdown()
    static_server.server_close()
    static_thread.join(timeout=2)


def main(argv: list[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Unexpected positional arguments.')
  if _DEBUG.value:
    logging.set_verbosity(logging.DEBUG)
  web_root = (
      Path(_WEB_ROOT.value).expanduser().resolve()
      if _WEB_ROOT.value
      else default_web_root()
  )
  try:
    asyncio.run(
        run_standalone(
            host=_HOST.value,
            web_port=_WEB_PORT.value,
            websocket_port=_WEBSOCKET_PORT.value,
            web_root=web_root,
            trace_dir=_TRACE_DIR.value,
        )
    )
  except KeyboardInterrupt:
    logging.info('Live Commentator stopped.')


if __name__ == '__main__':
  app.run(main)
