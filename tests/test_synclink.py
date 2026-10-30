import pytest

from wpcap.clock import SimClock
from wpcap.clocksync import ClockSync
from wpcap.protocol import ProtocolError, SequenceGapError
from wpcap.sim.syncbox import SimSyncBox
from wpcap.sim.transport import sim_transport_pair
from wpcap.synclink import SyncBoxLink, SyncBoxSilent


class Rig:
    def __init__(self, **box_kwargs):
        self.clock = SimClock()
        box_side, pc_side = sim_transport_pair()
        self.box = SimSyncBox(self.clock, box_side, **box_kwargs)
        self.clicks = []
        self.bounces = []
        self.link = SyncBoxLink(
            pc_side,
            self.clock,
            ClockSync(),
            self.clicks.append,
            lambda s, t: self.bounces.append(s),
        )

    def run(self, ns: int, step_ns: int = 1_000_000):
        end = self.clock.now_ns() + ns
        while self.clock.now_ns() < end:
            self.clock.advance(step_ns)
            self.box.tick()
            self.link.poll()


def test_link_reaches_sync_and_reports_serial():
    r = Rig(offset_us=5_000_000)
    r.run(2_000_000_000)
    assert r.link.clocksync.ready
    assert r.link.serial == "SIM00000001"
    assert r.link.clocksync.error_ms < 2.0


def test_clicks_are_converted_to_pc_time():
    r = Rig(offset_us=5_000_000, drift_ppm=30)
    r.run(2_000_000_000)
    t_click = r.clock.now_ns()
    r.box.close_switch()
    r.link.poll()
    assert len(r.clicks) == 1
    assert abs(r.clicks[0].t_pc_ns - t_click) < 1_000_000
    assert r.link.last_interval_us == 0


def test_clicks_before_sync_are_counted_not_delivered():
    r = Rig()
    r.box.tick()
    r.box.close_switch()
    r.link.poll()
    assert r.clicks == []
    assert r.link.clicks_before_sync == 1


def test_bounce_is_reported_separately():
    r = Rig()
    r.run(2_000_000_000)
    r.box.close_switch()
    r.clock.advance(3_000_000)
    r.box.close_switch()
    r.link.poll()
    assert len(r.clicks) == 1 and r.bounces == [r.clicks[0].seq + 1]


def test_dropped_message_is_sequence_gap_fault():
    r = Rig()
    r.run(2_000_000_000)
    r.box.drop_next = True
    r.box.close_switch()
    r.box.close_switch()
    with pytest.raises(SequenceGapError):
        r.link.poll()


def test_corrupted_message_is_protocol_fault():
    r = Rig()
    r.run(2_000_000_000)
    r.box.corrupt_next = True
    r.box.close_switch()
    with pytest.raises(ProtocolError):
        r.link.poll()


def test_silent_box_is_fault():
    r = Rig()
    r.run(2_000_000_000)
    r.clock.advance(3_500_000_000)
    with pytest.raises(SyncBoxSilent):
        r.link.poll()


def test_set_debounce_reaches_box():
    r = Rig()
    r.link.set_debounce(50_000)
    r.box.tick()
    assert r.box.debounce_us == 50_000
