"""Byte transport to a sync box. The real one wraps a serial port."""

from __future__ import annotations

from typing import Protocol


class Transport(Protocol):
    def read_line(self) -> bytes | None:
        """Return one complete line (with its trailing newline) or None if none is complete."""
        ...

    def write(self, data: bytes) -> None: ...

    def close(self) -> None: ...
