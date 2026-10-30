import numpy as np

from wpcap.camera import Picture
from wpcap.picker import Failed, FramePicker, PendingClick, Picked, RingBuffer
from wpcap.synclink import ClickEvent

MS = 1_000_000


def pic(index: int, t_ms: float) -> Picture:
    return Picture(index, int(t_ms * MS), np.zeros((4, 4, 3), dtype=np.uint8))


def click(n: int, t_ms: float) -> PendingClick:
    return PendingClick(ClickEvent(n, 0, int(t_ms * MS), 0), n, 0)


class Harness:
    def __init__(self, delay_ms=0.0, tolerance_ms=25.0, stall_ms=200.0):
        self.picked: list[Picked] = []
        self.failed: list[Failed] = []
        self.p = FramePicker(
            int(delay_ms * MS),
            int(tolerance_ms * MS),
            int(stall_ms * MS),
            self.picked.append,
            self.failed.append,
        )

    def pictures(self, start_ms, end_ms, step_ms=16.0, first_index=0):
        i = first_index
        t = start_ms
        while t <= end_ms:
            self.p.on_picture(pic(i, t))
            i += 1
            t += step_ms

    def send_click(self, n, t_ms):
        self.p.on_click(click(n, t_ms))


def test_ring_buffer_keeps_window_and_finds_nearest():
    rb = RingBuffer(window_ns=100 * MS)
    for i in range(20):
        rb.push(pic(i, i * 16))
    assert rb.newest_t_ns == 19 * 16 * MS
    assert len(rb) == 7  # 304 - 100 = 204 → indices 13..19
    assert rb.nearest(300 * MS).index == 19
    assert rb.nearest(250 * MS).index == 16  # 256 is nearer than 240


def test_picks_nearest_picture_to_click_plus_delay():
    h = Harness(delay_ms=10)
    h.pictures(0, 200)
    h.send_click(1, 100)  # target 110 → picture at 112 (index 7)
    assert len(h.picked) == 1 and h.picked[0].picture.index == 7
    assert h.picked[0].offset_ns == 2 * MS


def test_resolution_waits_for_picture_after_target():
    h = Harness(delay_ms=0)
    h.pictures(0, 96)  # newest 96
    h.send_click(1, 100)  # target 100; newest < 125 → wait
    assert h.picked == [] and h.p.pending_count == 1
    h.pictures(112, 128, first_index=7)
    assert len(h.picked) == 1 and h.picked[0].picture.index == 6  # 96 (4 away) vs 112 (12 away)


def test_click_with_empty_buffer_fails():
    h = Harness()
    h.send_click(1, 100)
    h.p.check(now_ns=400 * MS)
    assert [f.reason for f in h.failed] == ["camera stalled"]


def test_no_picture_within_window_fails():
    h = Harness(tolerance_ms=25)
    h.pictures(0, 48)
    h.pictures(200, 300, first_index=100)  # 150 ms gap
    h.send_click(1, 100)
    assert [f.reason for f in h.failed] == ["no picture within window"]


def test_picture_never_reused():
    h = Harness(tolerance_ms=25)
    h.pictures(0, 200)
    h.send_click(1, 100)  # nearest: index 6 at 96
    h.send_click(2, 101)  # index 6 is taken; next nearest untaken is index 7 at 112
    assert [p.picture.index for p in h.picked] == [6, 7]
    assert h.failed == []
    h.send_click(3, 99)  # 96 and 112 taken; 80 is 19 away (within 25) → index 5
    assert h.picked[-1].picture.index == 5
    h.send_click(4, 98)  # nearest untaken is 64 at 34 away → fails
    assert [f.reason for f in h.failed] == ["no picture within window"]


def test_stall_after_target_fails():
    h = Harness(stall_ms=200)
    h.pictures(0, 96)
    h.send_click(1, 100)
    h.p.check(now_ns=300 * MS)
    assert h.picked == []
    h.p.check(now_ns=326 * MS)
    assert [f.reason for f in h.failed] == ["camera stalled"]


def test_delay_can_be_changed_between_clicks():
    h = Harness(delay_ms=0)
    h.pictures(0, 300)
    h.send_click(1, 100)
    h.p.delay_ns = 40 * MS
    h.send_click(2, 100)
    assert [p.picture.index for p in h.picked] == [6, 9]  # 96 then 144


def test_drain_returns_pending_clicks_in_order_without_callbacks():
    h = Harness()
    h.send_click(1, 100)
    h.send_click(2, 225)
    assert [c.frame_number for c in h.p.drain()] == [1, 2]
    assert h.p.pending_count == 0 and h.picked == [] and h.failed == []
