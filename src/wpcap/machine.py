"""One WorkPrinter = one Machine: the state machine that turns clicks and pictures into frames."""

from __future__ import annotations

import shutil
import statistics
import threading
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Protocol

from wpcap.camera import CameraSource, Picture
from wpcap.clock import Clock
from wpcap.gate import ExposureWatcher, GateDetector, is_empty_gate
from wpcap.picker import Failed, FramePicker, PendingClick, Picked
from wpcap.protocol import ProtocolError, SequenceGapError
from wpcap.reel import Journal, ReelFolder
from wpcap.saver import Accounting, QueueFull, Saver
from wpcap.synclink import ClickEvent, SyncBoxGone, SyncBoxLink, SyncBoxSilent


class MachineState(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"
    RECORDING = "recording"
    REEL_FINISHED = "reel_finished"
    STOPPED = "stopped"
    SHUT_DOWN = "shut_down"


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
    free_bytes: int | None  # None: the reel drive is not there
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
        ReelFolder.check_name(config.name)  # it starts every default reel name
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
        self._reel_token: object | None = None
        self._pending_meta: ReelMeta | None = None
        self.segment = 0
        self._next_frame = 1
        self.accounting = Accounting()
        self.bounces = 0
        self.fault_history: list[Fault] = []
        self.warnings: list[str] = []
        self._first_shape: tuple[int, int] | None = None
        self._last_shape: tuple[int, int] | None = None
        self._last_picture_ns: int | None = None
        self._live: Picture | None = None
        self._last_saved: tuple[int, Picture] | None = None
        self._pictures_seen = 0
        # Fault kinds already raised while their condition persists: each is raised once,
        # and forgotten on resume, new reel, a new segment, or when the machine is Ready again.
        self._active_faults: set[str] = set()
        self._not_ready_warned = False
        # A journal write that failed during the current event; becomes a storage fault at
        # the end of the event (see _event), never dropped.
        self._journal_error: OSError | None = None
        self._intervals: deque[int] = deque(maxlen=20)
        self._click_times: deque[int] = deque(maxlen=20)
        self._first_click_of_segment = False
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
        link.on_unsynced_click = self.on_unsynced_click

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
        with self._event():
            self._camera.stop()
            if self.state == MachineState.RECORDING:
                self._fault(
                    Fault("operator", "capture program shutting down", "Switch off the WorkPrinter")
                )
            # Clicks still waiting for a picture (after the reel finished) can no longer get one.
            self._fail_pending_clicks("reel closed")
            saver, self._saver = self._saver, None
            accounting, journal = self.accounting, self._journal
        # The saver's callbacks take the machine lock, so drain it with the lock released.
        self._drain_saver(saver, accounting, journal)
        with self._lock:
            self.state = MachineState.SHUT_DOWN

    # ---- operator actions ------------------------------------------------------------------

    def new_reel(self, meta: ReelMeta) -> None:
        if meta.name is not None:
            ReelFolder.check_name(meta.name)
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                raise RuntimeError("machine is shut down")
            allowed = (
                MachineState.NOT_READY,
                MachineState.READY,
                MachineState.REEL_FINISHED,
                MachineState.STOPPED,
            )
            if self.state not in allowed:
                raise RuntimeError(f"cannot start a new reel while {self.state}")
            saver, accounting, journal = self._detach_reel()
            self._pending_meta = meta
            self._enter_ready_if_ready()
        self._drain_saver(saver, accounting, journal)

    def stop(self) -> None:
        with self._event():
            self._fault(Fault("operator", "Stop pressed on the page", "Switch off the WorkPrinter"))

    def resume(self) -> None:
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                raise RuntimeError("machine is shut down")
            if self.state != MachineState.STOPPED:
                raise RuntimeError(f"resume only from stopped, not {self.state}")
            if self.reel is None:
                raise RuntimeError("no reel to resume")
            self._replace_picker("segment stopped")
            self._intervals.clear()
            self._click_times.clear()
            self.segment += 1
            self._enter_ready_if_ready()

    # ---- events ----------------------------------------------------------------------------

    def on_picture(self, p: Picture) -> None:
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                return
            self._pictures_seen += 1
            self._last_picture_ns = p.t_ns
            self._live = p
            self._last_shape = p.shape
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
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                return
            self.bounces += 1
            self._journal_event({"type": "bounce", "seq": seq, "t_box_us": t_us})

    def on_unsynced_click(self, seq: int) -> None:
        """A closure arrived before the clocks are in sync: the film is moving too early."""
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                return
            self._journal_event({"type": "ignored_click", "seq": seq, "state": "unsynced"})
            self._warn_not_ready()

    def on_click(self, ev: ClickEvent) -> None:
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                return
            if self.state == MachineState.READY:
                self._open_segment()
            if self.state != MachineState.RECORDING:
                self._journal_event(
                    {"type": "ignored_click", "seq": ev.seq, "state": str(self.state)}
                )
                if self.state == MachineState.NOT_READY:
                    self._warn_not_ready()
                return
            self._click_times.append(ev.t_pc_ns)
            first_of_segment = self._first_click_of_segment
            self._first_click_of_segment = False
            # The first click of a segment measures the pause before it (winding back), not
            # the machine's running speed, so it is neither checked nor added to the median.
            if ev.interval_us > 0 and not first_of_segment:
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
                    if ev.interval_us * self.config.max_interval_ratio < median:
                        self._fault(
                            Fault(
                                "sync",
                                "double click: interval far too short: "
                                f"{ev.interval_us / 1000:.0f} ms (usual {median / 1000:.0f} ms)",
                                "Check the frame switch and the timing disk, raise the bounce "
                                "filter if needed, wind back, then Resume",
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
            self._last_saved = (n, picked.picture)
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

    # The saver callbacks are bound to the accounting and the token of the reel the saver
    # belongs to, so a saver still draining after new_reel() never books into, or stops, the
    # next reel.
    def _is_current(self, token: object) -> bool:
        return self._saver is not None and token is self._reel_token

    def _on_save_done(self, accounting: Accounting, n: int) -> None:
        with self._event():
            accounting.saved_one()

    def _on_save_error(
        self, accounting: Accounting, token: object, n: int, exc: Exception
    ) -> None:
        with self._event():
            accounting.failed_one()
            if not self._is_current(token):
                self._warn_previous_reel(n, exc)
                return
            self._fault(
                Fault(
                    "storage", f"frame {n}: {exc}", "Check the reel drive, wind back, then Resume"
                )
            )

    def _on_durability_error(self, token: object, n: int, exc: Exception) -> None:
        with self._event():
            if not self._is_current(token):
                self._warn_previous_reel(n, exc)
                return
            self._fault(
                Fault(
                    "storage",
                    f"frame {n} saved but the reel drive did not confirm it: {exc}",
                    "Check the reel drive; frames may not survive a power cut. "
                    "Wind back, then Resume",
                )
            )

    def _warn_previous_reel(self, n: int, exc: Exception) -> None:
        """A closed reel's saver reported late: the current reel is untouched."""
        self._alerter.alert("warning", self.config.name, f"previous reel: frame {n}: {exc}")

    # ---- periodic --------------------------------------------------------------------------

    def tick(self) -> None:
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                return
            try:
                self.link.poll()
            except (ProtocolError, SequenceGapError) as e:
                self._fault(
                    Fault("sync", str(e), "Check the sync box cable, wind back, then Resume")
                )
            except (SyncBoxSilent, SyncBoxGone) as e:
                self._fault(
                    Fault("sync_box", str(e), "Reconnect the sync box, wind back, then Resume")
                )
            if self.state == MachineState.RECORDING:
                self._picker.check(self._clock.now_ns())
            if self.state in (MachineState.NOT_READY, MachineState.READY, MachineState.RECORDING):
                self._check_health()

    def _storage(self) -> tuple[int | None, str]:
        """(free bytes, "") on the reel drive, or (None, why) when it cannot be measured.
        With a reel open, the reel's own folder is measured: a drive that unmounts leaves its
        mount point behind, and measuring that would report the host disk instead. Before a
        reel, the reel root or (not created yet) its parent."""
        where = self.config.reel_root
        try:
            if self.reel is not None:
                where = self.reel.frames_dir
                if not where.exists():
                    return None, f"reel folder gone: {where}"
            elif not where.exists():
                where = where.parent
            return self._free_bytes(where), ""
        except OSError as e:
            return None, f"reel drive not readable: {where}: {e}"

    def _free(self) -> int | None:
        return self._storage()[0]

    def _synced(self) -> bool:
        cs = self.link.clocksync
        return cs.ready and cs.error_ms <= self.config.sync_error_limit_ms

    def _camera_fresh(self) -> bool:
        """The camera is streaming now: its last picture is younger than the stall time."""
        if self._last_picture_ns is None:
            return False
        return self._clock.now_ns() - self._last_picture_ns <= round(self.config.stall_ms * 1e6)

    def _is_ready(self) -> bool:
        return (
            self._synced()
            and self.link.serial is not None
            and self.link.responsive
            and self._camera_fresh()
            and self._last_shape == self._first_shape
            and self._enough_free()
            and self._saver_alive()
        )

    def _enough_free(self) -> bool:
        free = self._free()
        return free is not None and free >= self.config.min_free_bytes

    def _saver_alive(self) -> bool:
        """No reel yet, or the reel's saver thread is running. A dead saver cannot be
        restarted: the machine stays Not ready until a new reel brings a new saver."""
        return self._saver is None or self._saver.alive

    def _enter_ready_if_ready(self) -> None:
        """Operator action done (resume, new reel): Ready only if every check passes now."""
        self._active_faults.clear()
        self._not_ready_warned = False
        self.state = MachineState.READY if self._is_ready() else MachineState.NOT_READY

    def _check_health(self) -> None:
        free, why = self._storage()
        if free is None:
            self._fault(
                Fault(
                    "storage",
                    f"reel drive not found ({why})",
                    "Plug the reel drive back in, wind back, then Resume",
                )
            )
        if not self._saver_alive():
            self._fault(
                Fault(
                    "storage",
                    "saver stopped unexpectedly",
                    "Check the reel drive, then start a new reel",
                )
            )
        if self.state == MachineState.NOT_READY:
            if self._is_ready():
                self.state = MachineState.READY
                self._active_faults.clear()
                self._not_ready_warned = False
        elif self.state == MachineState.READY:
            if not self._is_ready():
                self.state = MachineState.NOT_READY
        elif self.state == MachineState.RECORDING:
            if not self._synced():
                self._fault(
                    Fault(
                        "sync",
                        f"clock sync error {self.link.clocksync.error_ms:.2f} ms over limit",
                        "Check the sync box USB connection, wind back, then Resume",
                    )
                )
            elif free is not None and free < self.config.min_free_bytes:
                self._fault(
                    Fault(
                        "storage",
                        f"reel drive nearly full ({free / 1e9:.1f} GB free)",
                        "Free space on the reel drive, wind back, then Resume",
                    )
                )
            elif not self._camera_fresh():
                self._fault(
                    Fault(
                        "camera",
                        "camera stopped sending pictures",
                        "Check the camcorder, the video adapter and its USB cable, wind back, "
                        "then Resume",
                    )
                )

    # ---- pictures for the page --------------------------------------------------------------

    def live_picture(self) -> Picture | None:
        with self._lock:
            return self._live

    def last_saved(self) -> tuple[int, Picture] | None:
        with self._lock:
            return self._last_saved

    def click_window(self, before: int = 3, after: int = 3) -> list[tuple[int, Picture]]:
        """Pictures around the last click's target time, with their offset in ms (rounded)."""
        with self._lock:
            target = self._picker.last_target_ns
            if target is None:
                return []
            return [(round((p.t_ns - target) / 1e6), p) for p in self._picker.window(before, after)]

    def set_delay_ms(self, delay_ms: float) -> None:
        """Calibration: the delay from switch closure to the sharp picture. Not while recording
        (frames in flight were picked with the old delay). Recorded in the open reel."""
        if not (0.0 <= delay_ms <= 500.0):  # also rejects NaN
            raise ValueError(f"delay must be 0..500 ms, got {delay_ms}")
        with self._event():
            if self.state == MachineState.SHUT_DOWN:
                raise RuntimeError("machine is shut down")
            if self.state == MachineState.RECORDING:
                raise RuntimeError("cannot change the delay while recording: Stop first")
            self.config.delay_ms = delay_ms
            self._picker.set_delay(round(delay_ms * 1e6))
            if self.reel is not None:
                data = self.reel.read_reel_json()
                data["delay_ms"] = delay_ms
                self.reel.write_reel_json(data)

    # ---- internals -------------------------------------------------------------------------

    @contextmanager
    def _event(self) -> Iterator[None]:
        """Every entry point runs under the lock and ends by turning a journal write failure
        that happened during it into a storage fault, once the event's own bookkeeping is
        complete (so a failed write never leaves a click half booked)."""
        with self._lock:
            yield
            self._settle_journal_error()

    def _settle_journal_error(self) -> None:
        e = self._journal_error
        if e is None:
            return
        self._fault(
            Fault(
                "storage",
                f"cannot write the journal: {e}",
                "Check the reel drive, wind back, then Resume",
            )
        )
        # _fault's own journal lines meet the same broken journal; this fault reports it.
        self._journal_error = None

    def _journal_to(self, journal: Journal | None, event: dict) -> None:
        if journal is None:
            return
        try:
            journal.append({"t_ns": self._clock.now_ns(), **event})
        except OSError as e:
            if self._journal_error is None:
                self._journal_error = e

    def _journal_event(self, event: dict) -> None:
        self._journal_to(self._journal, event)

    def _open_segment(self) -> None:
        if self.reel is None:
            try:
                self._create_reel(self._pending_meta or ReelMeta())
            except OSError as e:
                self._fault(
                    Fault(
                        "storage",
                        f"cannot create the reel folder: {e}",
                        "Check the reel drive, then press New Reel",
                    ),
                    film_moving=True,
                )
                return
            self._pending_meta = None
        self._journal_event(
            {"type": "segment_start", "segment": self.segment, "first_frame": self._next_frame}
        )
        self._first_click_of_segment = True
        self._active_faults.clear()
        self.state = MachineState.RECORDING

    def _create_reel(self, meta: ReelMeta) -> None:
        """Nothing is attached to the machine until every step on the drive has worked."""
        name = meta.name or f"{self.config.name} — {self._wall_clock().strftime('%Y-%m-%d %H%M')}"
        reel = ReelFolder.create(self.config.reel_root, name)
        info = self._camera.info()
        reel.write_reel_json(
            {
                "name": reel.name,
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
        journal = Journal(reel.journal_path)
        accounting = Accounting()
        token = object()
        saver = Saver(
            reel,
            journal,
            self._clock,
            self.config.save_queue,
            partial(self._on_save_error, accounting, token),
            partial(self._on_save_done, accounting),
            partial(self._on_durability_error, token),
        )
        saver.start()
        self.reel, self._journal, self.accounting, self._saver = reel, journal, accounting, saver
        self._reel_token = token
        self.segment = 1
        self._next_frame = 1
        self._gate.reset()
        self._intervals.clear()

    def _fail_pending_clicks(self, reason: str) -> None:
        for pending in self._picker.drain():
            self.accounting.failed_one()
            self._journal_event({"type": "failed", "frame": pending.frame_number, "reason": reason})

    def _replace_picker(self, reason: str) -> None:
        self._fail_pending_clicks(reason)
        self._picker = self._new_picker()

    def _detach_reel(self) -> tuple[Saver | None, Accounting, Journal | None]:
        """Under the lock: close the open reel; return its saver, accounting and journal."""
        self._replace_picker("reel closed")
        saver, accounting, journal = self._saver, self.accounting, self._journal
        self.reel = None
        self._journal = None
        self._saver = None
        self.segment = 0
        self._next_frame = 1
        return saver, accounting, journal

    def _drain_saver(
        self, saver: Saver | None, accounting: Accounting, journal: Journal | None
    ) -> None:
        """Call WITHOUT the machine lock (the saver callbacks need it): finish queued frames,
        book any the saver never wrote as failed, then the reel must be settled."""
        lost = saver.finish(30) if saver is not None else []
        with self._event():
            for n in lost:
                accounting.failed_one()
                self._journal_to(
                    journal,
                    {"type": "failed", "frame": n, "reason": "saver stopped before writing it"},
                )
            accounting.assert_settled()

    def _warn(self, text: str) -> None:
        self.warnings.append(text)
        self._alerter.alert("warning", self.config.name, text)
        self._journal_event({"type": "warning", "text": text})

    def _warn_not_ready(self) -> None:
        if self._not_ready_warned:
            return
        self._not_ready_warned = True
        self._warn(
            f"film is moving but {self.config.name} is not ready: frames are not being saved. "
            "Stop the WorkPrinter until it shows Ready"
        )

    def _fault(self, fault: Fault, film_moving: bool = False) -> None:
        """Raise a fault: once per kind while its condition persists. While recording, or when
        the film is known to be moving (film_moving), the machine stops with a STOP alarm."""
        if fault.kind in self._active_faults:
            return
        self._active_faults.add(fault.kind)
        self.fault_history.append(fault)
        self._journal_event(
            {"type": "fault", "kind": fault.kind, "message": fault.message, "segment": self.segment}
        )
        if self.state == MachineState.RECORDING or film_moving:
            if self.state == MachineState.RECORDING:
                self._fail_pending_clicks("segment stopped")
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
