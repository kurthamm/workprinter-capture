"""End-of-reel detection from the picture (spec 6.3) and camcorder-setting drift (spec 5.5)."""

from __future__ import annotations

from collections import deque

import numpy as np


def _sample(pixels: np.ndarray) -> np.ndarray:
    return pixels[::4, ::4, :].astype(np.float32)


def is_empty_gate(pixels: np.ndarray, bright_min: int, std_max: float) -> bool:
    s = _sample(pixels)
    return float(s.mean()) >= bright_min and float(s.std()) <= std_max


class GateDetector:
    def __init__(
        self,
        bright_min: int = 200,
        std_max: float = 8.0,
        empty_needed: int = 24,
        min_frames_before: int = 100,
    ) -> None:
        if empty_needed < 1 or min_frames_before < 0:
            raise ValueError("bad GateDetector parameters")
        self.bright_min = bright_min
        self.std_max = std_max
        self.empty_needed = empty_needed
        self.min_frames_before = min_frames_before
        self.empty_run = 0
        self.picture_frames_seen = 0
        self.finished = False

    def reset(self) -> None:
        self.empty_run = 0
        self.picture_frames_seen = 0
        self.finished = False

    def observe(self, frame_number: int, pixels: np.ndarray) -> bool:
        if self.finished:
            return False
        if is_empty_gate(pixels, self.bright_min, self.std_max):
            if self.picture_frames_seen < self.min_frames_before:
                return False  # leader
            self.empty_run += 1
            if self.empty_run >= self.empty_needed:
                self.finished = True
                return True
            return False
        self.empty_run = 0
        self.picture_frames_seen += 1
        return False


class ExposureWatcher:
    def __init__(self, window: int = 30, jump: float = 25.0) -> None:
        if window < 1 or jump <= 0:
            raise ValueError("bad ExposureWatcher parameters")
        self._means: deque[float] = deque(maxlen=window)
        self.jump = jump

    def observe(self, pixels: np.ndarray) -> float | None:
        m = float(_sample(pixels).mean())
        result = None
        if len(self._means) == self._means.maxlen:
            baseline = sum(self._means) / len(self._means)
            if abs(m - baseline) > self.jump:
                result = abs(m - baseline)
        self._means.append(m)
        return result
