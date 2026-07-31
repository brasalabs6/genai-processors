"""Content-free runtime metrics for Leonidas."""

import collections
import math
import statistics
import threading
import time
from typing import Any
from typing import Callable


class MetricsStore:
  """Keeps bounded metric samples, series and counters in memory."""

  def __init__(self, max_samples: int = 100, max_series: int = 64):
    if max_samples <= 0 or max_series <= 0:
      raise ValueError('Metric bounds must be positive')
    self._max_samples = max_samples
    self._max_series = max_series
    self._samples: dict[str, collections.deque[float]] = {}
    self._counters: collections.Counter[str] = collections.Counter()
    self._lock = threading.Lock()

  def observe(self, name: str, value: float) -> None:
    with self._lock:
      if name not in self._samples and len(self._samples) >= self._max_series:
        raise ValueError('Metric series limit reached')
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
  """Measures first output audio from a completed input-turn boundary."""

  def __init__(
      self,
      metrics: MetricsStore,
      *,
      clock: Callable[[], float] = time.perf_counter,
  ):
    self._metrics = metrics
    self._clock = clock
    self._turn_boundary_at: float | None = None

  def mark_turn_boundary(self) -> None:
    """Starts TTFA after text submit, endpointed speech, or mic shutdown."""
    self._turn_boundary_at = self._clock()

  def mark_input(self) -> None:
    """Compatibility alias for callers that already represent a boundary."""
    self.mark_turn_boundary()

  def mark_output_audio(self) -> None:
    if self._turn_boundary_at is None:
      return
    self._metrics.observe(
        'ttfa_ms', (self._clock() - self._turn_boundary_at) * 1000
    )
    self._turn_boundary_at = None
