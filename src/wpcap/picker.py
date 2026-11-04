"""Pick one picture per click: the one whose timestamp is nearest click time + delay."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from wpcap.camera import Picture
from wpcap.synclink import ClickEvent

# A calibration window is only meaningful around pictures taken close to the click: farther
# than this from the target, the pictures show something else (the buffer has moved on).
WINDOW_MAX_DISTANCE_NS = 200_000_000


class RingBuffer:
    def __init__(self, window_ns: int = 1_000_000_000) -> None:
        self._window = window_ns
        self._pics: deque[Picture] = deque()
        self._taken: set[int] = set()

    def push(self, p: Picture) -> None:
        if self._pics and p.t_ns < self._pics[-1].t_ns:
            raise ValueError(f"picture {p.index} is older than the newest in the buffer")
        self._pics.append(p)
        while self._pics and self._pics[0].t_ns < p.t_ns - self._window:
            old = self._pics.popleft()
            self._taken.discard(old.index)

    @property
    def newest_t_ns(self) -> int | None:
        return self._pics[-1].t_ns if self._pics else None

    def nearest(self, t_ns: int, untaken_only: bool = False) -> Picture | None:
        best = None
        for p in self._pics:
            if untaken_only and p.index in self._taken:
                continue
            if best is None or abs(p.t_ns - t_ns) < abs(best.t_ns - t_ns):
                best = p
        return best

    def take(self, index: int) -> None:
        self._taken.add(index)

    def is_taken(self, index: int) -> bool:
        return index in self._taken

    def window(self, t_ns: int, before: int, after: int) -> list[Picture]:
        """The picture nearest t_ns with up to `before` older and `after` newer neighbours,
        oldest first. Fewer at the edges of the buffer; empty when the buffer is empty or the
        nearest picture is more than WINDOW_MAX_DISTANCE_NS from t_ns."""
        if not self._pics:
            return []
        pics = list(self._pics)
        centre = min(range(len(pics)), key=lambda i: abs(pics[i].t_ns - t_ns))
        if abs(pics[centre].t_ns - t_ns) > WINDOW_MAX_DISTANCE_NS:
            return []
        return pics[max(0, centre - before) : centre + after + 1]

    def __len__(self) -> int:
        return len(self._pics)


@dataclass
class PendingClick:
    click: ClickEvent
    frame_number: int
    target_ns: int


@dataclass(frozen=True)
class Picked:
    pending: PendingClick
    picture: Picture
    offset_ns: int


@dataclass(frozen=True)
class Failed:
    pending: PendingClick
    reason: str


class FramePicker:
    def __init__(
        self,
        delay_ns: int,
        tolerance_ns: int,
        stall_ns: int,
        on_picked: Callable[[Picked], None],
        on_failed: Callable[[Failed], None],
        window_ns: int = 1_000_000_000,
    ) -> None:
        if tolerance_ns <= 0 or stall_ns <= 0:
            raise ValueError("tolerance and stall must be positive")
        self.delay_ns = delay_ns
        self.tolerance_ns = tolerance_ns
        self.stall_ns = stall_ns
        self._on_picked = on_picked
        self._on_failed = on_failed
        self.buffer = RingBuffer(window_ns)
        self._pending: deque[PendingClick] = deque()
        self.last_target_ns: int | None = None

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def drain(self) -> list[PendingClick]:
        """Remove and return the unresolved clicks in order, without calling back."""
        out = list(self._pending)
        self._pending.clear()
        return out

    def on_click(self, pending: PendingClick) -> None:
        pending.target_ns = pending.click.t_pc_ns + self.delay_ns
        self.last_target_ns = pending.target_ns
        self._pending.append(pending)
        self._resolve()

    def set_delay(self, delay_ns: int) -> None:
        self.delay_ns = delay_ns

    def on_picture(self, p: Picture) -> None:
        self.buffer.push(p)
        self._resolve()

    def check(self, now_ns: int) -> None:
        self._resolve()
        while self._pending:
            head = self._pending[0]
            if now_ns >= head.target_ns + self.tolerance_ns + self.stall_ns:
                self._pending.popleft()
                self._on_failed(Failed(head, "camera stalled"))
            else:
                break

    def _resolve(self) -> None:
        while self._pending:
            head = self._pending[0]
            newest = self.buffer.newest_t_ns
            if newest is None or newest < head.target_ns + self.tolerance_ns:
                return
            self._pending.popleft()
            p = self.buffer.nearest(head.target_ns, untaken_only=True)
            if p is None or abs(p.t_ns - head.target_ns) > self.tolerance_ns:
                self._on_failed(Failed(head, "no picture within window"))
                continue
            self.buffer.take(p.index)
            self._on_picked(Picked(head, p, p.t_ns - head.target_ns))
