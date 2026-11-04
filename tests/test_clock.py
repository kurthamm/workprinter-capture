import pytest

from wpcap.clock import SimClock, SystemClock


def test_system_clock_is_monotonic():
    c = SystemClock()
    a = c.now_ns()
    b = c.now_ns()
    assert b >= a


def test_sim_clock_starts_at_zero_and_advances():
    c = SimClock()
    assert c.now_ns() == 0
    c.advance(1_500)
    assert c.now_ns() == 1_500
    c.set(10_000)
    assert c.now_ns() == 10_000


def test_sim_clock_never_goes_backwards():
    c = SimClock()
    c.set(100)
    with pytest.raises(ValueError):
        c.advance(-1)
    with pytest.raises(ValueError):
        c.set(99)
