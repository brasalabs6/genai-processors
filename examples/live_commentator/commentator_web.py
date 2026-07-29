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
import datetime
import functools
from http import server as http_server
import logging as std_logging
from logging import handlers as logging_handlers
import os
from pathlib import Path
import platform
import re
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
_LOG_DIR = flags.DEFINE_string(
    'commentator_log_dir',
    None,
    'Directory for diagnostic log files. Defaults to <repository>/logs.',
)

_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5
_SENSITIVE_ENV_MARKERS = ('API_KEY', 'PASSWORD', 'SECRET', 'TOKEN')


class _SensitiveDataRedactor:
  """Redacts credentials from rendered diagnostic messages."""

  def __init__(self, environ: Mapping[str, str]):
    self._secret_values = tuple(
        sorted(
            {
                value
                for name, value in environ.items()
                if value
                and len(value) >= 8
                and any(
                    marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS
                )
            },
            key=len,
            reverse=True,
        )
    )

  def redact(self, value: str) -> str:
    value = re.sub(
        r'(?i)(x-goog-api-key:\s*)\S+',
        r'\1[REDACTED]',
        value,
    )
    value = re.sub(
        r'(?i)(authorization:\s*(?:bearer\s+)?)\S+',
        r'\1[REDACTED]',
        value,
    )
    value = re.sub(r'\bAIza[A-Za-z0-9_-]{20,}\b', '[REDACTED]', value)
    value = re.sub(r'\bAQ\.[A-Za-z0-9_-]{20,}\b', '[REDACTED]', value)
    for secret in self._secret_values:
      value = value.replace(secret, '[REDACTED]')
    return value


class _SafeDiagnosticFilter(std_logging.Filter):
  """Suppresses payload-level debug logs and redacts record messages."""

  def __init__(self, redactor: _SensitiveDataRedactor):
    super().__init__()
    self._redactor = redactor

  def filter(self, record: std_logging.LogRecord) -> bool:
    if record.levelno < std_logging.WARNING:
      if record.name.startswith('websockets.'):
        return False
      if Path(record.pathname).name == 'live_model.py':
        return False
    if (
        record.levelno < std_logging.INFO
        and Path(record.pathname).name == 'commentator.py'
        and 'non media part:' in record.getMessage()
    ):
      return False
    record.msg = self._redactor.redact(record.getMessage())
    record.args = ()
    return True


class _RedactingFormatter(std_logging.Formatter):
  """Applies credential redaction after formatting exceptions and stack info."""

  def __init__(self, redactor: _SensitiveDataRedactor):
    super().__init__(
        (
            '%(asctime)s.%(msecs)03d %(levelname)s %(name)s '
            'pid=%(process)d thread=%(threadName)s %(message)s'
        ),
        datefmt='%Y-%m-%dT%H:%M:%S',
    )
    self._redactor = redactor

  def format(self, record: std_logging.LogRecord) -> str:
    return self._redactor.redact(super().format(record))


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


def default_log_dir() -> Path:
  """Returns the repository-local diagnostic log directory."""
  return Path(__file__).parents[2] / 'logs'


def install_file_logging(
    log_dir: Path,
    *,
    debug: bool,
) -> tuple[Path, logging_handlers.RotatingFileHandler]:
  """Installs a rotating diagnostic file handler on the root logger."""
  log_dir.mkdir(parents=True, exist_ok=True)
  timestamp = datetime.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
  log_path = log_dir / f'live-commentator-{timestamp}-{os.getpid()}.log'
  handler = logging_handlers.RotatingFileHandler(
      log_path,
      maxBytes=_LOG_MAX_BYTES,
      backupCount=_LOG_BACKUP_COUNT,
      encoding='utf-8',
  )
  handler.setLevel(std_logging.DEBUG if debug else std_logging.INFO)
  redactor = _SensitiveDataRedactor(os.environ)
  safe_filter = _SafeDiagnosticFilter(redactor)
  handler.addFilter(safe_filter)
  handler.setFormatter(_RedactingFormatter(redactor))
  root_logger = std_logging.getLogger()
  for existing_handler in root_logger.handlers:
    existing_handler.addFilter(safe_filter)
  root_logger.addHandler(handler)
  std_logging.captureWarnings(True)
  return log_path, handler


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
  live_model_name = str(config.get('live_model', commentator.MODEL_LIVE))
  commentator.resolve_live_model_profile(live_model_name)
  return commentator.create_live_commentator(
      api_key=os.environ['GOOGLE_API_KEY'],
      chattiness=chattiness,
      unsafe_string_list=None,
      live_model_name=live_model_name,
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
  logging.info(
      'Standalone services ready: web_ui=%s websocket_port=%d web_root=%s',
      ui_url,
      websocket_port,
      web_root,
  )

  try:
    await live_server.run_server(
        create_live_commentator,
        port=websocket_port,
        trace_dir=trace_dir,
    )
  finally:
    logging.info('Shutting down standalone services.')
    static_server.shutdown()
    static_server.server_close()
    static_thread.join(timeout=2)


def main(argv: list[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Unexpected positional arguments.')
  logging.set_verbosity(logging.DEBUG if _DEBUG.value else logging.INFO)
  web_root = (
      Path(_WEB_ROOT.value).expanduser().resolve()
      if _WEB_ROOT.value
      else default_web_root()
  )
  log_dir = (
      Path(_LOG_DIR.value).expanduser().resolve()
      if _LOG_DIR.value
      else default_log_dir()
  )
  log_path, file_handler = install_file_logging(
      log_dir,
      debug=_DEBUG.value,
  )
  print(f'Live Commentator log: {log_path}')
  logging.info(
      (
          'Starting Live Commentator: model_live=%s model_detection=%s '
          'python=%s platform=%s debug=%s'
      ),
      commentator.MODEL_LIVE,
      commentator.MODEL_DETECTION,
      platform.python_version(),
      platform.platform(),
      _DEBUG.value,
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
  except Exception:
    logging.exception('Live Commentator terminated with an unhandled error.')
    raise
  finally:
    file_handler.flush()
    std_logging.getLogger().removeHandler(file_handler)
    file_handler.close()


if __name__ == '__main__':
  app.run(main)
