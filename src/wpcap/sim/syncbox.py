"""A sync box that speaks the real protocol, driven by a SimClock.

Mirrors what the firmware will do (plan 3): timestamp closures, filter bounce, answer time
requests, say hello every second. Offset and drift make its clock differ from the PC's.
"""

from __future__ import annotations

from wpcap.clock import SimClock
from wpcap.protocol import (
    SEQ_MODULO,
    Bounce,
    BoxMessage,
    Click,
    Hello,
    TimeReply,
    encode_message,
    is_wire_text,
    parse_command,
)
from wpcap.transport import Transport


class SimSyncBox:
    def __init__(
        self,
        clock: SimClock,
        transport: Transport,
        serial: str = "SIM00000001",
        offset_us: int = 0,
        drift_ppm: float = 0.0,
        debounce_us: int = 20_000,
        fw_version: str = "sim-0.1",
    ) -> None:
        for text in (serial, fw_version):
            if not is_wire_text(text):
                raise ValueError(f"serial and firmware version must be wire text: {text!r}")
        self._clock = clock
        self._t = transport
        self.serial = serial
        self.offset_us = offset_us
        self.drift_ppm = drift_ppm
        self.debounce_us = debounce_us
        self.fw_version = fw_version
        self.seq = 0
        self.clicks_sent = 0
        self.bounces_sent = 0
        self.drop_next = False
        self.corrupt_next = False
        self._last_accept_us: int | None = None
        self._next_hello_us = 0

    def box_time_us(self) -> int:
        return int((self._clock.now_ns() / 1000 + self.offset_us) * (1 + self.drift_ppm / 1e6))

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) % SEQ_MODULO
        return self.seq

    def _send(self, msg: BoxMessage) -> None:
        if self.drop_next:
            self.drop_next = False
            return
        line = encode_message(msg)
        if self.corrupt_next:
            self.corrupt_next = False
            line = line[:3] + b"9" + line[4:]
        self._t.write(line)

    def _hello(self) -> None:
        self._send(Hello(self._next_seq(), self.box_time_us(), self.fw_version, self.serial))

    def close_switch(self) -> None:
        now = self.box_time_us()
        if self._last_accept_us is not None and now - self._last_accept_us < self.debounce_us:
            self.bounces_sent += 1
            self._send(Bounce(self._next_seq(), now))
            return
        interval = 0 if self._last_accept_us is None else now - self._last_accept_us
        self._last_accept_us = now
        self.clicks_sent += 1
        self._send(Click(self._next_seq(), now, interval))

    def tick(self) -> None:
        while (line := self._t.read_line()) is not None:
            kind, args = parse_command(line)
            match kind, args:
                case "T", [req_id]:
                    self._send(TimeReply(self._next_seq(), self.box_time_us(), req_id))
                case "D", [us]:
                    self.debounce_us = us
                case "I", []:
                    self._hello()
                case _:
                    raise ValueError(f"sim sync box got bad command {kind} {args}")
        now = self.box_time_us()
        if now >= self._next_hello_us:
            self._hello()
            self._next_hello_us = now + 1_000_000
