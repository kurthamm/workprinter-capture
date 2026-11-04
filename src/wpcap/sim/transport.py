"""Byte transport to a sync box. The real one wraps a serial port; this one is in memory."""

from __future__ import annotations

from collections import deque
from typing import Protocol


class Transport(Protocol):
    def read_line(self) -> bytes | None:
        """Return one complete line (with its trailing newline) or None if none is complete."""
        ...

    def write(self, data: bytes) -> None: ...

    def close(self) -> None: ...


class SimTransport:
    def __init__(self) -> None:
        self._inbox: deque[bytes] = deque()
        self._partial = b""
        self.peer: SimTransport | None = None
        self.closed = False

    def _deliver(self, data: bytes) -> None:
        self._partial += data
        while b"\n" in self._partial:
            line, self._partial = self._partial.split(b"\n", 1)
            self._inbox.append(line + b"\n")

    def read_line(self) -> bytes | None:
        if self.closed:
            raise OSError("transport closed")
        return self._inbox.popleft() if self._inbox else None

    def write(self, data: bytes) -> None:
        if self.closed:
            raise OSError("transport closed")
        if self.peer is None:
            raise RuntimeError("SimTransport has no peer")
        self.peer._deliver(data)

    def close(self) -> None:
        self.closed = True


def sim_transport_pair() -> tuple[SimTransport, SimTransport]:
    a, b = SimTransport(), SimTransport()
    a.peer, b.peer = b, a
    return a, b
