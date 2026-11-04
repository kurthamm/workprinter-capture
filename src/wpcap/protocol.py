"""Wire protocol between the PC and the sync box. See protocol/PROTOCOL.md.

ASCII lines: "<TYPE> <field> <field>...*<CRC16 hex>\\n". Every message from the box carries
one shared sequence number so a lost or repeated message is detected, never skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SEQ_MODULO = 2**32
TIME_MODULO = 2**64  # the box's microsecond counter is 64-bit and never wraps in practice


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


_INT_RE = re.compile(rb"-?[0-9]+")


def _ints(fields: list[bytes], line: bytes) -> list[int]:
    out = []
    for f in fields:
        if not _INT_RE.fullmatch(f):
            raise ProtocolError(f"non-integer field {f!r} in {line!r}")
        out.append(int(f))
    return out


def _in_range(line: bytes, **values: tuple[int, int]) -> None:
    """Each value must satisfy 0 <= value < limit."""
    for name, (value, limit) in values.items():
        if not 0 <= value < limit:
            raise ProtocolError(f"{name} {value} out of range in {line!r}")


def is_wire_text(text: str) -> bool:
    """Hello text fields: printable ASCII, at least one character, no space and no '*'."""
    return bool(text) and all(0x21 <= ord(c) <= 0x7E and c != "*" for c in text)


def _text(field: bytes, line: bytes) -> str:
    if not field or any(not 0x21 <= b <= 0x7E or b == ord("*") for b in field):
        raise ProtocolError(f"bad text field {field!r} in {line!r}")
    return field.decode("ascii")


def encode_message(msg: BoxMessage) -> bytes:
    match msg:
        case Click(seq, t_us, interval_us):
            body = f"C {seq} {t_us} {interval_us}"
        case Bounce(seq, t_us):
            body = f"B {seq} {t_us}"
        case TimeReply(seq, t_us, req_id):
            body = f"T {seq} {t_us} {req_id}"
        case Hello(seq, t_us, fw_version, serial):
            for text in (fw_version, serial):
                if not is_wire_text(text):
                    raise ValueError(
                        f"Hello text must be printable ASCII without spaces or '*': {text!r}"
                    )
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
            _in_range(
                line,
                seq=(seq, SEQ_MODULO),
                t_us=(t_us, TIME_MODULO),
                interval_us=(interval_us, TIME_MODULO),
            )
            return Click(seq, t_us, interval_us)
        case "B":
            if len(args) != 2:
                raise ProtocolError(f"B needs 2 fields: {line!r}")
            seq, t_us = _ints(args, line)
            _in_range(line, seq=(seq, SEQ_MODULO), t_us=(t_us, TIME_MODULO))
            return Bounce(seq, t_us)
        case "T":
            if len(args) != 3:
                raise ProtocolError(f"T needs 3 fields: {line!r}")
            seq, t_us, req_id = _ints(args, line)
            _in_range(
                line, seq=(seq, SEQ_MODULO), t_us=(t_us, TIME_MODULO), req_id=(req_id, SEQ_MODULO)
            )
            return TimeReply(seq, t_us, req_id)
        case "H":
            if len(args) != 4:
                raise ProtocolError(f"H needs 4 fields: {line!r}")
            seq, t_us = _ints(args[:2], line)
            _in_range(line, seq=(seq, SEQ_MODULO), t_us=(t_us, TIME_MODULO))
            return Hello(seq, t_us, _text(args[2], line), _text(args[3], line))
        case _:
            raise ProtocolError(f"unknown message type {kind!r}: {line!r}")


class SequenceChecker:
    """Every message from the box must carry the next sequence number (mod 2**32)."""

    def __init__(self) -> None:
        self._next: int | None = None

    def check(self, seq: int) -> None:
        expected = self._next
        self._next = (seq + 1) % SEQ_MODULO
        if expected is not None and seq != expected:
            raise SequenceGapError(expected, seq)  # reported once; the next message re-syncs


def cmd_time_request(req_id: int) -> bytes:
    if not 0 <= req_id < SEQ_MODULO:
        raise ValueError(f"request id {req_id} does not fit 32 bits")
    return _frame(f"T {req_id}".encode("ascii"))


def cmd_set_debounce(us: int) -> bytes:
    return _frame(f"D {us}".encode("ascii"))


def cmd_identify() -> bytes:
    return _frame(b"I")


def parse_command(line: bytes) -> tuple[str, list[int]]:
    fields = _unframe(line)
    return fields[0].decode("ascii"), _ints(fields[1:], line)
