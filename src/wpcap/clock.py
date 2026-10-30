"""Monotonic clocks. All PC-side times in wpcap are integer nanoseconds from one of these."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...


class SystemClock:
    """The PC's monotonic clock (time.perf_counter_ns; QueryPerformanceCounter on Windows)."""

    def now_ns(self) -> int:
        return time.perf_counter_ns()


class SimClock:
    """A clock that only moves when told to. Used by the simulators and tests."""

    def __init__(self, start_ns: int = 0) -> None:
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def advance(self, ns: int) -> None:
        if ns < 0:
            raise ValueError(f"SimClock cannot go backwards (advance {ns})")
        self._now += ns

    def set(self, ns: int) -> None:
        if ns < self._now:
            raise ValueError(f"SimClock cannot go backwards (set {ns} < {self._now})")
        self._now = ns
