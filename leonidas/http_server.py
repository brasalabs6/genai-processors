"""Threaded localhost HTTP adapter for the control API and Vite build."""

import asyncio
from http import server
import json
import logging
from pathlib import Path
import queue
import threading
from typing import Any
from urllib import parse

from leonidas import api
from leonidas import log_store


_ALLOWED_ORIGINS = {
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1:5173',
    'http://localhost:5173',
}


class _ThreadingHTTPServer(server.ThreadingHTTPServer):
  daemon_threads = True
  allow_reuse_address = True


def create_server(
    *,
    host: str,
    port: int,
    web_root: Path,
    control_api: api.ControlApi,
    event_loop: asyncio.AbstractEventLoop,
    log_bus: log_store.LogBus,
) -> server.ThreadingHTTPServer:
  """Creates an HTTP server; the caller owns its serving thread."""
  if host != '127.0.0.1':
    raise ValueError('Leonidas v1 only binds to 127.0.0.1')
  root = web_root.resolve()

  class Handler(server.SimpleHTTPRequestHandler):

    def __init__(self, *args: Any, **kwargs: Any):
      super().__init__(*args, directory=str(root), **kwargs)

    def log_message(self, format_string: str, *args: Any) -> None:
      # Access logs deliberately omit query strings and request bodies.
      del format_string, args
      logging.info(
          'HTTP %s %s', self.command, self.path.split('?', maxsplit=1)[0]
      )

    def _origin_allowed(self) -> bool:
      origin = self.headers.get('Origin')
      return origin is None or origin in _ALLOWED_ORIGINS

    def _send(self, response: api.ApiResponse) -> None:
      body = (
          response.body.encode('utf-8')
          if isinstance(response.body, str)
          else response.body
      )
      self.send_response(response.status)
      self.send_header('Content-Type', response.content_type)
      self.send_header('Content-Length', str(len(body)))
      self.send_header('Cache-Control', 'no-store')
      for name, value in response.headers.items():
        self.send_header(name, value)
      self.end_headers()
      self.wfile.write(body)

    def _dispatch(self, body: dict[str, Any] | None = None) -> None:
      if not self._origin_allowed():
        self._send(api._error(403, 'origin_forbidden', 'Origin not allowed'))
        return
      future = asyncio.run_coroutine_threadsafe(
          control_api.dispatch(self.command, self.path, body), event_loop
      )
      try:
        response = future.result(timeout=20)
      except TimeoutError:
        future.cancel()
        response = api._error(504, 'request_timeout', 'Request timed out')
      except Exception:
        logging.exception('Unhandled control API error')
        response = api._error(500, 'internal_error', 'Internal server error')
      self._send(response)

    def _json_body(self) -> dict[str, Any] | None:
      try:
        size = int(self.headers.get('Content-Length', '0'))
      except ValueError:
        return None
      if size < 0 or size > 1024 * 1024:
        return None
      try:
        payload = json.loads(self.rfile.read(size) or b'{}')
      except json.JSONDecodeError:
        return None
      return payload if isinstance(payload, dict) else None

    def do_GET(self) -> None:  # pylint: disable=invalid-name
      path = parse.urlsplit(self.path).path
      if path == '/api/v1/logs/stream':
        self._serve_log_stream()
      elif path.startswith('/api/v1/'):
        self._dispatch()
      else:
        if path != '/' and not (root / path.lstrip('/')).is_file():
          self.path = '/index.html'
        super().do_GET()

    def do_POST(self) -> None:  # pylint: disable=invalid-name
      body = self._json_body()
      if body is None:
        self._send(api._error(400, 'invalid_json', 'Invalid JSON body'))
        return
      self._dispatch(body)

    def do_PUT(self) -> None:  # pylint: disable=invalid-name
      self.do_POST()

    def _serve_log_stream(self) -> None:
      if not self._origin_allowed():
        self._send(api._error(403, 'origin_forbidden', 'Origin not allowed'))
        return
      subscriber = log_bus.subscribe()
      self.send_response(200)
      self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
      self.send_header('Cache-Control', 'no-store')
      self.send_header('Connection', 'keep-alive')
      self.end_headers()
      try:
        while True:
          try:
            line = subscriber.get(timeout=15)
            payload = json.dumps({'line': line}, ensure_ascii=False)
            self.wfile.write(f'data: {payload}\n\n'.encode('utf-8'))
          except queue.Empty:
            self.wfile.write(b': keepalive\n\n')
          self.wfile.flush()
      except (BrokenPipeError, ConnectionResetError):
        pass
      finally:
        log_bus.unsubscribe(subscriber)

  return _ThreadingHTTPServer((host, port), Handler)


def serve_in_thread(
    httpd: server.ThreadingHTTPServer,
) -> threading.Thread:
  thread = threading.Thread(
      target=httpd.serve_forever,
      name='leonidas-http',
      daemon=True,
  )
  thread.start()
  return thread
