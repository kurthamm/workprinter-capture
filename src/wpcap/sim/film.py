"""Timeline of a simulated reel: when each frame lands, when the switch closes, pull-down blur."""

from __future__ import annotations


class SimFilm:
    def __init__(
        self,
        frames: int,
        fps: float = 8.0,
        pulldown_ms: float = 30.0,
        switch_offset_ms: float = 0.0,
        leader_frames: int = 0,
        start_ns: int = 0,
        extra_clicks_after_end: int = 50,
    ) -> None:
        if frames < 0 or fps <= 0 or pulldown_ms < 0 or leader_frames < 0:
            raise ValueError("bad SimFilm parameters")
        self.frames = frames
        self.period_ns = round(1e9 / fps)
        self.pulldown_ns = round(pulldown_ms * 1e6)
        if self.pulldown_ns >= self.period_ns:
            raise ValueError("pull-down must be shorter than the frame period")
        self.switch_offset_ns = round(switch_offset_ms * 1e6)
        self.leader_frames = leader_frames
        self.start_ns = start_ns
        self.extra_clicks_after_end = extra_clicks_after_end

    def frame_landed_ns(self, k: int) -> int:
        if k < 1:
            raise ValueError("frames are numbered from 1")
        return self.start_ns + (k - 1) * self.period_ns

    def switch_ns(self, k: int) -> int:
        return self.frame_landed_ns(k) + self.switch_offset_ns

    def is_leader(self, k: int) -> bool:
        return k <= self.leader_frames

    def state_at(self, t_ns: int) -> tuple[int | None, bool]:
        if self.frames == 0:
            return None, False
        if t_ns < self.start_ns:
            return 1, False
        k = (t_ns - self.start_ns) // self.period_ns + 1
        if k > self.frames:
            return None, False
        into = (t_ns - self.start_ns) - (k - 1) * self.period_ns
        moving = into >= self.period_ns - self.pulldown_ns
        return k, moving

    def switch_times(self) -> list[int]:
        total = self.frames + self.extra_clicks_after_end
        return [self.switch_ns(k) for k in range(1, total + 1)]
