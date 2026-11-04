"""Camera source interface. A camera delivers timestamped Pictures; nothing else."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class CameraInfo:
    name: str
    serial: str
    width: int
    height: int
    fps: float
    mode: str


@dataclass(frozen=True)
class Picture:
    index: int
    t_ns: int
    pixels: np.ndarray

    def __post_init__(self) -> None:
        if self.pixels.ndim != 3 or self.pixels.shape[2] != 3:
            raise ValueError(f"picture must be (H, W, 3), got {self.pixels.shape}")
        if self.pixels.dtype != np.uint8:
            raise ValueError(f"picture must be uint8, got {self.pixels.dtype}")

    @property
    def shape(self) -> tuple[int, int]:
        return self.pixels.shape[0], self.pixels.shape[1]


class CameraSource(Protocol):
    def info(self) -> CameraInfo: ...

    def start(self, on_picture: Callable[[Picture], None]) -> None: ...

    def stop(self) -> None: ...
