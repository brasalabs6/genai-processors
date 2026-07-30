"""Content-free runtime metrics for Leonidas."""

import collections
import math
import statistics
import threading
import time
from typing import Any
from typing import Callable


class MetricsStore:
  """Keeps bounded metric samples and counters in memory."""

  def __init__(self, max_samples: int = 100):
    self._max_samples = max_samples
    self._samples: dict[str, collections.deque[float]] = {}
    self._counters: collections.Counter[str] = collections.Counter()
    self._lock = threading.Lock()

  def observe(self, name: str, value: float) -> None:
    with self._lock:
      self._samples.setdefault(
          name, collections.deque(maxlen=self._max_samples)
      ).append(float(value))

  def increment(self, name: str, amount: int = 1) -> None:
    with self._lock:
      self._counters[name] += amount

  @staticmethod
  def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]

  def snapshot(self) -> dict[str, Any]:
    with self._lock:
      metrics = {}
      for name, samples in self._samples.items():
        values = list(samples)
        metrics[name] = {
            'count': len(values),
            'current': values[-1],
            'mean': statistics.fmean(values),
            'p50': self._percentile(values, 0.50),
            'p95': self._percentile(values, 0.95),
            'samples': values,
        }
      return {
          'timestamp': time.time(),
          'metrics': metrics,
          'counters': dict(self._counters),
      }


class LatencyTracker:
  """Measures the first output audio after the latest input activity."""

  def __init__(
      self,
      metrics: MetricsStore,
      *,
      clock: Callable[[], float] = time.perf_counter,
  ):
    self._metrics = metrics
    self._clock = clock
    self._input_at: float | None = None

  def mark_input(self) -> None:
    self._input_at = self._clock()

  def mark_output_audio(self) -> None:
    if self._input_at is None:
      return
    self._metrics.observe('ttfa_ms', (self._clock() - self._input_at) * 1000)
    self._input_at = None
