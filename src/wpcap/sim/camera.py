"""Renders what a camera pointed at the gate would see, from a SimFilm timeline."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from wpcap.camera import CameraInfo, Picture
from wpcap.clock import Clock
from wpcap.sim.film import SimFilm

EMPTY_GATE_LEVEL = 235
BACKGROUND_LEVEL = 110
STRIP_ROWS = 8
STRIP_BITS = 24


def encode_number(pixels: np.ndarray, n: int) -> None:
    if not 0 <= n < 2**STRIP_BITS:
        raise ValueError(f"frame number out of range: {n}")
    w = pixels.shape[1]
    cell = w // STRIP_BITS
    for bit in range(STRIP_BITS):
        value = 255 if (n >> (STRIP_BITS - 1 - bit)) & 1 else 0
        pixels[:STRIP_ROWS, bit * cell : (bit + 1) * cell, :] = value


def _strip_levels(pixels: np.ndarray) -> np.ndarray:
    w = pixels.shape[1]
    cell = w // STRIP_BITS
    return np.array(
        [pixels[:STRIP_ROWS, b * cell : (b + 1) * cell, :].mean() for b in range(STRIP_BITS)]
    )


def decode_number(pixels: np.ndarray) -> int | None:
    levels = _strip_levels(pixels)
    if np.any((levels > 40) & (levels < 215)):
        return None
    n = 0
    for level in levels:
        n = (n << 1) | (1 if level >= 215 else 0)
    return n


def is_blurred(pixels: np.ndarray) -> bool:
    return decode_number(pixels) is None and pixels.min() != pixels.max()


class SimCamera:
    def __init__(
        self,
        clock: Clock,
        film: SimFilm,
        fps: float = 60.0,
        width: int = 192,
        height: int = 108,
        serial: str = "SIMCAM0001",
    ) -> None:
        if width % STRIP_BITS != 0 or height <= STRIP_ROWS:
            raise ValueError("width must be a multiple of 24 and height > 8")
        self._clock = clock
        self.film = film
        self.fps = fps
        self.width = width
        self.height = height
        self.serial = serial
        self._period_ns = 1e9 / fps
        self._index = 0
        self._next_emit = 0.0
        self._cb: Callable[[Picture], None] | None = None

    @property
    def started(self) -> bool:
        return self._cb is not None

    def info(self) -> CameraInfo:
        return CameraInfo(
            name="Simulated camera",
            serial=self.serial,
            width=self.width,
            height=self.height,
            fps=self.fps,
            mode=f"sim-rgb-{self.width}x{self.height}@{self.fps:g}",
        )

    def start(self, on_picture: Callable[[Picture], None]) -> None:
        if self._cb is not None:
            raise RuntimeError("camera already started")
        self._cb = on_picture

    def stop(self) -> None:
        self._cb = None

    def _frame_image(self, n: int) -> np.ndarray:
        img = np.full((self.height, self.width, 3), BACKGROUND_LEVEL, dtype=np.uint8)
        band = (n * 7) % self.width
        ys, xs = np.mgrid[STRIP_ROWS : self.height, 0 : self.width]
        mask = ((xs + ys // 2 - band) % self.width) < 12
        body = img[STRIP_ROWS:, :, :]
        body[mask] = 180
        encode_number(img, n)
        return img

    def render(self, t_ns: int) -> Picture:
        n, moving = self.film.state_at(t_ns)
        if n is None or self.film.is_leader(n):
            img = np.full((self.height, self.width, 3), EMPTY_GATE_LEVEL, dtype=np.uint8)
        elif moving:
            a = self._frame_image(n).astype(np.uint16)
            nxt = n + 1
            if nxt <= self.film.frames and not self.film.is_leader(nxt):
                b = self._frame_image(nxt).astype(np.uint16)
            else:
                b = np.full_like(a, EMPTY_GATE_LEVEL)
            img = ((a + b) // 2).astype(np.uint8)
        else:
            img = self._frame_image(n)
        p = Picture(self._index, t_ns, img)
        self._index += 1
        return p

    def emit_until(self, t_ns: int) -> list[Picture]:
        if self._cb is None:
            raise RuntimeError("camera not started")
        out = []
        while self._next_emit <= t_ns:
            p = self.render(round(self._next_emit))
            self._cb(p)
            out.append(p)
            self._next_emit += self._period_ns
        return out
