"""Wire protocol between the PC and the sync box. See protocol/PROTOCOL.md.

ASCII lines: "<TYPE> <field> <field>...*<CRC16 hex>\\n". Every message from the box carries
one shared sequence number so a lost or repeated message is detected, never skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

SEQ_MODULO = 2**32


class ProtocolError(Exception):
    """A line that cannot be trusted: bad CRC, unknown type, malformed fields."""


class SequenceGapError(Exception):
    def __init__(self, expected: int, got: int) -> None:
        super().__init__(f"sync box sequence gap: expected {expected}, got {got}")
        self.expected = expected
        self.got = got


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, no xorout)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Click:
    seq: int
    t_us: int
    interval_us: int


@dataclass(frozen=True)
class Bounce:
    seq: int
    t_us: int


@dataclass(frozen=True)
class TimeReply:
    seq: int
    t_us: int
    req_id: int


@dataclass(frozen=True)
class Hello:
    seq: int
    t_us: int
    fw_version: str
    serial: str


BoxMessage = Click | Bounce | TimeReply | Hello


def _frame(body: bytes) -> bytes:
    return body + b"*" + f"{crc16(body):04X}".encode("ascii") + b"\n"


def _unframe(line: bytes) -> list[bytes]:
    stripped = line.rstrip(b"\r\n")
    star = stripped.rfind(b"*")
    if star < 0 or len(stripped) - star != 5:
        raise ProtocolError(f"missing CRC suffix: {line!r}")
    body, crc_text = stripped[:star], stripped[star + 1 :]
    try:
        crc_given = int(crc_text, 16)
    except ValueError as e:
        raise ProtocolError(f"bad CRC text: {line!r}") from e
    if crc_given != crc16(body):
        raise ProtocolError(f"CRC mismatch: {line!r}")
    return body.split(b" ")


def _ints(fields: list[bytes], line: bytes) -> list[int]:
    out = []
    for f in fields:
        try:
            out.append(int(f))
        except ValueError as e:
            raise ProtocolError(f"non-integer field {f!r} in {line!r}") from e
    return out


def encode_message(msg: BoxMessage) -> bytes:
    match msg:
        case Click(seq, t_us, interval_us):
            body = f"C {seq} {t_us} {interval_us}"
        case Bounce(seq, t_us):
            body = f"B {seq} {t_us}"
        case TimeReply(seq, t_us, req_id):
            body = f"T {seq} {t_us} {req_id}"
        case Hello(seq, t_us, fw_version, serial):
            body = f"H {seq} {t_us} {fw_version} {serial}"
        case _:
            raise TypeError(f"not a BoxMessage: {msg!r}")
    return _frame(body.encode("ascii"))


def decode_line(line: bytes) -> BoxMessage:
    fields = _unframe(line)
    kind = fields[0].decode("ascii", errors="replace")
    args = fields[1:]
    match kind:
        case "C":
            if len(args) != 3:
                raise ProtocolError(f"C needs 3 fields: {line!r}")
            seq, t_us, interval_us = _ints(args, line)
            return Click(seq, t_us, interval_us)
        case "B":
            if len(args) != 2:
                raise ProtocolError(f"B needs 2 fields: {line!r}")
            seq, t_us = _ints(args, line)
            return Bounce(seq, t_us)
        case "T":
            if len(args) != 3:
                raise ProtocolError(f"T needs 3 fields: {line!r}")
            seq, t_us, req_id = _ints(args, line)
            return TimeReply(seq, t_us, req_id)
        case "H":
            if len(args) != 4:
                raise ProtocolError(f"H needs 4 fields: {line!r}")
            seq, t_us = _ints(args[:2], line)
            return Hello(seq, t_us, args[2].decode("ascii"), args[3].decode("ascii"))
        case _:
            raise ProtocolError(f"unknown message type {kind!r}: {line!r}")


class SequenceChecker:
    """Every message from the box must carry the next sequence number (mod 2**32)."""

    def __init__(self) -> None:
        self._next: int | None = None

    def check(self, seq: int) -> None:
        if self._next is not None and seq != self._next:
            raise SequenceGapError(self._next, seq)
        self._next = (seq + 1) % SEQ_MODULO


def cmd_time_request(req_id: int) -> bytes:
    return _frame(f"T {req_id}".encode("ascii"))


def cmd_set_debounce(us: int) -> bytes:
    return _frame(f"D {us}".encode("ascii"))


def cmd_identify() -> bytes:
    return _frame(b"I")


def parse_command(line: bytes) -> tuple[str, list[int]]:
    fields = _unframe(line)
    return fields[0].decode("ascii"), _ints(fields[1:], line)
