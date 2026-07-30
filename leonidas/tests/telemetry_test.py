import unittest

from leonidas import telemetry


class MetricsStoreTest(unittest.TestCase):

  def test_snapshot_reports_current_mean_p50_and_p95(self):
    store = telemetry.MetricsStore(max_samples=5)
    for value in (10, 20, 30, 40, 50, 60):
      store.observe('ttfa_ms', value)

    metric = store.snapshot()['metrics']['ttfa_ms']
    self.assertEqual(metric['count'], 5)
    self.assertEqual(metric['current'], 60)
    self.assertEqual(metric['mean'], 40)
    self.assertEqual(metric['p50'], 40)
    self.assertEqual(metric['p95'], 60)

  def test_counters_do_not_store_content(self):
    store = telemetry.MetricsStore()
    store.increment('frames_sent', amount=2)
    self.assertEqual(store.snapshot()['counters']['frames_sent'], 2)

  def test_latency_tracker_observes_first_output_after_latest_input(self):
    store = telemetry.MetricsStore()
    tracker = telemetry.LatencyTracker(store, clock=lambda: 10.0)
    tracker.mark_input()
    tracker._clock = lambda: 10.125
    tracker.mark_output_audio()
    tracker._clock = lambda: 11.0
    tracker.mark_output_audio()

    samples = store.snapshot()['metrics']['ttfa_ms']['samples']
    self.assertEqual(samples, [125.0])


if __name__ == '__main__':
  unittest.main()
