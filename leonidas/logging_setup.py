"""Rotating and live-safe logging setup for Leonidas."""

import datetime
import logging
from logging import handlers
import os
from pathlib import Path
from typing import Mapping

from leonidas import log_store


class _RedactingFormatter(logging.Formatter):

  def __init__(self, redactor: log_store.SensitiveDataRedactor):
    super().__init__(
        '%(asctime)s.%(msecs)03d %(levelname)s %(name)s '
        'pid=%(process)d thread=%(threadName)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
    )
    self._redactor = redactor

  def format(self, record: logging.LogRecord) -> str:
    return self._redactor.redact(super().format(record))


def install(
    log_dir: Path,
    *,
    debug: bool,
    environ: Mapping[str, str] = os.environ,
) -> tuple[Path, log_store.LogStore, log_store.LogBus, list[logging.Handler]]:
  """Installs file and live handlers and returns their owned resources."""
  log_dir.mkdir(parents=True, exist_ok=True)
  timestamp = datetime.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
  path = log_dir / f'leonidas-{timestamp}-{os.getpid()}.log'
  secrets = [
      value
      for key, value in environ.items()
      if any(marker in key.upper() for marker in ('KEY', 'TOKEN', 'SECRET'))
  ]
  redactor = log_store.SensitiveDataRedactor(secrets)
  formatter = _RedactingFormatter(redactor)
  file_handler = handlers.RotatingFileHandler(
      path,
      maxBytes=10 * 1024 * 1024,
      backupCount=5,
      encoding='utf-8',
  )
  file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
  file_handler.setFormatter(formatter)
  bus = log_store.LogBus()
  bus_handler = log_store.BusHandler(bus, redactor)
  bus_handler.setLevel(logging.DEBUG if debug else logging.INFO)
  bus_handler.setFormatter(formatter)
  root = logging.getLogger()
  root.setLevel(logging.DEBUG if debug else logging.INFO)
  root.addHandler(file_handler)
  root.addHandler(bus_handler)
  # These libraries can emit raw WebSocket frames at DEBUG level.
  logging.getLogger('websockets').setLevel(logging.INFO)
  logging.getLogger('google.genai.live').setLevel(logging.INFO)
  logging.captureWarnings(True)
  return (
      path,
      log_store.LogStore(log_dir, redactor),
      bus,
      [
          file_handler,
          bus_handler,
      ],
  )
