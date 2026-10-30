"""PC side of the sync box connection: parses messages, keeps the clocks in sync,
turns closures into ClickEvents in PC time. Every problem is raised, never hidden."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from wpcap.clock import Clock
from wpcap.clocksync import ClockSync, SyncSample
from wpcap.protocol import (
    Bounce,
    Click,
    Hello,
    SequenceChecker,
    TimeReply,
    cmd_set_debounce,
    cmd_time_request,
    decode_line,
)
from wpcap.sim.transport import Transport


class SyncBoxSilent(Exception):
    """No message from the box for longer than the hello timeout."""


@dataclass(frozen=True)
class ClickEvent:
    seq: int
    t_box_us: int
    t_pc_ns: int
    interval_us: int


class SyncBoxLink:
    def __init__(
        self,
        transport: Transport,
        clock: Clock,
        clocksync: ClockSync,
        on_click: Callable[[ClickEvent], None],
        on_bounce: Callable[[int, int], None],
        sync_interval_ns: int = 250_000_000,
        hello_timeout_ns: int = 3_000_000_000,
    ) -> None:
        self._t = transport
        self._clock = clock
        self.clocksync = clocksync
        self.on_click = on_click
        self.on_bounce = on_bounce
        self._sync_interval_ns = sync_interval_ns
        self._hello_timeout_ns = hello_timeout_ns
        self._seq = SequenceChecker()
        self._pending: dict[int, int] = {}  # req_id -> t_send_ns
        self._next_req_id = 1
        self._next_sync_ns = 0
        self._opened_ns = clock.now_ns()
        self.serial: str | None = None
        self.fw_version: str | None = None
        self.clicks_before_sync = 0
        self.last_message_ns: int | None = None
        self.last_interval_us: int | None = None

    def set_debounce(self, us: int) -> None:
        if us <= 0:
            raise ValueError("debounce must be positive microseconds")
        self._t.write(cmd_set_debounce(us))

    def poll(self) -> None:
        now = self._clock.now_ns()
        while (line := self._t.read_line()) is not None:
            msg = decode_line(line)
            self._seq.check(msg.seq)
            self.last_message_ns = self._clock.now_ns()
            match msg:
                case Hello(_, _, fw_version, serial):
                    self.serial = serial
                    self.fw_version = fw_version
                case TimeReply(_, t_us, req_id):
                    t_send = self._pending.pop(req_id, None)
                    if t_send is None:
                        raise ValueError(f"time reply for unknown request {req_id}")
                    self.clocksync.add(SyncSample(t_send, self.last_message_ns, t_us))
                case Click(seq, t_us, interval_us):
                    self.last_interval_us = interval_us
                    if not self.clocksync.ready:
                        self.clicks_before_sync += 1
                        continue
                    self.on_click(
                        ClickEvent(seq, t_us, self.clocksync.box_to_pc_ns(t_us), interval_us)
                    )
                case Bounce(seq, t_us):
                    self.on_bounce(seq, t_us)
        last = self.last_message_ns if self.last_message_ns is not None else self._opened_ns
        if now - last > self._hello_timeout_ns:
            raise SyncBoxSilent(f"no message from sync box for {(now - last) / 1e9:.1f} s")
        if now >= self._next_sync_ns:
            req_id = self._next_req_id
            self._next_req_id += 1
            self._pending[req_id] = now
            self._t.write(cmd_time_request(req_id))
            self._next_sync_ns = now + self._sync_interval_ns
