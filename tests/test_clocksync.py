import pytest

from wpcap.clocksync import ClockSync, NotSynchronised, SyncSample


def samples(offset_us: int, drift_ppm: float, n: int, rtt_ns: int = 400_000, step_ns=250_000_000):
    """Box clock = (pc_time + offset) * (1 + drift). Request every 250 ms."""
    out = []
    for i in range(n):
        t_send = 1_000_000_000 + i * step_ns
        t_recv = t_send + rtt_ns
        mid = (t_send + t_recv) // 2
        t_box_us = int((mid / 1000 + offset_us) * (1 + drift_ppm / 1e6))
        out.append(SyncSample(t_send, t_recv, t_box_us))
    return out


def test_not_ready_until_min_samples():
    cs = ClockSync()
    for s in samples(0, 0, 3):
        cs.add(s)
    assert not cs.ready
    with pytest.raises(NotSynchronised):
        cs.box_to_pc_ns(0)


def test_offset_only_converts_within_tolerance():
    cs = ClockSync()
    for s in samples(offset_us=5_000_000, drift_ppm=0, n=16):
        cs.add(s)
    assert cs.ready
    # pc = box - offset: box 8 s ↔ pc 3 s
    pc_ns = cs.box_to_pc_ns(8_000_000)
    assert abs(pc_ns - 3_000_000_000) < 1_000_000  # within 1 ms


def test_drift_is_fitted():
    cs = ClockSync()
    for s in samples(offset_us=0, drift_ppm=50, n=32):
        cs.add(s)
    assert abs(cs.drift_ppm - 50) < 5
    far_box_us = int(60_000_000 * (1 + 50 / 1e6))  # box reading one minute out
    assert abs(cs.box_to_pc_ns(far_box_us) - 60_000_000_000) < 500_000  # < 0.5 ms


def test_error_is_half_best_round_trip_and_bad_samples_are_ignored():
    cs = ClockSync()
    for s in samples(0, 0, 12, rtt_ns=300_000):
        cs.add(s)
    # Two slow, badly-timed replies (e.g. USB stall) must not move the fit.
    cs.add(SyncSample(10_000_000_000, 10_050_000_000, 10_000_000 + 40_000))
    cs.add(SyncSample(10_250_000_000, 10_300_000_000, 10_250_000 - 40_000))
    assert cs.error_ms == pytest.approx(0.15, abs=0.01)
    assert abs(cs.box_to_pc_ns(20_000_000) - 20_000_000_000) < 300_000
