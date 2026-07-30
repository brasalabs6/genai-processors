"""Safe local log discovery, reading and live distribution."""

import logging
from pathlib import Path
import queue
import re
import threading
from typing import Iterable


_SENSITIVE_ASSIGNMENT = re.compile(
    r'(?i)\b(api[_-]?key|authorization|token|prompt|objective|transcript|data)'
    r'\s*[:=]\s*([^\s,;]+)'
)


class InvalidLogIdError(ValueError):
  """Raised when a requested log is not an allowlisted local file."""


class SensitiveDataRedactor:
  """Redacts known secret values and sensitive structured fields."""

  def __init__(self, secret_values: Iterable[str] = ()):
    self._secret_values = tuple(value for value in secret_values if value)

  def redact(self, value: str) -> str:
    result = value
    for secret in self._secret_values:
      result = result.replace(secret, '[REDACTED]')
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f'{match.group(1)}=[REDACTED]', result
    )


class LogBus:
  """Non-blocking fan-out for already formatted and redacted log lines."""

  def __init__(self, max_queue_size: int = 1000):
    self._max_queue_size = max_queue_size
    self._subscribers: set[queue.Queue[str]] = set()
    self._lock = threading.Lock()

  def subscribe(self) -> queue.Queue[str]:
    subscriber: queue.Queue[str] = queue.Queue(self._max_queue_size)
    with self._lock:
      self._subscribers.add(subscriber)
    return subscriber

  def unsubscribe(self, subscriber: queue.Queue[str]) -> None:
    with self._lock:
      self._subscribers.discard(subscriber)

  def publish(self, line: str) -> None:
    with self._lock:
      subscribers = tuple(self._subscribers)
    for subscriber in subscribers:
      try:
        subscriber.put_nowait(line)
      except queue.Full:
        try:
          subscriber.get_nowait()
          subscriber.put_nowait(line)
        except (queue.Empty, queue.Full):
          pass


class BusHandler(logging.Handler):
  """Logging handler that redacts before publishing to the live bus."""

  def __init__(self, bus: LogBus, redactor: SensitiveDataRedactor):
    super().__init__()
    self._bus = bus
    self._redactor = redactor

  def emit(self, record: logging.LogRecord) -> None:
    try:
      self._bus.publish(self._redactor.redact(self.format(record)))
    except Exception:
      self.handleError(record)


class LogStore:
  """Lists and reads only Leonidas log files within one directory."""

  def __init__(self, root: Path, redactor: SensitiveDataRedactor | None = None):
    self._root = root.resolve()
    self._redactor = redactor or SensitiveDataRedactor()

  def list_files(self) -> list[dict[str, int | str]]:
    if not self._root.is_dir():
      return []
    files = sorted(
        (
            path
            for path in self._root.glob('leonidas-*.log*')
            if path.is_file() and path.resolve().parent == self._root
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            'id': path.name,
            'size': path.stat().st_size,
            'modified_ns': path.stat().st_mtime_ns,
        }
        for path in files
    ]

  def _resolve(self, log_id: str) -> Path:
    if Path(log_id).name != log_id:
      raise InvalidLogIdError('Invalid log id')
    known = {item['id'] for item in self.list_files()}
    if log_id not in known:
      raise InvalidLogIdError('Unknown log id')
    path = (self._root / log_id).resolve()
    if path.parent != self._root:
      raise InvalidLogIdError('Invalid log path')
    return path

  def read(
      self, log_id: str, *, cursor: int = 0, limit: int = 500
  ) -> dict[str, object]:
    if cursor < 0:
      raise InvalidLogIdError('Cursor must not be negative')
    limit = max(1, min(limit, 2000))
    path = self._resolve(log_id)
    lines: list[str] = []
    byte_count = 0
    with path.open('r', encoding='utf-8', errors='replace') as source:
      for index, line in enumerate(source):
        if index < cursor:
          continue
        encoded_size = len(line.encode('utf-8'))
        if lines and (
            len(lines) >= limit or byte_count + encoded_size > 524288
        ):
          break
        lines.append(self._redactor.redact(line.rstrip('\n')))
        byte_count += encoded_size
    return {
        'id': log_id,
        'cursor': cursor,
        'next_cursor': cursor + len(lines),
        'lines': lines,
    }
