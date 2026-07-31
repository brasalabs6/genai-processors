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

  def test_session_reset_clears_samples_and_counters(self):
    store = telemetry.MetricsStore()
    store.observe('ttfa_ms', 12)
    store.increment('audio_chunks_sent', 3)

    sequence = store.reset_session()
    snapshot = store.snapshot()

    self.assertEqual(sequence, 1)
    self.assertEqual(snapshot['session_sequence'], 1)
    self.assertEqual(snapshot['metrics'], {})
    self.assertEqual(snapshot['counters'], {})

  def test_latency_tracker_observes_first_output_after_turn_boundary(self):
    store = telemetry.MetricsStore()
    tracker = telemetry.LatencyTracker(store, clock=lambda: 10.0)
    tracker.mark_turn_boundary()
    tracker._clock = lambda: 10.125
    tracker.mark_output_audio()
    tracker._clock = lambda: 11.0
    tracker.mark_output_audio()

    samples = store.snapshot()['metrics']['ttfa_ms']['samples']
    self.assertEqual(samples, [125.0])

  def test_transport_activity_does_not_move_an_existing_boundary(self):
    moments = iter((10.0, 10.5))
    store = telemetry.MetricsStore()
    tracker = telemetry.LatencyTracker(store, clock=lambda: next(moments))

    tracker.mark_turn_boundary()
    # There is intentionally no per-audio-chunk API. Continuous transport
    # cannot rewrite the endpointed turn start time.
    tracker.mark_output_audio()

    self.assertEqual(store.snapshot()['metrics']['ttfa_ms']['samples'], [500.0])

  def test_metric_series_count_is_bounded(self):
    store = telemetry.MetricsStore(max_series=2)
    store.observe('first', 1)
    store.observe('second', 2)

    with self.assertRaisesRegex(ValueError, 'series limit'):
      store.observe('untrusted-third', 3)

    # Existing allowlisted series remain writable at the bound.
    store.observe('first', 4)
    self.assertEqual(store.snapshot()['metrics']['first']['current'], 4)


if __name__ == '__main__':
  unittest.main()
