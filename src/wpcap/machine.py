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
            self._fault(Fault("operator", "Stop pressed on the page", "Switch off the WorkPrinter"))

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
                self._journal_event(
                    {"type": "ignored_click", "seq": ev.seq, "state": str(self.state)}
                )
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
                self._warn(
                    f"picture brightness jumped by {jump:.0f} levels: check camcorder auto exposure"
                )
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
                Fault(
                    "storage", f"frame {n}: {exc}", "Check the reel drive, wind back, then Resume"
                )
            )

    # ---- periodic --------------------------------------------------------------------------

    def tick(self) -> None:
        with self._lock:
            try:
                self.link.poll()
            except (ProtocolError, SequenceGapError) as e:
                self._fault(
                    Fault("sync", str(e), "Check the sync box cable, wind back, then Resume")
                )
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
                    Fault(
                        "storage", "saver stopped unexpectedly", "Check the reel drive and restart"
                    )
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
            for pending in self._picker.drain():
                self.accounting.failed_one()
                self._journal_event(
                    {"type": "failed", "frame": pending.frame_number, "reason": "segment stopped"}
                )
            self._journal_event(
                {"type": "segment_stop", "segment": self.segment, "reason": fault.kind}
            )
            self.state = MachineState.STOPPED
            self._alerter.alert(
                "problem", f"STOP {self.config.name} NOW", f"{fault.message}. {fault.action}"
            )
            return
        if fault.kind == "operator" and self.state in (
            MachineState.READY,
            MachineState.REEL_FINISHED,
        ):
            self.state = MachineState.STOPPED
            return
        self._alerter.alert("warning", self.config.name, f"{fault.message}. {fault.action}")
        # STOPPED and REEL_FINISHED hold until the operator acts (resume / new reel); demoting
        # them would let the health check promote to READY and the next click record unasked.
        if fault.kind in ("camera", "sync_box", "sync") and self.state == MachineState.READY:
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
