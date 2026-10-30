"""Convert sync-box timestamps (its microsecond timer) to PC monotonic nanoseconds.

The PC asks the box for its time repeatedly. Each exchange gives (send, receive, box time).
The box time is assumed to correspond to the midpoint of the round trip. We keep the
exchanges with the shortest round trips (least uncertainty) and fit offset and drift.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


class NotSynchronised(Exception):
    """Asked to convert a time before enough sync exchanges have happened."""


@dataclass(frozen=True)
class SyncSample:
    t_send_ns: int
    t_recv_ns: int
    t_box_us: int

    @property
    def rtt_ns(self) -> int:
        return self.t_recv_ns - self.t_send_ns

    @property
    def mid_ns(self) -> int:
        return (self.t_send_ns + self.t_recv_ns) // 2


class ClockSync:
    def __init__(self, window: int = 32, keep_best: int = 8, min_samples: int = 4) -> None:
        if keep_best < 2 or min_samples < 2 or window < keep_best:
            raise ValueError("window >= keep_best >= 2 and min_samples >= 2 required")
        self._samples: deque[SyncSample] = deque(maxlen=window)
        self._keep_best = keep_best
        self._min_samples = min_samples
        self._slope = 1.0
        self._intercept_ns = 0.0
        self._error_ms = float("inf")

    @property
    def ready(self) -> bool:
        return len(self._samples) >= self._min_samples

    @property
    def error_ms(self) -> float:
        return self._error_ms

    @property
    def drift_ppm(self) -> float:
        """How much faster the box clock runs than the PC clock, in parts per million.

        The fit maps box time to PC time (slope b = pc/box), so the box rate is 1/b.
        """
        return (1.0 / self._slope - 1.0) * 1e6

    def add(self, sample: SyncSample) -> None:
        if sample.rtt_ns < 0:
            raise ValueError(f"negative round trip: {sample}")
        self._samples.append(sample)
        self._fit()

    def _fit(self) -> None:
        best = sorted(self._samples, key=lambda s: s.rtt_ns)[: self._keep_best]
        self._error_ms = best[0].rtt_ns / 2 / 1e6
        if len(best) < 2:
            self._slope = 1.0
            self._intercept_ns = best[0].mid_ns - best[0].t_box_us * 1000
            return
        xs = [s.t_box_us * 1000 for s in best]
        ys = [s.mid_ns for s in best]
        x0, y0 = xs[0], ys[0]  # centre to keep the arithmetic in float range
        dx = [x - x0 for x in xs]
        dy = [y - y0 for y in ys]
        n = len(best)
        mx = sum(dx) / n
        my = sum(dy) / n
        sxx = sum((x - mx) ** 2 for x in dx)
        if sxx == 0:
            self._slope = 1.0
        else:
            sxy = sum((x - mx) * (y - my) for x, y in zip(dx, dy, strict=True))
            self._slope = sxy / sxx
        self._intercept_ns = (y0 + my) - self._slope * (x0 + mx)

    def box_to_pc_ns(self, t_box_us: int) -> int:
        if not self.ready:
            raise NotSynchronised(f"{len(self._samples)} of {self._min_samples} samples")
        return round(self._intercept_ns + self._slope * (t_box_us * 1000))
