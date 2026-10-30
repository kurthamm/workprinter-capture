# Capture Core Implementation Plan (plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-machine capture engine that turns sync-box clicks and a live camera feed into one saved PNG per film frame, with journal, accounting, faults and end-of-reel detection, proven end to end on the Linux dev server with simulators (spec build order step 1, first half).

**Architecture:** Pure, single-threaded core objects (`FramePicker`, `Accounting`, `GateDetector`, `Machine` state machine) are fed events (`ClickEvent`, `Picture`) by hardware adapters behind two small interfaces (sync-box transport, camera source). Simulated versions of both share one `SimFilm` model so tests can drive a whole machine in virtual time, deterministically, in milliseconds. Only the `Saver` has its own thread (fixed-size queue; temp-file-then-rename; journal). A `SimRig` wires the simulators to a `Machine` and is reused by the Demo Mode CLI in real time.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`, `numpy` (pictures), `Pillow` (PNG writing). No FastAPI, no FFmpeg in this plan (plans 2–4 cover web page + alerts, export/review/recovery extras, firmware, Windows Media Foundation backend, packaging).

**Spec:** `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` (revision 4). Sections implemented here: 5.1 (protocol side), 5.2, 5.3, 5.4 (picking; calibration screen is plan 2), 6.1–6.4 (state machine, faults; alerts delivery is plan 2), 7.1, 7.2, 10.1 (the simulator-based tests that don't need the web page or FFmpeg).

**Out of scope here (later plans):** web page and HTTPS (plan 2), ntfy, calibration screen, review, export/FFmpeg, join reels, order deliverable, resume overlap trimming, neighbour keeping, syncmouse option, firmware in C (plan 3), Windows camera backend (plan 4), installer.

## Global Constraints

- Python **3.12** (`requires-python = ">=3.12"`); run everything through `uv`.
- Canonical verification command is `testrepo`, which runs `make test` (Makefile `test:` target). Every task ends with `testrepo` passing.
- Fail fast: no default values that mask missing config, no swallowed exceptions, no stubs, no fake data in production paths (global CLAUDE.md). Simulators are real implementations of the interfaces, not mocks.
- **Accounting rule (spec 7.2):** `clicks_accepted == frames_saved + frames_pending + frames_failed` for every segment, always.
- **Never reuse a picture** for two frames; **never overwrite** an existing frame file (spec 5.4, 7.2).
- Clicks are **sequence-numbered**; a gap, duplicate or corrupt message is a **fault**, never skipped (spec 5.1, 10.1).
- Bounce filter default **20 ms**, adjustable (spec 5.3). Clock-sync error limit default **2 ms** (spec 5.2).
- Frames are lossless PNG at full camera resolution, numbered `000001.png` from 1 per reel (spec 7.2).
- Reel folder layout exactly as spec 7.2: `reel.json`, `journal.jsonl`, `frames/`, `neighbours/`, `exports/`.
- Git: work on branch `feature/capture-core` (never master/main); one commit per task; PR + CodeRabbit before user testing.
- Pictures are `numpy.ndarray` of shape `(H, W, 3)`, dtype `uint8`, RGB. Timestamps are integers: PC times in **nanoseconds** (`time.perf_counter_ns` domain), sync-box times in **microseconds**.

## Review Focus

1. **A click arrives before the camera has delivered any picture** (sync box plugged in first, camera starting). Expected: the frame is recorded as failed, a fault stops the segment, nothing crashes. Test in Task 6 (`test_click_with_empty_buffer_fails`).
2. **Two clicks closer together than the camera spacing** (a bounce that beat the filter, or a slipping belt). Expected: the second click can never be given the same picture as the first; the accounting still balances. Test in Task 6 (`test_picture_never_reused`).
3. **Two reels started within the same minute on one machine**, so the default name collides. Expected: a numbered suffix, never an overwrite of the existing folder. Test in Task 7 (`test_reel_folder_name_collision_gets_suffix`).
4. **The disk fills or the write fails mid-frame.** Expected: the temp file is removed, no half frame is renamed into place, the journal records `failed` for that frame, the machine faults with a storage message. Test in Task 7 (`test_write_error_is_fault_not_half_frame`).
5. **The camera changes picture size or mode mid-reel** (operator touched the camcorder, adapter renegotiated). Expected: camera fault, segment stops, earlier frames kept. Test in Task 9 (`test_camera_mode_change_is_fault`).

---

## File structure

```text
Makefile                         test target (ruff + pytest) → testrepo picks it up
pyproject.toml                   package wpcap, deps, pytest + ruff config
src/wpcap/__init__.py            version string
src/wpcap/clock.py               Clock protocol, SystemClock, SimClock
src/wpcap/protocol.py            sync-box wire protocol: CRC16, encode/decode, SequenceChecker, commands
src/wpcap/clocksync.py           ClockSync: box time → PC time, error estimate
src/wpcap/synclink.py            SyncBoxLink: transport → ClickEvent + time-sync loop
src/wpcap/camera.py              Picture, CameraInfo, CameraSource protocol
src/wpcap/picker.py              RingBuffer, PendingClick, FramePicker
src/wpcap/reel.py                ReelFolder (layout, naming), Journal, reel.json
src/wpcap/saver.py               Saver worker thread + QueueFull, Accounting
src/wpcap/gate.py                GateDetector (end of reel), ExposureWatcher
src/wpcap/machine.py             MachineState, Fault, Alerter protocol, Machine
src/wpcap/recovery.py            recover(): journal vs frames after a crash
src/wpcap/sim/__init__.py
src/wpcap/sim/transport.py       Transport protocol, SimTransport pair (in-memory)
src/wpcap/sim/syncbox.py         SimSyncBox: speaks the real protocol, bounce, offset, drift
src/wpcap/sim/film.py            SimFilm: when frames land, when the switch closes, pull-down blur, leader, empty gate
src/wpcap/sim/camera.py          SimCamera renders Pictures from SimFilm; encode/decode frame numbers
src/wpcap/sim/rig.py             SimRig: one Machine + simulators driven in virtual or real time
src/wpcap/__main__.py            `python -m wpcap demo` (Demo Mode)
tests/                           one test file per module, same names
protocol/PROTOCOL.md             the wire protocol (shared with firmware, plan 3)
```

---

### Task 1: Project scaffold and canonical test command

**Files:**
- Create: `pyproject.toml`, `Makefile`, `src/wpcap/__init__.py`, `tests/test_package.py`, `.gitignore`

**Interfaces:**
- Produces: package `wpcap` importable; `make test` / `testrepo` runs ruff then pytest.

- [ ] **Step 1: Create the branch**

```bash
cd /home/deltaprism/moviestuff
git checkout -b feature/capture-core
```

- [ ] **Step 2: Write the failing test**

`tests/test_package.py`:
```python
import wpcap


def test_version_is_set():
    assert wpcap.__version__ == "0.1.0"
```

- [ ] **Step 3: Write pyproject, Makefile, package, gitignore**

`pyproject.toml`:
```toml
[project]
name = "wpcap"
version = "0.1.0"
description = "WorkPrinter Capture: modern replacement for CineCap"
requires-python = ">=3.12"
dependencies = [
    "numpy>=2.0,<3",
    "pillow>=10.4,<12",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "ruff>=0.6,<1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/wpcap"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

`Makefile`:
```make
.PHONY: test lint
test:
	uv run --extra dev ruff check src tests
	uv run --extra dev pytest -q

lint:
	uv run --extra dev ruff check src tests
```

`src/wpcap/__init__.py`:
```python
"""WorkPrinter Capture."""

__version__ = "0.1.0"
```

`.gitignore`:
```text
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
reels/
uv.lock
```

- [ ] **Step 4: Run the canonical command, verify it passes**

Run: `testrepo`
Expected: `RUN: make test`, ruff clean, `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Makefile src/wpcap/__init__.py tests/test_package.py .gitignore
git commit -m "feat: project scaffold with make test as the canonical check"
```

---

### Task 2: Clocks

**Files:**
- Create: `src/wpcap/clock.py`, `tests/test_clock.py`

**Interfaces:**
- Produces:
  - `class Clock(Protocol): def now_ns(self) -> int`
  - `class SystemClock(Clock)`: `time.perf_counter_ns()`
  - `class SimClock(Clock)`: `now_ns()`, `advance(ns: int) -> None`, `set(ns: int) -> None`; `advance` with negative or `set` backwards raises `ValueError`.

- [ ] **Step 1: Write the failing tests**

`tests/test_clock.py`:
```python
import pytest

from wpcap.clock import SimClock, SystemClock


def test_system_clock_is_monotonic():
    c = SystemClock()
    a = c.now_ns()
    b = c.now_ns()
    assert b >= a


def test_sim_clock_starts_at_zero_and_advances():
    c = SimClock()
    assert c.now_ns() == 0
    c.advance(1_500)
    assert c.now_ns() == 1_500
    c.set(10_000)
    assert c.now_ns() == 10_000


def test_sim_clock_never_goes_backwards():
    c = SimClock()
    c.set(100)
    with pytest.raises(ValueError):
        c.advance(-1)
    with pytest.raises(ValueError):
        c.set(99)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_clock.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'wpcap.clock'`.

- [ ] **Step 3: Implement**

`src/wpcap/clock.py`:
```python
"""Monotonic clocks. All PC-side times in wpcap are integer nanoseconds from one of these."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...


class SystemClock:
    """The PC's monotonic clock (time.perf_counter_ns; QueryPerformanceCounter on Windows)."""

    def now_ns(self) -> int:
        return time.perf_counter_ns()


class SimClock:
    """A clock that only moves when told to. Used by the simulators and tests."""

    def __init__(self, start_ns: int = 0) -> None:
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def advance(self, ns: int) -> None:
        if ns < 0:
            raise ValueError(f"SimClock cannot go backwards (advance {ns})")
        self._now += ns

    def set(self, ns: int) -> None:
        if ns < self._now:
            raise ValueError(f"SimClock cannot go backwards (set {ns} < {self._now})")
        self._now = ns
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/wpcap/clock.py tests/test_clock.py
git commit -m "feat: Clock protocol with SystemClock and SimClock"
```

---

### Task 3: Sync-box wire protocol

**Files:**
- Create: `src/wpcap/protocol.py`, `tests/test_protocol.py`, `protocol/PROTOCOL.md`

**Interfaces:**
- Produces:
  - `crc16(data: bytes) -> int` (CRC-16/CCITT-FALSE, init 0xFFFF, poly 0x1021)
  - Messages from the box (frozen dataclasses): `Click(seq, t_us, interval_us)`, `Bounce(seq, t_us)`, `TimeReply(seq, t_us, req_id)`, `Hello(seq, t_us, fw_version: str, serial: str)`; `BoxMessage = Click | Bounce | TimeReply | Hello`
  - `encode_message(msg: BoxMessage) -> bytes` (one line, `\n` terminated, `*XXXX` CRC suffix)
  - `decode_line(line: bytes) -> BoxMessage`; raises `ProtocolError` on bad CRC, unknown type, wrong field count or non-integer field
  - `class SequenceChecker: check(seq: int) -> None` raises `SequenceGapError(expected, got)` on gap or repeat; first message sets the start
  - Commands to the box: `cmd_time_request(req_id: int) -> bytes`, `cmd_set_debounce(us: int) -> bytes`, `cmd_identify() -> bytes`; `parse_command(line: bytes) -> tuple[str, list[int]]` (used by simulator and firmware tests)

Wire format (also written to `protocol/PROTOCOL.md`): ASCII, one message per line.
`<TYPE> <seq> <t_us> [fields...]*<crc16 hex4>\n`. CRC is over everything before the `*`.
Box → PC: `C seq t_us interval_us` click accepted; `B seq t_us` bounce rejected; `T seq t_us req_id` time reply; `H seq t_us fw_version serial` hello (sent on connect and every second).
PC → box: `T req_id` time request; `D us` set debounce; `I` identify (box answers with `H`). Commands carry a CRC too.
`seq` is one 32-bit counter over all message types, starting at 0 at box boot, wrapping at 2**32.

- [ ] **Step 1: Write the failing tests**

`tests/test_protocol.py`:
```python
import pytest

from wpcap.protocol import (
    Bounce,
    Click,
    Hello,
    ProtocolError,
    SequenceChecker,
    SequenceGapError,
    TimeReply,
    cmd_identify,
    cmd_set_debounce,
    cmd_time_request,
    crc16,
    decode_line,
    encode_message,
    parse_command,
)


def test_crc16_ccitt_false_check_value():
    # Standard check value for CRC-16/CCITT-FALSE over "123456789".
    assert crc16(b"123456789") == 0x29B1


@pytest.mark.parametrize(
    "msg",
    [
        Click(seq=7, t_us=1_234_567, interval_us=125_000),
        Bounce(seq=8, t_us=1_240_000),
        TimeReply(seq=9, t_us=1_250_000, req_id=42),
        Hello(seq=0, t_us=5, fw_version="0.1.0", serial="E6614C311B4C7A2F"),
    ],
)
def test_round_trip(msg):
    line = encode_message(msg)
    assert line.endswith(b"\n")
    assert decode_line(line) == msg


def test_click_wire_format_is_exact():
    line = encode_message(Click(seq=1, t_us=2, interval_us=3))
    body = b"C 1 2 3"
    assert line == body + b"*" + f"{crc16(body):04X}".encode() + b"\n"


def test_bad_crc_is_protocol_error():
    line = bytearray(encode_message(Click(seq=1, t_us=2, interval_us=3)))
    line[-2] = ord("0") if line[-2] != ord("0") else ord("1")
    with pytest.raises(ProtocolError, match="CRC"):
        decode_line(bytes(line))


def test_unknown_type_and_wrong_field_count_are_protocol_errors():
    body = b"X 1 2"
    with pytest.raises(ProtocolError, match="unknown"):
        decode_line(body + b"*" + f"{crc16(body):04X}".encode() + b"\n")
    body = b"C 1 2"
    with pytest.raises(ProtocolError, match="fields"):
        decode_line(body + b"*" + f"{crc16(body):04X}".encode() + b"\n")


def test_non_integer_field_is_protocol_error():
    body = b"C 1 two 3"
    with pytest.raises(ProtocolError, match="integer"):
        decode_line(body + b"*" + f"{crc16(body):04X}".encode() + b"\n")


def test_sequence_checker_accepts_consecutive_and_wraps():
    s = SequenceChecker()
    s.check(2**32 - 2)
    s.check(2**32 - 1)
    s.check(0)


def test_sequence_gap_and_repeat_raise():
    s = SequenceChecker()
    s.check(5)
    with pytest.raises(SequenceGapError) as e:
        s.check(7)
    assert (e.value.expected, e.value.got) == (6, 7)
    s2 = SequenceChecker()
    s2.check(5)
    with pytest.raises(SequenceGapError):
        s2.check(5)


def test_commands_round_trip():
    assert parse_command(cmd_time_request(42)) == ("T", [42])
    assert parse_command(cmd_set_debounce(20_000)) == ("D", [20_000])
    assert parse_command(cmd_identify()) == ("I", [])


def test_command_with_bad_crc_is_protocol_error():
    line = bytearray(cmd_time_request(1))
    line[-2] = ord("0") if line[-2] != ord("0") else ord("1")
    with pytest.raises(ProtocolError, match="CRC"):
        parse_command(bytes(line))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_protocol.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'wpcap.protocol'`.

- [ ] **Step 3: Implement**

`src/wpcap/protocol.py`:
```python
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
```

`protocol/PROTOCOL.md`:
```markdown
# Sync box protocol (version 1)

USB serial, 115200 baud, ASCII, one message per line, `\n` terminated.
Format: `<TYPE> <fields...>*<CRC>` where `<CRC>` is CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
over the bytes before `*`, as four upper-case hex digits.

## Box → PC (every message carries one shared 32-bit sequence number `seq`, starting at 0 at boot)

| Line | Meaning |
|---|---|
| `C seq t_us interval_us` | Switch closure accepted. `t_us` = box microsecond timer at the closure. `interval_us` since the previous accepted closure (0 for the first). |
| `B seq t_us` | Closure rejected as contact bounce (within the debounce time of the previous accepted closure). |
| `T seq t_us req_id` | Reply to a time request: `t_us` is the box time when the request was processed. |
| `H seq t_us fw_version serial` | Hello: sent on connect, every second, and in answer to `I`. `serial` is the board's unique ID. |

A gap or repeat in `seq` is a fault on the PC side. The box never skips a number.

## PC → box

| Line | Meaning |
|---|---|
| `T req_id` | Time request. The box answers with `T` carrying the same `req_id`. |
| `D us` | Set the debounce time in microseconds (default 20000). |
| `I` | Identify: the box answers with `H`. |
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/wpcap/protocol.py tests/test_protocol.py protocol/PROTOCOL.md
git commit -m "feat: sync box wire protocol with CRC16 and sequence checking"
```

---

### Task 4: Clock sync (box time → PC time)

**Files:**
- Create: `src/wpcap/clocksync.py`, `tests/test_clocksync.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) SyncSample(t_send_ns: int, t_recv_ns: int, t_box_us: int)` with properties `rtt_ns`, `mid_ns`
  - `class NotSynchronised(Exception)`
  - `class ClockSync(window: int = 32, keep_best: int = 8, min_samples: int = 4)`:
    - `add(sample: SyncSample) -> None`
    - `ready: bool` (property; at least `min_samples` samples)
    - `box_to_pc_ns(t_box_us: int) -> int` (raises `NotSynchronised` until ready)
    - `error_ms: float` (property; half the smallest round trip among the kept samples; `inf` until any sample)
    - `drift_ppm: float` (property; fitted slope minus 1, in parts per million)

Method: for each sample, PC midpoint `m = (t_send + t_recv) / 2` and round trip `rtt = t_recv - t_send`. Keep the last `window` samples, pick the `keep_best` with the smallest `rtt`, least-squares fit `m_ns = a + b * t_box_us * 1000`. With fewer than 2 kept samples, slope is 1.

- [ ] **Step 1: Write the failing tests**

`tests/test_clocksync.py`:
```python
import pytest

from wpcap.clocksync import ClockSync, NotSynchronised, SyncSample


def samples(offset_us: int, drift_ppm: float, n: int, rtt_ns: int = 400_000, step_ns=250_000_000):
    """Box clock = (pc_time + offset) * (1 + drift). Request every 250 ms."""
    out = []
    for i in range(n):
        t_send = 1_000_000_000 + i * step_ns
        t_recv = t_send + rtt_ns
        mid = (t_send + t_recv) // 2
        t_box_us = int((mid / 1000 + offset_us) * (1 + drift_ppm / 1e6))
        out.append(SyncSample(t_send, t_recv, t_box_us))
    return out


def test_not_ready_until_min_samples():
    cs = ClockSync()
    for s in samples(0, 0, 3):
        cs.add(s)
    assert not cs.ready
    with pytest.raises(NotSynchronised):
        cs.box_to_pc_ns(0)


def test_offset_only_converts_within_tolerance():
    cs = ClockSync()
    for s in samples(offset_us=5_000_000, drift_ppm=0, n=16):
        cs.add(s)
    assert cs.ready
    # pc = box - offset: box 8 s ↔ pc 3 s
    pc_ns = cs.box_to_pc_ns(8_000_000)
    assert abs(pc_ns - 3_000_000_000) < 1_000_000  # within 1 ms


def test_drift_is_fitted():
    cs = ClockSync()
    for s in samples(offset_us=0, drift_ppm=50, n=32):
        cs.add(s)
    assert abs(cs.drift_ppm - 50) < 5
    far_box_us = int(60_000_000 * (1 + 50 / 1e6))  # box reading one minute out
    assert abs(cs.box_to_pc_ns(far_box_us) - 60_000_000_000) < 500_000  # < 0.5 ms


def test_error_is_half_best_round_trip_and_bad_samples_are_ignored():
    cs = ClockSync()
    for s in samples(0, 0, 12, rtt_ns=300_000):
        cs.add(s)
    # Two slow, badly-timed replies (e.g. USB stall) must not move the fit.
    cs.add(SyncSample(10_000_000_000, 10_050_000_000, 10_000_000 + 40_000))
    cs.add(SyncSample(10_250_000_000, 10_300_000_000, 10_250_000 - 40_000))
    assert cs.error_ms == pytest.approx(0.15, abs=0.01)
    assert abs(cs.box_to_pc_ns(20_000_000) - 20_000_000_000) < 300_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_clocksync.py -q`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

`src/wpcap/clocksync.py`:
```python
"""Convert sync-box timestamps (its microsecond timer) to PC monotonic nanoseconds.

The PC asks the box for its time repeatedly. Each exchange gives (send, receive, box time).
The box time is assumed to correspond to the midpoint of the round trip. We keep the
exchanges with the shortest round trips (least uncertainty) and fit offset and drift.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


class NotSynchronised(Exception):
    """Asked to convert a time before enough sync exchanges have happened."""


@dataclass(frozen=True)
class SyncSample:
    t_send_ns: int
    t_recv_ns: int
    t_box_us: int

    @property
    def rtt_ns(self) -> int:
        return self.t_recv_ns - self.t_send_ns

    @property
    def mid_ns(self) -> int:
        return (self.t_send_ns + self.t_recv_ns) // 2


class ClockSync:
    def __init__(self, window: int = 32, keep_best: int = 8, min_samples: int = 4) -> None:
        if keep_best < 2 or min_samples < 2 or window < keep_best:
            raise ValueError("window >= keep_best >= 2 and min_samples >= 2 required")
        self._samples: deque[SyncSample] = deque(maxlen=window)
        self._keep_best = keep_best
        self._min_samples = min_samples
        self._slope = 1.0
        self._intercept_ns = 0.0
        self._error_ms = float("inf")

    @property
    def ready(self) -> bool:
        return len(self._samples) >= self._min_samples

    @property
    def error_ms(self) -> float:
        return self._error_ms

    @property
    def drift_ppm(self) -> float:
        return (self._slope - 1.0) * 1e6

    def add(self, sample: SyncSample) -> None:
        if sample.rtt_ns < 0:
            raise ValueError(f"negative round trip: {sample}")
        self._samples.append(sample)
        self._fit()

    def _fit(self) -> None:
        best = sorted(self._samples, key=lambda s: s.rtt_ns)[: self._keep_best]
        self._error_ms = best[0].rtt_ns / 2 / 1e6
        if len(best) < 2:
            self._slope = 1.0
            self._intercept_ns = best[0].mid_ns - best[0].t_box_us * 1000
            return
        xs = [s.t_box_us * 1000 for s in best]
        ys = [s.mid_ns for s in best]
        x0, y0 = xs[0], ys[0]  # centre to keep the arithmetic in float range
        dx = [x - x0 for x in xs]
        dy = [y - y0 for y in ys]
        n = len(best)
        mx = sum(dx) / n
        my = sum(dy) / n
        sxx = sum((x - mx) ** 2 for x in dx)
        if sxx == 0:
            self._slope = 1.0
        else:
            sxy = sum((x - mx) * (y - my) for x, y in zip(dx, dy, strict=True))
            self._slope = sxy / sxx
        self._intercept_ns = (y0 + my) - self._slope * (x0 + mx)

    def box_to_pc_ns(self, t_box_us: int) -> int:
        if not self.ready:
            raise NotSynchronised(f"{len(self._samples)} of {self._min_samples} samples")
        return round(self._intercept_ns + self._slope * (t_box_us * 1000))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass. If `test_drift_is_fitted` is off by more than the tolerance, the bug is in `_fit` centring, not in the test.

- [ ] **Step 5: Commit**

```bash
git add src/wpcap/clocksync.py tests/test_clocksync.py
git commit -m "feat: ClockSync fits offset and drift from best round trips"
```

---

### Task 5: Simulated transport, simulated sync box, and the SyncBoxLink

**Files:**
- Create: `src/wpcap/sim/__init__.py`, `src/wpcap/sim/transport.py`, `src/wpcap/sim/syncbox.py`, `src/wpcap/synclink.py`, `tests/test_sim_syncbox.py`, `tests/test_synclink.py`

**Interfaces:**
- Consumes: Task 2 `Clock`, `SimClock`; Task 3 protocol; Task 4 `ClockSync`, `SyncSample`.
- Produces:
  - `class Transport(Protocol)`: `read_line() -> bytes | None` (non-blocking; a full line or None), `write(data: bytes) -> None`, `close() -> None`
  - `sim_transport_pair() -> tuple[SimTransport, SimTransport]` (what one writes, the other reads, line-buffered)
  - `class SimSyncBox(clock: SimClock, transport: Transport, serial: str = "SIM00000001", offset_us: int = 0, drift_ppm: float = 0.0, debounce_us: int = 20_000, fw_version: str = "sim-0.1")`:
    - `box_time_us() -> int` = `int((clock.now_ns()/1000 + offset_us) * (1 + drift_ppm/1e6))`
    - `close_switch() -> None` (emit `C` or `B` based on debounce), `tick() -> None` (process inbound commands, send hello once per second of box time), `seq: int`, `debounce_us: int`, `clicks_sent: int`, `bounces_sent: int`
    - `corrupt_next: bool` and `drop_next: bool` flags (tests make the link see a bad or missing message)
  - `@dataclass(frozen=True) ClickEvent(seq: int, t_box_us: int, t_pc_ns: int, interval_us: int)`
  - `class SyncBoxLink(transport: Transport, clock: Clock, clocksync: ClockSync, on_click: Callable[[ClickEvent], None], on_bounce: Callable[[int, int], None], sync_interval_ns: int = 250_000_000, hello_timeout_ns: int = 3_000_000_000)`:
    - `poll() -> None`: read all available lines, dispatch; send a time request when due. Raises `ProtocolError`, `SequenceGapError` (from protocol) and `SyncBoxSilent` (no message for `hello_timeout_ns`); these are faults for the caller to handle.
    - `serial: str | None`, `fw_version: str | None`, `clicks_before_sync: int`, `last_message_ns: int | None`, `last_interval_us: int | None`, `clocksync: ClockSync`
    - `set_debounce(us: int) -> None`
    - `on_click` / `on_bounce` are public attributes so the `Machine` (Task 9) can bind itself after construction.

- [ ] **Step 1: Write the failing tests**

`tests/test_sim_syncbox.py`:
```python
from wpcap.clock import SimClock
from wpcap.protocol import (
    Bounce,
    Click,
    Hello,
    TimeReply,
    cmd_identify,
    cmd_time_request,
    decode_line,
)
from wpcap.sim.syncbox import SimSyncBox
from wpcap.sim.transport import sim_transport_pair


def make():
    clock = SimClock()
    box_side, pc_side = sim_transport_pair()
    box = SimSyncBox(clock, box_side, offset_us=1_000_000)
    return clock, box, pc_side


def read_all(t):
    out = []
    while (line := t.read_line()) is not None:
        out.append(decode_line(line))
    return out


def test_hello_on_first_tick_then_every_second():
    clock, box, pc = make()
    box.tick()
    msgs = read_all(pc)
    assert len(msgs) == 1 and isinstance(msgs[0], Hello) and msgs[0].serial == "SIM00000001"
    clock.advance(500_000_000)
    box.tick()
    assert read_all(pc) == []
    clock.advance(600_000_000)
    box.tick()
    assert isinstance(read_all(pc)[0], Hello)


def test_clicks_and_bounce_with_sequence_numbers():
    clock, box, pc = make()
    box.tick()  # hello is seq 1
    read_all(pc)
    box.close_switch()
    clock.advance(5_000_000)  # 5 ms later: bounce
    box.close_switch()
    clock.advance(120_000_000)  # 125 ms after first: real click
    box.close_switch()
    msgs = read_all(pc)
    assert [type(m) for m in msgs] == [Click, Bounce, Click]
    assert [m.seq for m in msgs] == [2, 3, 4]
    assert msgs[0].interval_us == 0
    assert msgs[2].interval_us == 125_000
    assert msgs[0].t_us == box.box_time_us() - 125_000


def test_time_request_is_answered_with_box_time_and_req_id():
    clock, box, pc = make()
    clock.set(2_000_000_000)
    pc.write(cmd_time_request(77))
    box.tick()
    msgs = [m for m in read_all(pc) if isinstance(m, TimeReply)]
    assert len(msgs) == 1 and msgs[0].t_us == 3_000_000 and msgs[0].req_id == 77


def test_identify_answers_hello():
    clock, box, pc = make()
    box.tick()
    read_all(pc)
    pc.write(cmd_identify())
    box.tick()
    assert isinstance(read_all(pc)[0], Hello)


def test_drift_changes_box_time():
    clock = SimClock()
    box_side, _ = sim_transport_pair()
    box = SimSyncBox(clock, box_side, drift_ppm=100)
    clock.set(10_000_000_000)
    assert box.box_time_us() == 10_001_000
```

`tests/test_synclink.py`:
```python
import pytest

from wpcap.clock import SimClock
from wpcap.clocksync import ClockSync
from wpcap.protocol import ProtocolError, SequenceGapError
from wpcap.sim.syncbox import SimSyncBox
from wpcap.sim.transport import sim_transport_pair
from wpcap.synclink import SyncBoxLink, SyncBoxSilent


class Rig:
    def __init__(self, **box_kwargs):
        self.clock = SimClock()
        box_side, pc_side = sim_transport_pair()
        self.box = SimSyncBox(self.clock, box_side, **box_kwargs)
        self.clicks = []
        self.bounces = []
        self.link = SyncBoxLink(
            pc_side,
            self.clock,
            ClockSync(),
            self.clicks.append,
            lambda s, t: self.bounces.append(s),
        )

    def run(self, ns: int, step_ns: int = 10_000_000):
        end = self.clock.now_ns() + ns
        while self.clock.now_ns() < end:
            self.clock.advance(step_ns)
            self.box.tick()
            self.link.poll()


def test_link_reaches_sync_and_reports_serial():
    r = Rig(offset_us=5_000_000)
    r.run(2_000_000_000)
    assert r.link.clocksync.ready
    assert r.link.serial == "SIM00000001"
    assert r.link.clocksync.error_ms < 2.0


def test_clicks_are_converted_to_pc_time():
    r = Rig(offset_us=5_000_000, drift_ppm=30)
    r.run(2_000_000_000)
    t_click = r.clock.now_ns()
    r.box.close_switch()
    r.link.poll()
    assert len(r.clicks) == 1
    assert abs(r.clicks[0].t_pc_ns - t_click) < 1_000_000
    assert r.link.last_interval_us == 0


def test_clicks_before_sync_are_counted_not_delivered():
    r = Rig()
    r.box.tick()
    r.box.close_switch()
    r.link.poll()
    assert r.clicks == []
    assert r.link.clicks_before_sync == 1


def test_bounce_is_reported_separately():
    r = Rig()
    r.run(2_000_000_000)
    r.box.close_switch()
    r.clock.advance(3_000_000)
    r.box.close_switch()
    r.link.poll()
    assert len(r.clicks) == 1 and r.bounces == [r.clicks[0].seq + 1]


def test_dropped_message_is_sequence_gap_fault():
    r = Rig()
    r.run(2_000_000_000)
    r.box.drop_next = True
    r.box.close_switch()
    r.box.close_switch()
    with pytest.raises(SequenceGapError):
        r.link.poll()


def test_corrupted_message_is_protocol_fault():
    r = Rig()
    r.run(2_000_000_000)
    r.box.corrupt_next = True
    r.box.close_switch()
    with pytest.raises(ProtocolError):
        r.link.poll()


def test_silent_box_is_fault():
    r = Rig()
    r.run(2_000_000_000)
    r.clock.advance(3_500_000_000)
    with pytest.raises(SyncBoxSilent):
        r.link.poll()


def test_set_debounce_reaches_box():
    r = Rig()
    r.link.set_debounce(50_000)
    r.box.tick()
    assert r.box.debounce_us == 50_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_sim_syncbox.py tests/test_synclink.py -q`
Expected: FAIL, modules not found.

- [ ] **Step 3: Implement the transport**

`src/wpcap/sim/__init__.py`:
```python
"""Simulated hardware: real implementations of the hardware interfaces, no real hardware."""
```

`src/wpcap/sim/transport.py`:
```python
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
```

- [ ] **Step 4: Implement the simulated sync box**

`src/wpcap/sim/syncbox.py`:
```python
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
    parse_command,
)
from wpcap.sim.transport import Transport


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
```

- [ ] **Step 5: Implement the link**

`src/wpcap/synclink.py`:
```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/wpcap/sim/__init__.py src/wpcap/sim/transport.py src/wpcap/sim/syncbox.py src/wpcap/synclink.py tests/test_sim_syncbox.py tests/test_synclink.py
git commit -m "feat: simulated sync box over in-memory transport and SyncBoxLink with clock sync"
```

---

### Task 6: Camera interface, simulated film and camera, ring buffer and frame picker

**Files:**
- Create: `src/wpcap/camera.py`, `src/wpcap/sim/film.py`, `src/wpcap/sim/camera.py`, `src/wpcap/picker.py`, `tests/test_sim_camera.py`, `tests/test_picker.py`

**Interfaces:**
- Consumes: Task 2 clocks; Task 5 `ClickEvent`.
- Produces:
  - `@dataclass(frozen=True) CameraInfo(name: str, serial: str, width: int, height: int, fps: float, mode: str)`
  - `@dataclass(frozen=True) Picture(index: int, t_ns: int, pixels: np.ndarray)` (`pixels` shape `(H, W, 3)` uint8; `__post_init__` validates shape/dtype and raises `ValueError`); property `shape -> tuple[int, int]`
  - `class CameraSource(Protocol)`: `info() -> CameraInfo`, `start(on_picture: Callable[[Picture], None]) -> None`, `stop() -> None`
  - `class SimFilm(frames: int, fps: float = 8.0, pulldown_ms: float = 30.0, switch_offset_ms: float = 0.0, leader_frames: int = 0, start_ns: int = 0, extra_clicks_after_end: int = 50)`:
    - `period_ns: int`; `frame_landed_ns(k: int) -> int` (frame k, 1-based, is still from `landed` until `landed + period - pulldown`)
    - `switch_ns(k: int) -> int` = `frame_landed_ns(k) + switch_offset` (negative offset = switch before the frame is still, like a disk set for an old camcorder)
    - `is_leader(k) -> bool`; frames 1..leader_frames are **clear leader** (rendered like an empty gate but still counted as frames)
    - `state_at(t_ns) -> tuple[int | None, bool]`: `(frame_number_or_None_for_empty_gate, moving)`. After the last frame the gate is empty forever. Before `start_ns`: `(1, False)` if frames > 0.
    - `switch_times() -> list[int]`: `switch_ns(k)` for k in 1..frames **plus** `extra_clicks_after_end` more at the same period (the motor keeps turning the disk after the film runs out, spec 6.3)
  - `class SimCamera(clock: Clock, film: SimFilm, fps: float = 60.0, width: int = 192, height: int = 108, serial: str = "SIMCAM0001")`:
    - `info()`, `start(cb)`, `stop()`; `render(t_ns: int) -> Picture` (index increments per render); `emit_until(t_ns: int) -> list[Picture]` renders every picture due up to `t_ns` and calls the callback; `started: bool`
    - module functions `encode_number(pixels, n)` / `decode_number(pixels) -> int | None` (24-bit binary in a strip of 24 cells across the top 8 rows: cell dark = 0, bright = 1; returns None when a cell is neither, i.e. blurred) and `is_blurred(pixels) -> bool`
    - Rendering: film frame = mid-grey 110 background with a brighter diagonal band whose position depends on `n` (so neighbours differ), number strip on top; **moving** = pixel average of frame n and n+1 renders (the strip cells become half-intensity where the bits differ); **empty gate / leader** = uniform 235.
  - `class RingBuffer(window_ns: int = 1_000_000_000)`: `push(p: Picture)`, `newest_t_ns: int | None`, `nearest(t_ns, untaken_only=False) -> Picture | None`, `take(index: int)`, `is_taken(index) -> bool`, `__len__`
  - `@dataclass PendingClick(click: ClickEvent, frame_number: int, target_ns: int)`
  - `@dataclass(frozen=True) Picked(pending: PendingClick, picture: Picture, offset_ns: int)`; `@dataclass(frozen=True) Failed(pending: PendingClick, reason: str)`
  - `class FramePicker(delay_ns: int, tolerance_ns: int, stall_ns: int, on_picked: Callable[[Picked], None], on_failed: Callable[[Failed], None], window_ns: int = 1_000_000_000)`:
    - `on_click(pending: PendingClick)` (sets `pending.target_ns = click.t_pc_ns + delay_ns`); `on_picture(p: Picture)`; `check(now_ns: int)`; `pending_count: int`; `delay_ns`, `tolerance_ns`, `stall_ns` attributes; `buffer: RingBuffer`
    - Resolution rule: a pending click resolves as soon as `buffer.newest_t_ns >= target + tolerance` (so the picture after the target has arrived). It takes the nearest **untaken** picture within `±tolerance`; none → `Failed("no picture within window")`. If `now_ns >= target + tolerance + stall_ns` and still unresolved → `Failed("camera stalled")`. Pending clicks resolve in order.

- [ ] **Step 1: Write the failing tests**

`tests/test_sim_camera.py`:
```python
import numpy as np
import pytest

from wpcap.camera import Picture
from wpcap.clock import SimClock
from wpcap.sim.camera import SimCamera, decode_number, encode_number, is_blurred
from wpcap.sim.film import SimFilm


def test_picture_validates_shape_and_dtype():
    with pytest.raises(ValueError):
        Picture(1, 0, np.zeros((10, 10), dtype=np.uint8))
    with pytest.raises(ValueError):
        Picture(1, 0, np.zeros((10, 10, 3), dtype=np.float32))


def test_number_strip_round_trips():
    img = np.full((108, 192, 3), 110, dtype=np.uint8)
    encode_number(img, 123_456)
    assert decode_number(img) == 123_456


def test_film_timeline():
    f = SimFilm(frames=3, fps=8.0, pulldown_ms=30.0)
    period = 125_000_000
    assert f.frame_landed_ns(1) == 0
    assert f.frame_landed_ns(2) == period
    assert f.state_at(10_000_000) == (1, False)
    assert f.state_at(period - 10_000_000) == (1, True)  # last 30 ms before frame 2 lands
    assert f.state_at(2 * period + 10_000_000) == (3, False)
    assert f.state_at(3 * period + 1) == (None, False)  # film ran out: empty gate
    assert len(f.switch_times()) == 3 + 50


def test_switch_offset_moves_clicks():
    f = SimFilm(frames=2, switch_offset_ms=-20.0)
    assert f.switch_ns(2) == f.frame_landed_ns(2) - 20_000_000


def test_camera_renders_still_blurred_and_empty():
    clock = SimClock()
    film = SimFilm(frames=2, leader_frames=0)
    cam = SimCamera(clock, film)
    still = cam.render(10_000_000)
    assert decode_number(still.pixels) == 1 and not is_blurred(still.pixels)
    moving = cam.render(125_000_000 - 5_000_000)
    assert decode_number(moving.pixels) is None and is_blurred(moving.pixels)
    empty = cam.render(10 * 125_000_000)
    assert empty.pixels.min() == 235 and empty.pixels.max() == 235


def test_leader_frames_look_empty_but_count():
    cam = SimCamera(SimClock(), SimFilm(frames=5, leader_frames=2))
    assert cam.render(10_000_000).pixels.min() == 235
    assert decode_number(cam.render(2 * 125_000_000 + 10_000_000).pixels) == 3


def test_emit_until_delivers_60_per_second_with_timestamps():
    clock = SimClock()
    cam = SimCamera(clock, SimFilm(frames=100), fps=60.0)
    got = []
    cam.start(got.append)
    cam.emit_until(999_000_000)
    assert len(got) == 60
    assert got[0].t_ns == 0 and got[1].t_ns - got[0].t_ns == pytest.approx(16_666_667, abs=1)
    assert [p.index for p in got] == list(range(60))
```

`tests/test_picker.py`:
```python
import numpy as np

from wpcap.camera import Picture
from wpcap.picker import Failed, FramePicker, PendingClick, Picked, RingBuffer
from wpcap.synclink import ClickEvent

MS = 1_000_000


def pic(index: int, t_ms: float) -> Picture:
    return Picture(index, int(t_ms * MS), np.zeros((4, 4, 3), dtype=np.uint8))


def click(n: int, t_ms: float) -> PendingClick:
    return PendingClick(ClickEvent(n, 0, int(t_ms * MS), 0), n, 0)


class Harness:
    def __init__(self, delay_ms=0.0, tolerance_ms=25.0, stall_ms=200.0):
        self.picked: list[Picked] = []
        self.failed: list[Failed] = []
        self.p = FramePicker(
            int(delay_ms * MS),
            int(tolerance_ms * MS),
            int(stall_ms * MS),
            self.picked.append,
            self.failed.append,
        )

    def pictures(self, start_ms, end_ms, step_ms=16.0, first_index=0):
        i = first_index
        t = start_ms
        while t <= end_ms:
            self.p.on_picture(pic(i, t))
            i += 1
            t += step_ms

    def send_click(self, n, t_ms):
        self.p.on_click(click(n, t_ms))


def test_ring_buffer_keeps_window_and_finds_nearest():
    rb = RingBuffer(window_ns=100 * MS)
    for i in range(20):
        rb.push(pic(i, i * 16))
    assert rb.newest_t_ns == 19 * 16 * MS
    assert len(rb) == 7  # 304 - 100 = 204 → indices 13..19
    assert rb.nearest(300 * MS).index == 19
    assert rb.nearest(250 * MS).index == 16  # 256 is nearer than 240


def test_picks_nearest_picture_to_click_plus_delay():
    h = Harness(delay_ms=10)
    h.pictures(0, 200)
    h.send_click(1, 100)  # target 110 → picture at 112 (index 7)
    assert len(h.picked) == 1 and h.picked[0].picture.index == 7
    assert h.picked[0].offset_ns == 2 * MS


def test_resolution_waits_for_picture_after_target():
    h = Harness(delay_ms=0)
    h.pictures(0, 96)  # newest 96
    h.send_click(1, 100)  # target 100; newest < 125 → wait
    assert h.picked == [] and h.p.pending_count == 1
    h.pictures(112, 128, first_index=7)
    assert len(h.picked) == 1 and h.picked[0].picture.index == 6  # 96 (4 away) vs 112 (12 away)


def test_click_with_empty_buffer_fails():
    h = Harness()
    h.send_click(1, 100)
    h.p.check(now_ns=400 * MS)
    assert [f.reason for f in h.failed] == ["camera stalled"]


def test_no_picture_within_window_fails():
    h = Harness(tolerance_ms=25)
    h.pictures(0, 48)
    h.pictures(200, 300, first_index=100)  # 150 ms gap
    h.send_click(1, 100)
    assert [f.reason for f in h.failed] == ["no picture within window"]


def test_picture_never_reused():
    h = Harness(tolerance_ms=25)
    h.pictures(0, 200)
    h.send_click(1, 100)  # nearest: index 6 at 96
    h.send_click(2, 101)  # index 6 is taken; next nearest untaken is index 7 at 112
    assert [p.picture.index for p in h.picked] == [6, 7]
    assert h.failed == []
    h.send_click(3, 99)  # 96 and 112 taken; 80 is 19 away (within 25) → index 5
    assert h.picked[-1].picture.index == 5
    h.send_click(4, 98)  # nearest untaken is 64 at 34 away → fails
    assert [f.reason for f in h.failed] == ["no picture within window"]


def test_stall_after_target_fails():
    h = Harness(stall_ms=200)
    h.pictures(0, 96)
    h.send_click(1, 100)
    h.p.check(now_ns=300 * MS)
    assert h.picked == []
    h.p.check(now_ns=326 * MS)
    assert [f.reason for f in h.failed] == ["camera stalled"]


def test_delay_can_be_changed_between_clicks():
    h = Harness(delay_ms=0)
    h.pictures(0, 300)
    h.send_click(1, 100)
    h.p.delay_ns = 40 * MS
    h.send_click(2, 100)
    assert [p.picture.index for p in h.picked] == [6, 9]  # 96 then 144
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_sim_camera.py tests/test_picker.py -q`
Expected: FAIL, modules not found.

- [ ] **Step 3: Implement the camera interface**

`src/wpcap/camera.py`:
```python
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
```

- [ ] **Step 4: Implement the simulated film**

`src/wpcap/sim/film.py`:
```python
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
```

- [ ] **Step 5: Implement the simulated camera**

`src/wpcap/sim/camera.py`:
```python
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
```

Note: blurred pictures of consecutive frames whose numbers share bits can decode to a valid number if every differing bit happens to be... no: any differing bit renders at 127, which is in the "neither" band, and consecutive numbers always differ in at least the lowest bit. So `decode_number` returns None for every moving picture.

- [ ] **Step 6: Implement the ring buffer and picker**

`src/wpcap/picker.py`:
```python
"""Pick one picture per click: the one whose timestamp is nearest click time + delay."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from wpcap.camera import Picture
from wpcap.synclink import ClickEvent


class RingBuffer:
    def __init__(self, window_ns: int = 1_000_000_000) -> None:
        self._window = window_ns
        self._pics: deque[Picture] = deque()
        self._taken: set[int] = set()

    def push(self, p: Picture) -> None:
        if self._pics and p.t_ns < self._pics[-1].t_ns:
            raise ValueError(f"picture {p.index} is older than the newest in the buffer")
        self._pics.append(p)
        while self._pics and self._pics[0].t_ns < p.t_ns - self._window:
            old = self._pics.popleft()
            self._taken.discard(old.index)

    @property
    def newest_t_ns(self) -> int | None:
        return self._pics[-1].t_ns if self._pics else None

    def nearest(self, t_ns: int, untaken_only: bool = False) -> Picture | None:
        best = None
        for p in self._pics:
            if untaken_only and p.index in self._taken:
                continue
            if best is None or abs(p.t_ns - t_ns) < abs(best.t_ns - t_ns):
                best = p
        return best

    def take(self, index: int) -> None:
        self._taken.add(index)

    def is_taken(self, index: int) -> bool:
        return index in self._taken

    def __len__(self) -> int:
        return len(self._pics)


@dataclass
class PendingClick:
    click: ClickEvent
    frame_number: int
    target_ns: int


@dataclass(frozen=True)
class Picked:
    pending: PendingClick
    picture: Picture
    offset_ns: int


@dataclass(frozen=True)
class Failed:
    pending: PendingClick
    reason: str


class FramePicker:
    def __init__(
        self,
        delay_ns: int,
        tolerance_ns: int,
        stall_ns: int,
        on_picked: Callable[[Picked], None],
        on_failed: Callable[[Failed], None],
        window_ns: int = 1_000_000_000,
    ) -> None:
        if tolerance_ns <= 0 or stall_ns <= 0:
            raise ValueError("tolerance and stall must be positive")
        self.delay_ns = delay_ns
        self.tolerance_ns = tolerance_ns
        self.stall_ns = stall_ns
        self._on_picked = on_picked
        self._on_failed = on_failed
        self.buffer = RingBuffer(window_ns)
        self._pending: deque[PendingClick] = deque()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def on_click(self, pending: PendingClick) -> None:
        pending.target_ns = pending.click.t_pc_ns + self.delay_ns
        self._pending.append(pending)
        self._resolve()

    def on_picture(self, p: Picture) -> None:
        self.buffer.push(p)
        self._resolve()

    def check(self, now_ns: int) -> None:
        self._resolve()
        while self._pending:
            head = self._pending[0]
            if now_ns >= head.target_ns + self.tolerance_ns + self.stall_ns:
                self._pending.popleft()
                self._on_failed(Failed(head, "camera stalled"))
            else:
                break

    def _resolve(self) -> None:
        while self._pending:
            head = self._pending[0]
            newest = self.buffer.newest_t_ns
            if newest is None or newest < head.target_ns + self.tolerance_ns:
                return
            self._pending.popleft()
            p = self.buffer.nearest(head.target_ns, untaken_only=True)
            if p is None or abs(p.t_ns - head.target_ns) > self.tolerance_ns:
                self._on_failed(Failed(head, "no picture within window"))
                continue
            self.buffer.take(p.index)
            self._on_picked(Picked(head, p, p.t_ns - head.target_ns))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/wpcap/camera.py src/wpcap/sim/film.py src/wpcap/sim/camera.py src/wpcap/picker.py tests/test_sim_camera.py tests/test_picker.py
git commit -m "feat: camera interface, simulated film and camera, ring buffer and frame picker"
```

---

### Task 7: Reel folder, journal, saver worker and accounting

**Files:**
- Create: `src/wpcap/reel.py`, `src/wpcap/saver.py`, `tests/test_reel.py`, `tests/test_saver.py`

**Interfaces:**
- Consumes: Task 6 `Picture`; Task 2 `Clock`.
- Produces:
  - `class ReelFolder`: `ReelFolder.create(root: Path, name: str) -> ReelFolder` (makes `name/`, `frames/`, `neighbours/`, `exports/`; if `root/name` exists, uses `name (2)`, `name (3)`…; `name` must not be empty or contain `/` or `\`); `ReelFolder.open(path) -> ReelFolder` (raises `FileNotFoundError`); attributes `path`, `name`, `frames_dir`, `journal_path`, `reel_json_path`; `frame_path(n: int) -> Path` (`frames/000001.png`); `write_reel_json(data: dict)`, `read_reel_json() -> dict`
  - `class JournalCorrupt(Exception)` with `line_number`
  - `class Journal(path: Path)`: `append(event: dict) -> None` (caller supplies `"type"` and `"t_ns"`; raises `ValueError` if missing; one JSON line, flushed); `read_all() -> list[dict]` (raises `JournalCorrupt` on any bad line, including a truncated last line); `read_all_tolerant() -> tuple[list[dict], bool]` (tolerates only a truncated last line without a newline; returns `truncated=True`)
  - `class AccountingError(Exception)`; `class Accounting`: counters `clicks_accepted`, `saved`, `pending`, `failed`; methods `click()`, `saved_one()`, `failed_one()`; `balanced() -> bool`; `assert_balanced()`; `as_dict()`
  - `class QueueFull(Exception)`
  - `class Saver(folder: ReelFolder, journal: Journal, clock: Clock, queue_size: int, on_error: Callable[[int, Exception], None], on_saved: Callable[[int], None])`: `start()`, `submit(frame_number: int, picture: Picture) -> None` (raises `QueueFull` immediately when the queue is full; raises `FileExistsError` if the frame file exists), `join(timeout_s: float) -> None` (waits for the queue to drain, raises `TimeoutError`), `stop()`, `pending: int`, `saved: int`, `errors: int`, `alive: bool`. Worker writes `frames/NNNNNN.png.tmp` with Pillow (`compress_level=1`), then `os.replace` to `NNNNNN.png`, then journals `{"type": "saved", "frame": n, "picture_index": i, "t_pic_ns": t, "t_ns": now}`, then calls `on_saved(n)`. On any exception: remove the tmp file if present, journal `{"type": "failed", "frame": n, "reason": "write error: ...", "t_ns": now}`, call `on_error(n, exc)`, keep running.

- [ ] **Step 1: Write the failing tests**

`tests/test_reel.py`:
```python
import json

import pytest

from wpcap.reel import Journal, JournalCorrupt, ReelFolder


def test_create_makes_layout(tmp_path):
    r = ReelFolder.create(tmp_path, "WorkPrinter 1 — 2026-10-30 1800")
    assert r.path == tmp_path / "WorkPrinter 1 — 2026-10-30 1800"
    for sub in ("frames", "neighbours", "exports"):
        assert (r.path / sub).is_dir()
    assert r.frame_path(1) == r.path / "frames" / "000001.png"
    assert r.frame_path(123456) == r.path / "frames" / "123456.png"


def test_reel_folder_name_collision_gets_suffix(tmp_path):
    a = ReelFolder.create(tmp_path, "Reel")
    b = ReelFolder.create(tmp_path, "Reel")
    c = ReelFolder.create(tmp_path, "Reel")
    assert (a.name, b.name, c.name) == ("Reel", "Reel (2)", "Reel (3)")
    assert a.path.exists() and b.path.exists() and c.path.exists()


def test_bad_names_rejected(tmp_path):
    with pytest.raises(ValueError):
        ReelFolder.create(tmp_path, "a/b")
    with pytest.raises(ValueError):
        ReelFolder.create(tmp_path, "")


def test_open_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ReelFolder.open(tmp_path / "nope")


def test_reel_json_round_trip(tmp_path):
    r = ReelFolder.create(tmp_path, "Reel")
    r.write_reel_json({"name": "Reel", "machine": "WorkPrinter 1"})
    assert r.read_reel_json() == {"name": "Reel", "machine": "WorkPrinter 1"}


def test_journal_append_and_read(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    j.append({"type": "click", "t_ns": 1, "seq": 5})
    j.append({"type": "saved", "t_ns": 2, "frame": 1})
    assert j.read_all() == [
        {"type": "click", "t_ns": 1, "seq": 5},
        {"type": "saved", "t_ns": 2, "frame": 1},
    ]


def test_journal_requires_type_and_time(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    with pytest.raises(ValueError):
        j.append({"type": "click"})
    with pytest.raises(ValueError):
        j.append({"t_ns": 1})


def test_journal_corrupt_middle_line_raises(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text(
        json.dumps({"type": "a", "t_ns": 1}) + "\n{not json\n" + json.dumps({"type": "b", "t_ns": 2}) + "\n"
    )
    with pytest.raises(JournalCorrupt) as e:
        Journal(p).read_all()
    assert e.value.line_number == 2


def test_journal_truncated_last_line_is_tolerated_only_by_tolerant_reader(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text(json.dumps({"type": "a", "t_ns": 1}) + "\n" + '{"type": "b", "t_ns": 2')
    with pytest.raises(JournalCorrupt):
        Journal(p).read_all()
    events, truncated = Journal(p).read_all_tolerant()
    assert events == [{"type": "a", "t_ns": 1}] and truncated
```

`tests/test_saver.py`:
```python
import os
import stat

import numpy as np
import pytest
from PIL import Image

from wpcap.camera import Picture
from wpcap.clock import SystemClock
from wpcap.reel import Journal, ReelFolder
from wpcap.saver import Accounting, AccountingError, QueueFull, Saver


def pic(i: int, level: int = 100) -> Picture:
    return Picture(i, i * 1_000_000, np.full((16, 24, 3), level, dtype=np.uint8))


def make(tmp_path, queue_size=120):
    folder = ReelFolder.create(tmp_path, "Reel")
    journal = Journal(folder.journal_path)
    errors = []
    saved = []
    s = Saver(
        folder, journal, SystemClock(), queue_size,
        lambda n, e: errors.append((n, e)), saved.append,
    )
    return folder, journal, s, errors, saved


def test_saves_png_then_journals(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path)
    s.start()
    s.submit(1, pic(10, 77))
    s.join(5)
    s.stop()
    assert errors == [] and saved == [1]
    img = np.asarray(Image.open(folder.frame_path(1)))
    assert img.shape == (16, 24, 3) and img.min() == 77 and img.max() == 77
    assert not list(folder.frames_dir.glob("*.tmp"))
    ev = journal.read_all()
    assert ev[-1]["type"] == "saved" and ev[-1]["frame"] == 1 and ev[-1]["picture_index"] == 10
    assert s.saved == 1 and s.pending == 0


def test_queue_full_raises_immediately(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path, queue_size=2)
    # not started: nothing drains
    s.submit(1, pic(1))
    s.submit(2, pic(2))
    with pytest.raises(QueueFull):
        s.submit(3, pic(3))


def test_never_overwrites_existing_frame(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path)
    folder.frame_path(1).write_bytes(b"existing")
    s.start()
    with pytest.raises(FileExistsError):
        s.submit(1, pic(1))
    s.stop()
    assert folder.frame_path(1).read_bytes() == b"existing"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_write_error_is_fault_not_half_frame(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path)
    s.start()
    s.submit(1, pic(1))
    s.join(5)
    os.chmod(folder.frames_dir, stat.S_IRUSR | stat.S_IXUSR)  # read-only: next write fails
    try:
        s.submit(2, pic(2))
        s.join(5)
    finally:
        os.chmod(folder.frames_dir, stat.S_IRWXU)
    s.stop()
    assert len(errors) == 1 and errors[0][0] == 2
    assert not folder.frame_path(2).exists()
    assert not list(folder.frames_dir.glob("*.tmp"))
    ev = journal.read_all()
    assert ev[-1]["type"] == "failed" and ev[-1]["frame"] == 2 and "write error" in ev[-1]["reason"]
    assert s.errors == 1 and s.saved == 1


def test_accounting_balances():
    a = Accounting()
    a.click()
    a.click()
    a.click()
    assert a.pending == 3 and a.balanced()
    a.saved_one()
    a.failed_one()
    assert (a.saved, a.failed, a.pending) == (1, 1, 1) and a.balanced()
    a.saved = 5
    assert not a.balanced()
    with pytest.raises(AccountingError):
        a.assert_balanced()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_reel.py tests/test_saver.py -q`
Expected: FAIL, modules not found.

- [ ] **Step 3: Implement reel folder and journal**

`src/wpcap/reel.py`:
```python
"""Reel folder layout (spec 7.2) and the append-only journal."""

from __future__ import annotations

import json
from pathlib import Path


class JournalCorrupt(Exception):
    def __init__(self, path: Path, line_number: int) -> None:
        super().__init__(f"journal {path} line {line_number} is not valid JSON")
        self.line_number = line_number


class ReelFolder:
    SUBDIRS = ("frames", "neighbours", "exports")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name
        self.frames_dir = path / "frames"
        self.journal_path = path / "journal.jsonl"
        self.reel_json_path = path / "reel.json"

    @classmethod
    def create(cls, root: Path, name: str) -> ReelFolder:
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"bad reel name: {name!r}")
        root.mkdir(parents=True, exist_ok=True)
        candidate = root / name
        n = 2
        while candidate.exists():
            candidate = root / f"{name} ({n})"
            n += 1
        candidate.mkdir()
        for sub in cls.SUBDIRS:
            (candidate / sub).mkdir()
        return cls(candidate)

    @classmethod
    def open(cls, path: Path) -> ReelFolder:
        if not (path / "frames").is_dir():
            raise FileNotFoundError(f"not a reel folder: {path}")
        return cls(path)

    def frame_path(self, n: int) -> Path:
        if n < 1:
            raise ValueError("frames are numbered from 1")
        return self.frames_dir / f"{n:06d}.png"

    def write_reel_json(self, data: dict) -> None:
        tmp = self.reel_json_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.reel_json_path)

    def read_reel_json(self) -> dict:
        return json.loads(self.reel_json_path.read_text(encoding="utf-8"))


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: dict) -> None:
        if "type" not in event or "t_ns" not in event:
            raise ValueError(f"journal event needs 'type' and 't_ns': {event}")
        line = json.dumps(event, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    def read_all(self) -> list[dict]:
        events, truncated = self._read()
        if truncated:
            raise JournalCorrupt(self.path, len(events) + 1)
        return events

    def read_all_tolerant(self) -> tuple[list[dict], bool]:
        return self._read()

    def _read(self) -> tuple[list[dict], bool]:
        if not self.path.exists():
            return [], False
        text = self.path.read_text(encoding="utf-8")
        ends_with_newline = text.endswith("\n")
        lines = text.split("\n")
        if ends_with_newline:
            lines = lines[:-1]
        events: list[dict] = []
        for i, line in enumerate(lines, start=1):
            is_last = i == len(lines)
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                if is_last and not ends_with_newline:
                    return events, True
                raise JournalCorrupt(self.path, i) from e
        return events, False
```

- [ ] **Step 4: Implement the saver and accounting**

`src/wpcap/saver.py`:
```python
"""Save frames to disk in a worker thread with a fixed-size queue (spec 7.1)."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

from PIL import Image

from wpcap.camera import Picture
from wpcap.clock import Clock
from wpcap.reel import Journal, ReelFolder


class QueueFull(Exception):
    """The save queue is full: the disk is not keeping up. This is a fault, not a drop."""


class AccountingError(Exception):
    pass


class Accounting:
    def __init__(self) -> None:
        self.clicks_accepted = 0
        self.saved = 0
        self.pending = 0
        self.failed = 0

    def click(self) -> None:
        self.clicks_accepted += 1
        self.pending += 1

    def saved_one(self) -> None:
        self.pending -= 1
        self.saved += 1

    def failed_one(self) -> None:
        self.pending -= 1
        self.failed += 1

    def balanced(self) -> bool:
        total = self.saved + self.pending + self.failed
        return self.clicks_accepted == total and self.pending >= 0

    def assert_balanced(self) -> None:
        if not self.balanced():
            raise AccountingError(
                f"clicks {self.clicks_accepted} != saved {self.saved} + pending {self.pending}"
                f" + failed {self.failed}"
            )

    def as_dict(self) -> dict:
        return {
            "clicks_accepted": self.clicks_accepted,
            "saved": self.saved,
            "pending": self.pending,
            "failed": self.failed,
        }


class Saver:
    def __init__(
        self,
        folder: ReelFolder,
        journal: Journal,
        clock: Clock,
        queue_size: int,
        on_error: Callable[[int, Exception], None],
        on_saved: Callable[[int], None],
    ) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be at least 1")
        self._folder = folder
        self._journal = journal
        self._clock = clock
        self._on_error = on_error
        self._on_saved = on_saved
        self._q: queue.Queue[tuple[int, Picture] | None] = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.saved = 0
        self.errors = 0
        self._submitted = 0

    @property
    def pending(self) -> int:
        with self._lock:
            return self._submitted - self.saved - self.errors

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("saver already started")
        self._thread = threading.Thread(target=self._run, name="saver", daemon=True)
        self._thread.start()

    def submit(self, frame_number: int, picture: Picture) -> None:
        path = self._folder.frame_path(frame_number)
        if path.exists():
            raise FileExistsError(f"frame already exists: {path}")
        try:
            self._q.put_nowait((frame_number, picture))
        except queue.Full as e:
            raise QueueFull(f"save queue full ({self._q.maxsize}) at frame {frame_number}") from e
        with self._lock:
            self._submitted += 1

    def join(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while self.pending > 0:
            if not self.alive:
                raise RuntimeError(f"saver thread is not running with {self.pending} frames queued")
            if time.monotonic() > deadline:
                raise TimeoutError(f"saver still has {self.pending} frames after {timeout_s} s")
            time.sleep(0.005)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._q.put(None)
        self._thread.join(timeout=10)
        self._thread = None

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            frame_number, picture = item
            self._save(frame_number, picture)

    def _save(self, frame_number: int, picture: Picture) -> None:
        path = self._folder.frame_path(frame_number)
        tmp = path.with_name(path.name + ".tmp")
        try:
            Image.fromarray(picture.pixels, mode="RGB").save(tmp, format="PNG", compress_level=1)
            tmp.replace(path)
            self._journal.append(
                {
                    "type": "saved",
                    "t_ns": self._clock.now_ns(),
                    "frame": frame_number,
                    "picture_index": picture.index,
                    "t_pic_ns": picture.t_ns,
                }
            )
            with self._lock:
                self.saved += 1
            self._on_saved(frame_number)
        except Exception as exc:  # noqa: BLE001 - every failure is journaled and reported upward
            if tmp.exists():
                tmp.unlink()
            with self._lock:
                self.errors += 1
            self._journal.append(
                {
                    "type": "failed",
                    "t_ns": self._clock.now_ns(),
                    "frame": frame_number,
                    "reason": f"write error: {exc}",
                }
            )
            self._on_error(frame_number, exc)
```

Note on the broad `except`: it is the one place the spec requires every failure to be caught, journaled and reported upward (`on_error`), never swallowed. If the journal append inside the handler itself fails (disk full), the exception propagates and ends the worker thread; `Saver.alive` goes false and the `Machine` (Task 9) turns that into a storage fault. That is the correct fail-fast behaviour.

- [ ] **Step 5: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/wpcap/reel.py src/wpcap/saver.py tests/test_reel.py tests/test_saver.py
git commit -m "feat: reel folder, journal, saver worker with temp-then-rename, accounting"
```

---

### Task 8: End-of-reel gate detector and exposure watcher

**Files:**
- Create: `src/wpcap/gate.py`, `tests/test_gate.py`

**Interfaces:**
- Consumes: nothing beyond numpy.
- Produces:
  - `is_empty_gate(pixels, bright_min: int, std_max: float) -> bool` (mean ≥ bright_min and std ≤ std_max, on a 1/4-scale subsample)
  - `class GateDetector(bright_min: int = 200, std_max: float = 8.0, empty_needed: int = 24, min_frames_before: int = 100)`: `observe(frame_number: int, pixels) -> bool` returns `True` exactly once when the reel is finished; `empty_run: int`; `picture_frames_seen: int`; `finished: bool`; `reset()`.
    Rule: an empty frame while `picture_frames_seen < min_frames_before` is leader and ignored; once `picture_frames_seen >= min_frames_before`, `empty_needed` consecutive empty frames finish the reel. A non-empty frame resets `empty_run`.
  - `class ExposureWatcher(window: int = 30, jump: float = 25.0)`: `observe(pixels) -> float | None` returns the jump size when the mean brightness differs from the rolling mean of the previous `window` pictures by more than `jump`, else None. Empty-gate pictures are not fed to it (the caller decides).

- [ ] **Step 1: Write the failing tests**

`tests/test_gate.py`:
```python
import numpy as np

from wpcap.gate import ExposureWatcher, GateDetector, is_empty_gate


def flat(level):
    return np.full((54, 96, 3), level, dtype=np.uint8)


def textured(level=110):
    img = np.full((54, 96, 3), level, dtype=np.uint8)
    img[:, ::2, :] = level + 60
    return img


def test_is_empty_gate():
    assert is_empty_gate(flat(235), 200, 8.0)
    assert not is_empty_gate(flat(120), 200, 8.0)
    assert not is_empty_gate(textured(190), 200, 8.0)


def test_leader_at_start_does_not_finish():
    g = GateDetector(empty_needed=5, min_frames_before=10)
    for k in range(1, 40):
        assert g.observe(k, flat(235)) is False
    assert not g.finished and g.picture_frames_seen == 0


def test_empty_gate_after_pictures_finishes_once():
    g = GateDetector(empty_needed=5, min_frames_before=10)
    k = 0
    for _ in range(10):
        k += 1
        assert g.observe(k, textured()) is False
    results = []
    for _ in range(7):
        k += 1
        results.append(g.observe(k, flat(235)))
    assert results == [False, False, False, False, True, False, False]
    assert g.finished


def test_non_empty_frame_resets_run():
    g = GateDetector(empty_needed=3, min_frames_before=2)
    g.observe(1, textured())
    g.observe(2, textured())
    g.observe(3, flat(235))
    g.observe(4, flat(235))
    assert g.empty_run == 2
    g.observe(5, textured())
    assert g.empty_run == 0
    assert g.observe(6, flat(235)) is False


def test_exposure_watcher_flags_jump_only():
    w = ExposureWatcher(window=5, jump=25.0)
    for _ in range(5):
        assert w.observe(flat(100)) is None
    assert w.observe(flat(110)) is None
    j = w.observe(flat(160))
    assert j is not None and j > 25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_gate.py -q`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

`src/wpcap/gate.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/wpcap/gate.py tests/test_gate.py
git commit -m "feat: end-of-reel gate detector and exposure drift watcher"
```

---

### Task 9: The Machine state machine (ties everything together)

**Files:**
- Create: `src/wpcap/machine.py`, `src/wpcap/sim/rig.py`, `tests/test_machine.py`

**Interfaces:**
- Consumes: Tasks 2–8.
- Produces:
  - `class MachineState(StrEnum)`: `NOT_READY`, `READY`, `RECORDING`, `REEL_FINISHED`, `STOPPED`
  - `@dataclass(frozen=True) Fault(kind: str, message: str, action: str)` with `kind` in `{"camera", "missed_frame", "storage", "sync", "sync_box", "operator", "accounting"}`
  - `class Alerter(Protocol)`: `alert(level: str, title: str, message: str) -> None` (`level` in `{"info", "warning", "problem"}`); `class RecordingAlerter` (`alerts: list[tuple[str, str, str]]`) in the same module for tests and Demo Mode
  - `@dataclass MachineConfig(name: str, reel_root: Path, delay_ms: float = 0.0, tolerance_ms: float = 25.0, stall_ms: float = 200.0, debounce_us: int = 20_000, sync_error_limit_ms: float = 2.0, save_queue: int = 120, gate_bright_min: int = 200, gate_std_max: float = 8.0, gate_empty_needed: int = 24, gate_min_frames: int = 100, exposure_jump: float = 25.0, min_free_bytes: int = 2 * 1024**3, max_interval_ratio: float = 2.0)`
  - `@dataclass ReelMeta(name: str | None = None, film_type: str = "super8", notes: str = "", customer: str = "", job_number: str = "")`
  - `@dataclass(frozen=True) MachineStatus(state, reel_name, segment, frames_saved, frames_failed, frames_pending, clicks, bounces, fps, sync_error_ms, free_bytes, last_fault, warnings: tuple[str, ...])`
  - `class Machine(config: MachineConfig, clock: Clock, link: SyncBoxLink, camera: CameraSource, alerter: Alerter, free_bytes: Callable[[Path], int] = _free_bytes, wall_clock: Callable[[], datetime] = datetime.now)`:
    - `start() -> None` (starts the camera, sends the debounce setting), `shutdown()` (stops the camera, drains the saver, checks accounting)
    - `on_click(ev: ClickEvent)`, `on_bounce(seq, t_us)`, `on_picture(p: Picture)` (the constructor binds the first two into the link; `start` binds the third into the camera), `tick() -> None` (call often: polls the link, picker timeouts, sync error, free space, saver health, readiness)
    - `new_reel(meta: ReelMeta) -> None` (allowed in READY / REEL_FINISHED / STOPPED; the next click starts recording into it), `stop() -> None` (operator stop → fault kind `operator`), `resume() -> None` (STOPPED → READY with the same reel, next segment)
    - `status() -> MachineStatus`; attributes `state`, `reel: ReelFolder | None`, `accounting: Accounting`, `segment: int`, `fault_history: list[Fault]`, `warnings: list[str]`, `link`
    - Behaviour:
      - NOT_READY → READY when: camera has delivered a picture, link is synced with `error_ms <= limit`, free space ≥ `min_free_bytes`, link serial known.
      - First click in READY: if no reel is open, create one named `f"{config.name} — {YYYY-MM-DD HHMM}"` (wall clock); write `reel.json` (name, machine, film type, notes, customer, job_number, created, camera info, delay, debounce, sync box serial/fw); journal `segment_start`; state RECORDING. Every accepted click: `accounting.click()`, journal `click`, hand a `PendingClick` to the picker with the next frame number.
      - Picked → journal `picked` (frame, picture_index, offset_ns), `saver.submit`; gate detector observes the picked pixels; exposure watcher observes non-empty ones. Gate finished → journal `reel_finished` + `segment_stop`, state REEL_FINISHED, alert info `"Reel finished — switch off {name}"`; further clicks journaled as `ignored_click` and not counted.
      - Failed pick → `accounting.failed_one()`, journal `failed`, fault `missed_frame`.
      - Saver error → `accounting.failed_one()` + fault `storage`. `QueueFull` / `FileExistsError` on submit → `accounting.failed_one()`, journal `failed`, fault `storage`.
      - Link raises `ProtocolError`/`SequenceGapError` → fault `sync`; `SyncBoxSilent` → fault `sync_box`; `error_ms > limit` while RECORDING → fault `sync`.
      - Click interval > `max_interval_ratio ×` the median of the last 20 intervals (once 20 are known) → fault `missed_frame` ("far too long between clicks").
      - Picture shape differs from the first picture's shape → fault `camera` ("camera changed mode"). No picture for `stall_ms` after a click's target → picker reports stall → fault `missed_frame`.
      - Free space < `min_free_bytes` while RECORDING → fault `storage`. Saver thread not alive while RECORDING → fault `storage`.
      - Any fault while RECORDING: journal `fault`, journal `segment_stop`, state STOPPED, alert problem `f"STOP {config.name} NOW"` + message + action. Faults outside RECORDING are journaled (if a reel is open) and alerted as warnings; state → NOT_READY for camera/sync/sync_box faults; `operator` in READY/REEL_FINISHED → STOPPED.
      - `resume()`: STOPPED → READY, `segment += 1`, a fresh picker (old pending clicks are gone); the next click journals `segment_start` with the new segment number and frame numbering continues from the last frame number + 1.
  - `class SimRig(config: MachineConfig, film: SimFilm, offset_us=0, drift_ppm=0.0, cam_fps=60.0, cam_size=(192, 108), free_bytes=None)`: builds `SimClock`, transport pair, `SimSyncBox`, `SimCamera`, `RecordingAlerter`, `Machine`; `run_until(t_ns, step_ns=1_000_000)`: advances virtual time in steps, at each step emits due camera pictures (if the camera is started), due switch closures (from `switch_times`), ticks the box and the machine, and drains the saver so counts are deterministic. `run_for(ns)`. `run_realtime(seconds)` for Demo Mode. Attributes: `clock`, `box`, `camera`, `machine`, `alerts`, `switch_times` (mutable, kept sorted by tests).

- [ ] **Step 1: Write the failing tests**

`tests/test_machine.py`:
```python
from pathlib import Path

import numpy as np
from PIL import Image

from wpcap.machine import MachineConfig, MachineState, ReelMeta
from wpcap.reel import Journal, ReelFolder
from wpcap.sim.camera import decode_number
from wpcap.sim.film import SimFilm
from wpcap.sim.rig import SimRig

S = 1_000_000_000


def cfg(tmp_path, **kw):
    base = dict(
        name="WorkPrinter 1", reel_root=tmp_path / "reels", gate_min_frames=20, gate_empty_needed=8
    )
    base.update(kw)
    return MachineConfig(**base)


def frame_numbers(folder: ReelFolder) -> list[int | None]:
    out = []
    for p in sorted(folder.frames_dir.glob("*.png")):
        out.append(decode_number(np.asarray(Image.open(p))))
    return out


def test_becomes_ready_after_sync_and_first_picture(tmp_path):
    rig = SimRig(cfg(tmp_path), SimFilm(frames=0, start_ns=10 * S))
    assert rig.machine.status().state == MachineState.NOT_READY
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.READY


def test_scans_every_frame_once_in_order(tmp_path):
    film = SimFilm(frames=200, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 260 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.REEL_FINISHED
    assert st.frames_failed == 0
    assert st.frames_saved == 200 + 8  # 200 pictures + the 8 empty frames that proved the end
    rig.machine.shutdown()
    nums = frame_numbers(ReelFolder.open(rig.machine.reel.path))
    assert nums[:200] == list(range(1, 201))
    assert all(n is None for n in nums[200:])  # empty gate frames
    assert any("Reel finished" in a[1] for a in rig.alerts)
    assert rig.machine.accounting.balanced()


def test_delay_absorbs_switch_offset(tmp_path):
    # Switch closes 40 ms before the frame is still (old timing-disk setting).
    film = SimFilm(frames=60, start_ns=3 * S, switch_offset_ms=-40.0)
    rig = SimRig(cfg(tmp_path, delay_ms=45.0), film)
    rig.run_until(3 * S + 70 * film.period_ns)
    rig.machine.shutdown()
    nums = frame_numbers(ReelFolder.open(rig.machine.reel.path))
    assert nums[:60] == list(range(1, 61))


def test_wrong_delay_lands_on_blur_and_is_visible(tmp_path):
    film = SimFilm(frames=30, start_ns=3 * S, switch_offset_ms=-20.0)
    rig = SimRig(cfg(tmp_path, delay_ms=0.0), film)  # click is 20 ms before still → blurred
    rig.run_until(3 * S + 40 * film.period_ns)
    rig.machine.shutdown()
    nums = frame_numbers(ReelFolder.open(rig.machine.reel.path))
    assert nums[:30].count(None) > 20


def test_leader_does_not_finish_reel(tmp_path):
    film = SimFilm(frames=80, leader_frames=30, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, gate_min_frames=20), film)
    rig.run_until(3 * S + 40 * film.period_ns)
    assert rig.machine.status().state == MachineState.RECORDING


def test_bounce_is_counted_not_saved(tmp_path):
    film = SimFilm(frames=20, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.switch_times.insert(5, film.switch_ns(5) + 3_000_000)  # 3 ms after click 5
    rig.run_until(3 * S + 30 * film.period_ns)
    st = rig.machine.status()
    assert st.bounces == 1 and st.frames_saved >= 20 and st.frames_failed == 0


def test_dropped_sync_message_is_fault_and_frames_kept(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 50 * film.period_ns)
    rig.box.drop_next = True
    rig.run_until(3 * S + 60 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "sync"
    assert st.frames_saved >= 49
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    rig.machine.shutdown()
    assert rig.machine.accounting.balanced()


def test_missing_click_is_missed_frame_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    del rig.switch_times[40:43]  # three clicks never happen: 500 ms gap
    rig.run_until(3 * S + 60 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "missed_frame"


def test_camera_stall_is_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.camera.stop()  # no more pictures
    rig.run_until(3 * S + 40 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "missed_frame"
    assert st.frames_failed >= 1


def test_camera_mode_change_is_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.camera.width, rig.camera.height = 96, 54
    rig.run_until(3 * S + 32 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "camera"


def test_operator_stop_then_resume_continues_numbering(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.machine.stop()
    assert rig.machine.status().state == MachineState.STOPPED
    saved_before = rig.machine.status().frames_saved
    rig.run_for(2 * S)  # clicks keep coming while stopped: ignored
    rig.machine.resume()
    assert rig.machine.status().state == MachineState.READY
    rig.run_until(3 * S + 120 * film.period_ns)
    st = rig.machine.status()
    assert st.segment == 2 and st.frames_saved > saved_before
    events = Journal(rig.machine.reel.journal_path).read_all()
    assert [e["segment"] for e in events if e["type"] == "segment_start"] == [1, 2]
    first_frames = [e["first_frame"] for e in events if e["type"] == "segment_start"]
    assert first_frames[1] == saved_before + 1


def test_disk_space_keeps_machine_not_ready(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, min_free_bytes=10**15), film)
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.NOT_READY


def test_sync_error_over_limit_keeps_machine_not_ready(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, sync_error_limit_ms=0.0001), film)
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.NOT_READY


def test_new_reel_metadata_written(tmp_path):
    film = SimFilm(frames=30, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_for(2 * S)
    rig.machine.new_reel(
        ReelMeta(name="Smith wedding", customer="Smith", job_number="J-001", notes="box 2")
    )
    rig.run_until(3 * S + 5 * film.period_ns)
    meta = rig.machine.reel.read_reel_json()
    assert meta["name"] == "Smith wedding" and meta["job_number"] == "J-001"
    assert meta["camera"]["mode"].startswith("sim-rgb") and meta["delay_ms"] == 0.0
    assert rig.machine.reel.path == Path(tmp_path / "reels" / "Smith wedding")


def test_two_machines_do_not_interfere(tmp_path):
    f1 = SimFilm(frames=150, start_ns=3 * S)
    f2 = SimFilm(frames=150, start_ns=3 * S + 37_000_000)
    r1 = SimRig(cfg(tmp_path, name="WorkPrinter 1"), f1)
    r2 = SimRig(cfg(tmp_path, name="WorkPrinter 2"), f2, offset_us=123_456, drift_ppm=40)
    end = 3 * S + 170 * f1.period_ns
    while r1.clock.now_ns() < end:
        r1.run_for(10_000_000)
        r2.run_for(10_000_000)
        if r1.clock.now_ns() == 3 * S + 50 * f1.period_ns:
            r1.box.drop_next = True
    assert r1.machine.status().state == MachineState.STOPPED
    assert r2.machine.status().state == MachineState.REEL_FINISHED
    assert r2.machine.status().frames_failed == 0
    r1.machine.shutdown()
    r2.machine.shutdown()
    assert frame_numbers(ReelFolder.open(r2.machine.reel.path))[:150] == list(range(1, 151))


def test_thousand_frames_none_lost_or_doubled(tmp_path):
    film = SimFilm(frames=1000, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film, drift_ppm=25, offset_us=-777_000)
    rig.run_until(3 * S + 1040 * film.period_ns)
    rig.machine.shutdown()
    st = rig.machine.status()
    assert st.state == MachineState.REEL_FINISHED and st.frames_failed == 0
    assert frame_numbers(ReelFolder.open(rig.machine.reel.path))[:1000] == list(range(1, 1001))
    assert rig.machine.accounting.balanced()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_machine.py -q`
Expected: FAIL, modules not found.

- [ ] **Step 3: Implement the Machine**

`src/wpcap/machine.py`:
```python
"""One WorkPrinter = one Machine: the state machine that turns clicks and pictures into frames."""

from __future__ import annotations

import shutil
import statistics
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from wpcap.camera import CameraSource, Picture
from wpcap.clock import Clock
from wpcap.gate import ExposureWatcher, GateDetector, is_empty_gate
from wpcap.picker import Failed, FramePicker, PendingClick, Picked
from wpcap.protocol import ProtocolError, SequenceGapError
from wpcap.reel import Journal, ReelFolder
from wpcap.saver import Accounting, QueueFull, Saver
from wpcap.synclink import ClickEvent, SyncBoxLink, SyncBoxSilent


class MachineState(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"
    RECORDING = "recording"
    REEL_FINISHED = "reel_finished"
    STOPPED = "stopped"


FAULT_KINDS = {"camera", "missed_frame", "storage", "sync", "sync_box", "operator", "accounting"}


@dataclass(frozen=True)
class Fault:
    kind: str
    message: str
    action: str

    def __post_init__(self) -> None:
        if self.kind not in FAULT_KINDS:
            raise ValueError(f"unknown fault kind {self.kind}")


class Alerter(Protocol):
    def alert(self, level: str, title: str, message: str) -> None: ...


class RecordingAlerter:
    def __init__(self) -> None:
        self.alerts: list[tuple[str, str, str]] = []

    def alert(self, level: str, title: str, message: str) -> None:
        if level not in ("info", "warning", "problem"):
            raise ValueError(f"bad alert level {level}")
        self.alerts.append((level, title, message))


@dataclass
class MachineConfig:
    name: str
    reel_root: Path
    delay_ms: float = 0.0
    tolerance_ms: float = 25.0
    stall_ms: float = 200.0
    debounce_us: int = 20_000
    sync_error_limit_ms: float = 2.0
    save_queue: int = 120
    gate_bright_min: int = 200
    gate_std_max: float = 8.0
    gate_empty_needed: int = 24
    gate_min_frames: int = 100
    exposure_jump: float = 25.0
    min_free_bytes: int = 2 * 1024**3
    max_interval_ratio: float = 2.0


@dataclass
class ReelMeta:
    name: str | None = None
    film_type: str = "super8"
    notes: str = ""
    customer: str = ""
    job_number: str = ""


@dataclass(frozen=True)
class MachineStatus:
    state: MachineState
    reel_name: str | None
    segment: int
    frames_saved: int
    frames_failed: int
    frames_pending: int
    clicks: int
    bounces: int
    fps: float
    sync_error_ms: float
    free_bytes: int
    last_fault: Fault | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


class Machine:
    def __init__(
        self,
        config: MachineConfig,
        clock: Clock,
        link: SyncBoxLink,
        camera: CameraSource,
        alerter: Alerter,
        free_bytes: Callable[[Path], int] = _free_bytes,
        wall_clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.config = config
        self._clock = clock
        self.link = link
        self._camera = camera
        self._alerter = alerter
        self._free_bytes = free_bytes
        self._wall_clock = wall_clock
        self._lock = threading.RLock()
        self.state = MachineState.NOT_READY
        self.reel: ReelFolder | None = None
        self._journal: Journal | None = None
        self._saver: Saver | None = None
        self._pending_meta: ReelMeta | None = None
        self.segment = 0
        self._next_frame = 1
        self.accounting = Accounting()
        self.bounces = 0
        self.fault_history: list[Fault] = []
        self.warnings: list[str] = []
        self._first_shape: tuple[int, int] | None = None
        self._pictures_seen = 0
        self._intervals: deque[int] = deque(maxlen=20)
        self._click_times: deque[int] = deque(maxlen=20)
        self._picker = self._new_picker()
        self._gate = GateDetector(
            config.gate_bright_min,
            config.gate_std_max,
            config.gate_empty_needed,
            config.gate_min_frames,
        )
        self._exposure = ExposureWatcher(jump=config.exposure_jump)
        link.on_click = self.on_click
        link.on_bounce = self.on_bounce

    def _new_picker(self) -> FramePicker:
        c = self.config
        return FramePicker(
            round(c.delay_ms * 1e6),
            round(c.tolerance_ms * 1e6),
            round(c.stall_ms * 1e6),
            self._on_picked,
            self._on_failed,
        )

    # ---- lifecycle -------------------------------------------------------------------------

    def start(self) -> None:
        self._camera.start(self.on_picture)
        self.link.set_debounce(self.config.debounce_us)

    def shutdown(self) -> None:
        with self._lock:
            self._camera.stop()
            if self._saver is not None:
                self._saver.join(30)
                self._saver.stop()
                self.accounting.assert_balanced()

    # ---- operator actions ------------------------------------------------------------------

    def new_reel(self, meta: ReelMeta) -> None:
        with self._lock:
            allowed = (MachineState.READY, MachineState.REEL_FINISHED, MachineState.STOPPED)
            if self.state not in allowed:
                raise RuntimeError(f"cannot start a new reel while {self.state}")
            self._close_reel()
            self._pending_meta = meta
            self.state = MachineState.READY

    def stop(self) -> None:
        with self._lock:
            self._fault(
                Fault("operator", "Stop pressed on the page", "Switch off the WorkPrinter")
            )

    def resume(self) -> None:
        with self._lock:
            if self.state != MachineState.STOPPED:
                raise RuntimeError(f"resume only from stopped, not {self.state}")
            if self.reel is None:
                raise RuntimeError("no reel to resume")
            self._picker = self._new_picker()
            self.segment += 1
            self.state = MachineState.READY

    # ---- events ----------------------------------------------------------------------------

    def on_picture(self, p: Picture) -> None:
        with self._lock:
            self._pictures_seen += 1
            if self._first_shape is None:
                self._first_shape = p.shape
            elif p.shape != self._first_shape:
                self._fault(
                    Fault(
                        "camera",
                        f"camera changed mode: {self._first_shape} -> {p.shape}",
                        "Check the camcorder and the video adapter, then Resume",
                    )
                )
                return
            self._picker.on_picture(p)

    def on_bounce(self, seq: int, t_us: int) -> None:
        with self._lock:
            self.bounces += 1
            self._journal_event({"type": "bounce", "seq": seq, "t_box_us": t_us})

    def on_click(self, ev: ClickEvent) -> None:
        with self._lock:
            if self.state == MachineState.READY:
                self._open_segment()
            if self.state != MachineState.RECORDING:
                self._journal_event({"type": "ignored_click", "seq": ev.seq, "state": str(self.state)})
                return
            self._click_times.append(ev.t_pc_ns)
            if ev.interval_us > 0:
                if len(self._intervals) == self._intervals.maxlen:
                    median = statistics.median(self._intervals)
                    if ev.interval_us > self.config.max_interval_ratio * median:
                        self._fault(
                            Fault(
                                "missed_frame",
                                f"far too long between clicks: {ev.interval_us / 1000:.0f} ms "
                                f"(usual {median / 1000:.0f} ms)",
                                "Check the film path and the sync cable, wind back, then Resume",
                            )
                        )
                        return
                self._intervals.append(ev.interval_us)
            n = self._next_frame
            self._next_frame += 1
            self.accounting.click()
            self._journal_event(
                {
                    "type": "click",
                    "seq": ev.seq,
                    "frame": n,
                    "t_box_us": ev.t_box_us,
                    "t_pc_ns": ev.t_pc_ns,
                    "interval_us": ev.interval_us,
                    "segment": self.segment,
                }
            )
            self._picker.on_click(PendingClick(ev, n, 0))

    def _on_picked(self, picked: Picked) -> None:
        n = picked.pending.frame_number
        self._journal_event(
            {
                "type": "picked",
                "frame": n,
                "picture_index": picked.picture.index,
                "offset_ns": picked.offset_ns,
            }
        )
        try:
            self._saver.submit(n, picked.picture)
        except (QueueFull, FileExistsError) as e:
            self.accounting.failed_one()
            self._journal_event({"type": "failed", "frame": n, "reason": str(e)})
            self._fault(Fault("storage", str(e), "Check the reel drive, wind back, then Resume"))
            return
        px = picked.picture.pixels
        if not is_empty_gate(px, self.config.gate_bright_min, self.config.gate_std_max):
            jump = self._exposure.observe(px)
            if jump is not None:
                self._warn(f"picture brightness jumped by {jump:.0f} levels: check camcorder auto exposure")
        if self._gate.observe(n, px):
            self._journal_event({"type": "reel_finished", "frame": n})
            self._journal_event(
                {"type": "segment_stop", "segment": self.segment, "reason": "reel finished"}
            )
            self.state = MachineState.REEL_FINISHED
            self._alerter.alert(
                "info",
                f"Reel finished — switch off {self.config.name}",
                f"{self.accounting.saved + self.accounting.pending} frames",
            )

    def _on_failed(self, failed: Failed) -> None:
        n = failed.pending.frame_number
        self.accounting.failed_one()
        self._journal_event({"type": "failed", "frame": n, "reason": failed.reason})
        self._fault(
            Fault(
                "missed_frame",
                f"frame {n}: {failed.reason}",
                "Check the camera, wind back to the last saved frame, then Resume",
            )
        )

    def _on_save_done(self, n: int) -> None:
        with self._lock:
            self.accounting.saved_one()

    def _on_save_error(self, n: int, exc: Exception) -> None:
        with self._lock:
            self.accounting.failed_one()
            self._fault(
                Fault("storage", f"frame {n}: {exc}", "Check the reel drive, wind back, then Resume")
            )

    # ---- periodic --------------------------------------------------------------------------

    def tick(self) -> None:
        with self._lock:
            try:
                self.link.poll()
            except (ProtocolError, SequenceGapError) as e:
                self._fault(Fault("sync", str(e), "Check the sync box cable, wind back, then Resume"))
            except SyncBoxSilent as e:
                self._fault(
                    Fault("sync_box", str(e), "Reconnect the sync box, wind back, then Resume")
                )
            if self.state == MachineState.RECORDING:
                self._picker.check(self._clock.now_ns())
            if self.state in (MachineState.NOT_READY, MachineState.READY, MachineState.RECORDING):
                self._check_health()

    def _free(self) -> int:
        root = self.config.reel_root
        return self._free_bytes(root if root.exists() else root.parent)

    def _check_health(self) -> None:
        cs = self.link.clocksync
        free = self._free()
        synced = cs.ready and cs.error_ms <= self.config.sync_error_limit_ms
        ok = (
            synced
            and self._pictures_seen > 0
            and free >= self.config.min_free_bytes
            and self.link.serial is not None
        )
        if self.state == MachineState.NOT_READY:
            if ok:
                self.state = MachineState.READY
        elif self.state == MachineState.READY:
            if not ok:
                self.state = MachineState.NOT_READY
        elif self.state == MachineState.RECORDING:
            if not synced:
                self._fault(
                    Fault(
                        "sync",
                        f"clock sync error {cs.error_ms:.2f} ms over limit",
                        "Check the sync box USB connection, wind back, then Resume",
                    )
                )
            elif free < self.config.min_free_bytes:
                self._fault(
                    Fault(
                        "storage",
                        f"reel drive nearly full ({free / 1e9:.1f} GB free)",
                        "Free space on the reel drive, wind back, then Resume",
                    )
                )
            elif self._saver is not None and not self._saver.alive:
                self._fault(
                    Fault("storage", "saver stopped unexpectedly", "Check the reel drive and restart")
                )

    # ---- internals -------------------------------------------------------------------------

    def _journal_event(self, event: dict) -> None:
        if self._journal is None:
            return
        self._journal.append({"t_ns": self._clock.now_ns(), **event})

    def _open_segment(self) -> None:
        if self.reel is None:
            self._create_reel(self._pending_meta or ReelMeta())
            self._pending_meta = None
        self._journal_event(
            {"type": "segment_start", "segment": self.segment, "first_frame": self._next_frame}
        )
        self.state = MachineState.RECORDING

    def _create_reel(self, meta: ReelMeta) -> None:
        name = meta.name or f"{self.config.name} — {self._wall_clock().strftime('%Y-%m-%d %H%M')}"
        self.reel = ReelFolder.create(self.config.reel_root, name)
        self._journal = Journal(self.reel.journal_path)
        self._saver = Saver(
            self.reel,
            self._journal,
            self._clock,
            self.config.save_queue,
            self._on_save_error,
            self._on_save_done,
        )
        self._saver.start()
        self.segment = 1
        self._next_frame = 1
        self.accounting = Accounting()
        self._gate.reset()
        self._intervals.clear()
        info = self._camera.info()
        self.reel.write_reel_json(
            {
                "name": self.reel.name,
                "machine": self.config.name,
                "film_type": meta.film_type,
                "notes": meta.notes,
                "customer": meta.customer,
                "job_number": meta.job_number,
                "created": self._wall_clock().isoformat(timespec="seconds"),
                "camera": asdict(info),
                "delay_ms": self.config.delay_ms,
                "debounce_us": self.config.debounce_us,
                "sync_box_serial": self.link.serial,
                "sync_box_fw": self.link.fw_version,
            }
        )

    def _close_reel(self) -> None:
        if self._saver is not None:
            self._saver.join(30)
            self._saver.stop()
            self.accounting.assert_balanced()
        self.reel = None
        self._journal = None
        self._saver = None
        self.segment = 0
        self._next_frame = 1
        self._picker = self._new_picker()

    def _warn(self, text: str) -> None:
        self.warnings.append(text)
        self._alerter.alert("warning", self.config.name, text)
        self._journal_event({"type": "warning", "text": text})

    def _fault(self, fault: Fault) -> None:
        self.fault_history.append(fault)
        self._journal_event(
            {"type": "fault", "kind": fault.kind, "message": fault.message, "segment": self.segment}
        )
        if self.state == MachineState.RECORDING:
            self._journal_event(
                {"type": "segment_stop", "segment": self.segment, "reason": fault.kind}
            )
            self.state = MachineState.STOPPED
            self._alerter.alert(
                "problem", f"STOP {self.config.name} NOW", f"{fault.message}. {fault.action}"
            )
            return
        if fault.kind == "operator" and self.state in (MachineState.READY, MachineState.REEL_FINISHED):
            self.state = MachineState.STOPPED
            return
        self._alerter.alert("warning", self.config.name, f"{fault.message}. {fault.action}")
        if fault.kind in ("camera", "sync_box", "sync"):
            self.state = MachineState.NOT_READY

    def status(self) -> MachineStatus:
        with self._lock:
            fps = 0.0
            if len(self._click_times) >= 2:
                span = self._click_times[-1] - self._click_times[0]
                if span > 0:
                    fps = (len(self._click_times) - 1) * 1e9 / span
            return MachineStatus(
                state=self.state,
                reel_name=self.reel.name if self.reel else None,
                segment=self.segment,
                frames_saved=self.accounting.saved,
                frames_failed=self.accounting.failed,
                frames_pending=self.accounting.pending,
                clicks=self.accounting.clicks_accepted,
                bounces=self.bounces,
                fps=fps,
                sync_error_ms=self.link.clocksync.error_ms,
                free_bytes=self._free(),
                last_fault=self.fault_history[-1] if self.fault_history else None,
                warnings=tuple(self.warnings[-5:]),
            )
```

Notes for the engineer:
- `Saver` calls `_on_save_done` / `_on_save_error` from its thread; both take the `RLock`, so the accounting is never touched by two threads at once.
- `_on_picked` runs while `_lock` is held (it is called from `on_picture`/`on_click`), so `self._saver` is never None there: a `Picked` can only exist while RECORDING, which requires an open reel.
- A `_fault` while RECORDING does not touch the picker's pending clicks; `resume()` replaces the picker, which drops them. Their accounting entries were never created (a click is counted only when accepted in RECORDING), so the books still balance.

- [ ] **Step 4: Implement the SimRig**

`src/wpcap/sim/rig.py`:
```python
"""Wire one Machine to simulated hardware and drive it in virtual time (tests) or real time (demo)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from wpcap.clock import SimClock
from wpcap.clocksync import ClockSync
from wpcap.machine import Machine, MachineConfig, RecordingAlerter
from wpcap.sim.camera import SimCamera
from wpcap.sim.film import SimFilm
from wpcap.sim.syncbox import SimSyncBox
from wpcap.sim.transport import sim_transport_pair
from wpcap.synclink import SyncBoxLink


class SimRig:
    def __init__(
        self,
        config: MachineConfig,
        film: SimFilm,
        offset_us: int = 0,
        drift_ppm: float = 0.0,
        cam_fps: float = 60.0,
        cam_size: tuple[int, int] = (192, 108),
        free_bytes: Callable[[Path], int] | None = None,
    ) -> None:
        self.clock = SimClock()
        box_side, pc_side = sim_transport_pair()
        self.box = SimSyncBox(self.clock, box_side, offset_us=offset_us, drift_ppm=drift_ppm)
        self.camera = SimCamera(
            self.clock, film, fps=cam_fps, width=cam_size[0], height=cam_size[1]
        )
        self.alerter = RecordingAlerter()
        link = SyncBoxLink(pc_side, self.clock, ClockSync(), lambda ev: None, lambda s, t: None)
        kwargs = {} if free_bytes is None else {"free_bytes": free_bytes}
        self.machine = Machine(config, self.clock, link, self.camera, self.alerter, **kwargs)
        self.switch_times: list[int] = film.switch_times()
        self._next_switch = 0
        self.machine.start()

    @property
    def alerts(self) -> list[tuple[str, str, str]]:
        return self.alerter.alerts

    def _step(self) -> None:
        now = self.clock.now_ns()
        if self.camera.started:
            self.camera.emit_until(now)
        while (
            self._next_switch < len(self.switch_times)
            and self.switch_times[self._next_switch] <= now
        ):
            self.box.close_switch()
            self._next_switch += 1
        self.box.tick()
        self.machine.tick()
        saver = self.machine._saver
        if saver is not None and saver.alive:
            saver.join(5)

    def run_until(self, t_ns: int, step_ns: int = 1_000_000) -> None:
        while self.clock.now_ns() < t_ns:
            self.clock.advance(step_ns)
            self._step()

    def run_for(self, ns: int, step_ns: int = 1_000_000) -> None:
        self.run_until(self.clock.now_ns() + ns, step_ns)

    def run_realtime(self, seconds: float, step_ns: int = 2_000_000) -> None:
        """Demo Mode: advance the simulated clock in step with the wall clock."""
        start_wall = time.perf_counter_ns()
        start_sim = self.clock.now_ns()
        end = start_sim + round(seconds * 1e9)
        while self.clock.now_ns() < end:
            target = start_sim + (time.perf_counter_ns() - start_wall)
            if target > self.clock.now_ns():
                self.clock.set(min(target, end))
                self._step()
            else:
                time.sleep(step_ns / 1e9)
```

`SimRig._step` reaches into `machine._saver` to drain it each step. That is deliberate test plumbing: it makes `frames_saved` exact at every virtual instant. Keep it in the rig, not in the machine.

- [ ] **Step 5: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass. Expected first-run issues and their real causes:
- `test_scans_every_frame_once_in_order` saved count: the gate needs 8 empty frames **after** 20 picture frames; the 200th frame is the last picture, so frames 201–208 are empty and the reel finishes on 208. The simulated film emits 50 extra clicks after the end, so there are plenty.
- `test_missing_click_is_missed_frame_fault`: removing three consecutive switch times gives a 500 ms interval, 4× the 125 ms median; the median needs 20 intervals first, satisfied by frame 40.
- `test_camera_stall_is_fault`: after `camera.stop()`, the next click's target gets no picture; `stall_ms=200` later `check()` fails it.

- [ ] **Step 6: Commit**

```bash
git add src/wpcap/machine.py src/wpcap/sim/rig.py tests/test_machine.py
git commit -m "feat: Machine state machine with faults, end of reel, resume; SimRig drives it in virtual time"
```

---

### Task 10: Recovery after a crash

**Files:**
- Create: `src/wpcap/recovery.py`, `tests/test_recovery.py`

**Interfaces:**
- Consumes: Task 7 `ReelFolder`, `Journal`, `JournalCorrupt`.
- Produces:
  - `@dataclass(frozen=True) RecoveryReport(reel: Path, complete_frames: tuple[int, ...], half_written: tuple[Path, ...], journaled_but_missing: tuple[int, ...], on_disk_not_journaled: tuple[int, ...], journal_truncated: bool, last_frame: int, open_segment: int | None)`
  - `recover(folder: ReelFolder) -> RecoveryReport`: lists `frames/*.png` (complete), `frames/*.png.tmp` (half-written, **left in place**), compares with `saved` journal events; `open_segment` is the segment of the last `segment_start` without a matching `segment_stop`; `last_frame` = highest complete frame number. Never deletes or renames anything. Raises `JournalCorrupt` for a corrupt line that is not a truncated last line.
  - `repair(folder, report) -> None`: trims a truncated last line, journals `failed` (`reason: "half-written at recovery"`) for each tmp file and unlinks it, journals `segment_stop` with `reason: "crash"` if a segment was open, then journals `recovered` with the report numbers.

- [ ] **Step 1: Write the failing tests**

`tests/test_recovery.py`:
```python
import pytest

from wpcap.recovery import recover, repair
from wpcap.reel import Journal, JournalCorrupt, ReelFolder


def reel_with(tmp_path, frames=(1, 2, 3), saved=(1, 2, 3), tmp=(), open_segment=True, truncate=False):
    r = ReelFolder.create(tmp_path, "Reel")
    j = Journal(r.journal_path)
    j.append({"type": "segment_start", "t_ns": 1, "segment": 1, "first_frame": 1})
    for n in frames:
        r.frame_path(n).write_bytes(b"png")
    for n in saved:
        j.append({"type": "saved", "t_ns": 10 + n, "frame": n, "picture_index": n, "t_pic_ns": n})
    for n in tmp:
        (r.frames_dir / f"{n:06d}.png.tmp").write_bytes(b"partial")
    if not open_segment:
        j.append({"type": "segment_stop", "t_ns": 99, "segment": 1, "reason": "reel finished"})
    if truncate:
        with r.journal_path.open("a") as f:
            f.write('{"type": "saved", "t_ns": 5')
    return r, j


def test_clean_reel(tmp_path):
    r, _ = reel_with(tmp_path, open_segment=False)
    rep = recover(r)
    assert rep.complete_frames == (1, 2, 3) and rep.half_written == () and rep.open_segment is None
    assert rep.last_frame == 3 and not rep.journal_truncated


def test_crash_mid_write(tmp_path):
    r, _ = reel_with(tmp_path, frames=(1, 2), saved=(1, 2), tmp=(3,), truncate=True)
    rep = recover(r)
    assert rep.complete_frames == (1, 2)
    assert [p.name for p in rep.half_written] == ["000003.png.tmp"]
    assert rep.open_segment == 1 and rep.journal_truncated and rep.last_frame == 2
    assert (r.frames_dir / "000003.png.tmp").exists()  # recover never deletes


def test_frame_on_disk_but_not_journaled_and_vice_versa(tmp_path):
    r, _ = reel_with(tmp_path, frames=(1, 2, 3), saved=(1, 2, 4))
    rep = recover(r)
    assert rep.on_disk_not_journaled == (3,) and rep.journaled_but_missing == (4,)


def test_corrupt_middle_line_raises(tmp_path):
    r, _ = reel_with(tmp_path)
    lines = r.journal_path.read_text().split("\n")
    lines.insert(1, "{broken")
    r.journal_path.write_text("\n".join(lines))
    with pytest.raises(JournalCorrupt):
        recover(r)


def test_repair_closes_segment_and_removes_tmp(tmp_path):
    r, j = reel_with(tmp_path, frames=(1, 2), saved=(1, 2), tmp=(3,), truncate=True)
    rep = recover(r)
    repair(r, rep)
    assert not (r.frames_dir / "000003.png.tmp").exists()
    events = j.read_all()  # no longer truncated
    assert [e["type"] for e in events[-3:]] == ["failed", "segment_stop", "recovered"]
    assert events[-2]["reason"] == "crash"
    assert events[-3]["frame"] == 3
    assert recover(r).open_segment is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_recovery.py -q`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

`src/wpcap/recovery.py`:
```python
"""After a crash or power cut: compare the journal with the frames on disk (spec 7.2)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from wpcap.reel import Journal, JournalCorrupt, ReelFolder

_FRAME_RE = re.compile(r"^(\d{6})\.png$")
_TMP_RE = re.compile(r"^(\d{6})\.png\.tmp$")


@dataclass(frozen=True)
class RecoveryReport:
    reel: Path
    complete_frames: tuple[int, ...]
    half_written: tuple[Path, ...]
    journaled_but_missing: tuple[int, ...]
    on_disk_not_journaled: tuple[int, ...]
    journal_truncated: bool
    last_frame: int
    open_segment: int | None


def _trim_truncated_line(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: text.rfind("\n") + 1], encoding="utf-8")


def recover(folder: ReelFolder) -> RecoveryReport:
    complete: list[int] = []
    half: list[Path] = []
    for p in sorted(folder.frames_dir.iterdir()):
        if m := _FRAME_RE.match(p.name):
            complete.append(int(m.group(1)))
        elif _TMP_RE.match(p.name):
            half.append(p)
    journal = Journal(folder.journal_path)
    events, truncated = journal.read_all_tolerant()
    # read_all_tolerant forgives only a truncated last line; any other bad line must raise.
    # It already raises JournalCorrupt for a bad middle line, so nothing more to do here.
    journaled = sorted({e["frame"] for e in events if e["type"] == "saved"})
    open_segment: int | None = None
    for e in events:
        if e["type"] == "segment_start":
            open_segment = e["segment"]
        elif e["type"] == "segment_stop" and e.get("segment") == open_segment:
            open_segment = None
    complete_set, journaled_set = set(complete), set(journaled)
    return RecoveryReport(
        reel=folder.path,
        complete_frames=tuple(complete),
        half_written=tuple(half),
        journaled_but_missing=tuple(sorted(journaled_set - complete_set)),
        on_disk_not_journaled=tuple(sorted(complete_set - journaled_set)),
        journal_truncated=truncated,
        last_frame=max(complete) if complete else 0,
        open_segment=open_segment,
    )


def repair(folder: ReelFolder, report: RecoveryReport) -> None:
    if report.journal_truncated:
        _trim_truncated_line(folder.journal_path)
    journal = Journal(folder.journal_path)
    now = time.perf_counter_ns()
    for p in report.half_written:
        m = _TMP_RE.match(p.name)
        if m is None:
            raise ValueError(f"not a half-written frame file: {p}")
        n = int(m.group(1))
        journal.append(
            {"type": "failed", "t_ns": now, "frame": n, "reason": "half-written at recovery"}
        )
        p.unlink()
    if report.open_segment is not None:
        journal.append(
            {"type": "segment_stop", "t_ns": now, "segment": report.open_segment, "reason": "crash"}
        )
    journal.append(
        {
            "type": "recovered",
            "t_ns": now,
            "complete": len(report.complete_frames),
            "half_written": len(report.half_written),
            "journaled_but_missing": list(report.journaled_but_missing),
            "on_disk_not_journaled": list(report.on_disk_not_journaled),
            "last_frame": report.last_frame,
        }
    )


__all__ = ["JournalCorrupt", "RecoveryReport", "recover", "repair"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/wpcap/recovery.py tests/test_recovery.py
git commit -m "feat: crash recovery report and repair from journal and frame files"
```

---

### Task 11: Demo Mode command line

**Files:**
- Create: `src/wpcap/__main__.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 9 `SimRig`, `MachineConfig`, `MachineState`; Task 6 `SimFilm`, `is_blurred`; Task 7 `ReelFolder`.
- Produces: `python -m wpcap demo --reels DIR [--frames N] [--delay-ms D] [--switch-offset-ms O] [--realtime]`. Prints a status line every simulated second, then a final summary line `final: <state> saved N failed N blurred N` and the reel path. Exit code 0 when the reel finished with no failed and no blurred frames, 1 otherwise. `--realtime` uses `run_realtime`, otherwise virtual time as fast as possible.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import subprocess
import sys


def test_demo_runs_a_reel_and_exits_zero(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "wpcap", "demo", "--reels", str(tmp_path), "--frames", "150"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "final: reel_finished saved 158 failed 0 blurred 0" in r.stdout
    assert list(tmp_path.iterdir()), "a reel folder was created"


def test_demo_wrong_delay_exits_nonzero_with_blur_count(tmp_path):
    r = subprocess.run(
        [
            sys.executable, "-m", "wpcap", "demo", "--reels", str(tmp_path),
            "--frames", "60", "--switch-offset-ms", "-20", "--delay-ms", "0",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 1
    assert "blurred" in r.stdout and "blurred 0" not in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_cli.py -q`
Expected: FAIL (`No module named wpcap.__main__`).

- [ ] **Step 3: Implement**

`src/wpcap/__main__.py`:
```python
"""Command line: `python -m wpcap demo` runs a simulated reel end to end."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from wpcap.machine import MachineConfig, MachineState
from wpcap.reel import ReelFolder
from wpcap.sim.camera import is_blurred
from wpcap.sim.film import SimFilm
from wpcap.sim.rig import SimRig

S = 1_000_000_000


def demo(args: argparse.Namespace) -> int:
    config = MachineConfig(
        name="Demo WorkPrinter",
        reel_root=Path(args.reels),
        delay_ms=args.delay_ms,
        gate_min_frames=20,
        gate_empty_needed=8,
    )
    film = SimFilm(frames=args.frames, start_ns=3 * S, switch_offset_ms=args.switch_offset_ms)
    rig = SimRig(config, film)
    total_s = 3 + args.frames / 8.0 + 3
    seconds_run = 0
    while seconds_run < total_s:
        if args.realtime:
            rig.run_realtime(1.0)
        else:
            rig.run_for(S)
        seconds_run += 1
        _print_status(rig)
    rig.machine.shutdown()
    st = rig.machine.status()
    reel = rig.machine.reel
    blurred = 0
    if reel is not None:
        for p in sorted(ReelFolder.open(reel.path).frames_dir.glob("*.png")):
            if is_blurred(np.asarray(Image.open(p))):
                blurred += 1
    print(f"final: {st.state} saved {st.frames_saved} failed {st.frames_failed} blurred {blurred}")
    if reel is not None:
        print(f"reel: {reel.path}")
    for level, title, message in rig.alerts:
        print(f"alert [{level}] {title}: {message}")
    ok = st.state == MachineState.REEL_FINISHED and st.frames_failed == 0 and blurred == 0
    return 0 if ok else 1


def _print_status(rig: SimRig) -> None:
    st = rig.machine.status()
    print(
        f"t={rig.clock.now_ns() / S:6.1f}s {st.state:14s} saved {st.frames_saved:5d} "
        f"failed {st.frames_failed:3d} fps {st.fps:4.1f} sync {st.sync_error_ms:.3f} ms"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wpcap")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="scan a simulated reel")
    d.add_argument("--reels", required=True, help="folder for reel folders")
    d.add_argument("--frames", type=int, default=300)
    d.add_argument("--delay-ms", type=float, default=0.0)
    d.add_argument("--switch-offset-ms", type=float, default=0.0)
    d.add_argument("--realtime", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "demo":
        return demo(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `testrepo`
Expected: all pass. With `--switch-offset-ms -20 --delay-ms 0` every click lands inside the 30 ms pull-down, so every picked picture is blurred and the final line reads `blurred 60`.

- [ ] **Step 5: Commit, push, open the PR**

```bash
git add src/wpcap/__main__.py tests/test_cli.py
git commit -m "feat: demo mode runs a simulated reel from the command line"
git push -u origin feature/capture-core
gh pr create --title "Capture core: protocol, clock sync, simulators, picker, saver, machine" --body "$(cat <<'EOF'
Plan 1 of 4 from docs/superpowers/plans/2026-10-30-capture-core.md.

- Sync box wire protocol (CRC16, sequence numbers) + PROTOCOL.md
- ClockSync (offset + drift from best round trips)
- Simulated sync box and camera sharing one SimFilm timeline
- RingBuffer + FramePicker (nearest picture to click + delay, never reused, fails loudly)
- Reel folder, journal, Saver (temp-then-rename, fixed queue), Accounting
- GateDetector (end of reel, leader rule), ExposureWatcher
- Machine state machine: faults, alerts, resume/segments
- Recovery after crash
- `python -m wpcap demo`

All tests run on Linux with simulators: `testrepo` → `make test`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
```

Address every CodeRabbit finding (security, correctness, best practice) before calling the plan done.

---

## Self-review

**Spec coverage (sections in scope):** 5.1 box side → Task 3 + Task 5 simulator (firmware itself is plan 3). 5.2 → Task 4, Task 5, Task 9 (`sync_error_limit_ms`). 5.3 → Task 5 (bounce via box), Task 9 (interval check). 5.4 picking → Task 6; calibration screen and neighbours → plan 2 (out of scope, listed). 5.5 drift warning → Task 8 + Task 9. 5.6 pairing by serial → the serial is read (Task 5) and recorded in `reel.json` (Task 9); the registry/pairing UI is plan 2. 6.1 → Task 9 `new_reel`, auto-naming, customer/job number. 6.2 status fields → `MachineStatus` (PC temperature is a Windows-side reading, plan 4). 6.3 → Task 8 + Task 9. 6.4 fault table → Task 9 (camera, missed frame, storage, sync, sync box, operator; overheating is plan 4). 6.5 delivery of alerts → `Alerter` interface here, ntfy/browser in plan 2. 7.1 → Task 7. 7.2 → Task 7, Task 9 (`reel.json`), Task 10 (recovery). 10.1 bullets covered: 1,000 frames and two machines (Task 9), bounce/missed/no-picture (Tasks 6, 9), clock sync converge/excess (Tasks 4, 9), protocol lost/dup/corrupt (Tasks 3, 5, 9), picking at the correct delay never blur (Task 9 `test_delay_absorbs_switch_offset`), drift warning (Task 8), end of reel/leader (Tasks 8, 9), faults incl. one machine not affecting the other (Task 9), recovery (Task 10), accounting (Tasks 7, 9). Not here by design: firmware unit tests (plan 3), neighbour re-picking and overlap trimming (plan 2), movies (plan 2).

**Placeholder scan:** none; every step has code or an exact command.

**Type consistency:** `ClickEvent(seq, t_box_us, t_pc_ns, interval_us)` used identically in Tasks 5, 6, 9. `PendingClick(click, frame_number, target_ns)` in 6 and 9. `Saver(folder, journal, clock, queue_size, on_error, on_saved)` in Tasks 7 and 9. `SyncBoxLink.on_click` / `.on_bounce` are public attributes (Task 5) rebound by `Machine` (Task 9). `SimCamera.started` (Task 6) used by `SimRig` (Task 9). `Saver.alive` (Task 7) used by `Machine` and `SimRig` (Task 9). `Picture.shape` (Task 6) used by Task 9. `SimSyncBox.drop_next` used in Tasks 5 and 9. `is_blurred` (Task 6) used by Task 11.

**Review Focus:** 1 → `test_click_with_empty_buffer_fails` (Task 6). 2 → `test_picture_never_reused` (Task 6). 3 → `test_reel_folder_name_collision_gets_suffix` (Task 7). 4 → `test_write_error_is_fault_not_half_frame` (Task 7). 5 → `test_camera_mode_change_is_fault` (Task 9).
