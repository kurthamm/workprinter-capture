"""Save frames to disk in a worker thread with a fixed-size queue (spec 7.1)."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from wpcap.camera import Picture
from wpcap.clock import Clock
from wpcap.reel import Journal, ReelFolder


class QueueFull(Exception):
    """The save queue is full: the disk is not keeping up. This is a fault, not a drop."""


class AccountingError(Exception):
    pass


class _FrameExists(FileExistsError):
    """The frame file appeared between submit and write; it is never replaced."""


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

    def assert_settled(self) -> None:
        """After a drain: balanced and nothing left in flight."""
        self.assert_balanced()
        if self.pending != 0:
            raise AccountingError(f"{self.pending} frames still pending after the drain")

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
        self._inflight: set[int] = set()

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
        with self._lock:
            if frame_number in self._inflight:
                raise FileExistsError(f"frame {frame_number} is already queued for saving")
            self._inflight.add(frame_number)
            self._submitted += 1
        try:
            self._q.put_nowait((frame_number, picture))
        except queue.Full as e:
            with self._lock:
                self._inflight.discard(frame_number)
                self._submitted -= 1
            raise QueueFull(f"save queue full ({self._q.maxsize}) at frame {frame_number}") from e

    def join(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while self.pending > 0:
            if not self.alive:
                raise RuntimeError(f"saver thread is not running with {self.pending} frames queued")
            if time.monotonic() > deadline:
                raise TimeoutError(f"saver still has {self.pending} frames after {timeout_s} s")
            time.sleep(0.005)

    def wait_idle(self, timeout_s: float) -> None:
        """Wait until every queued frame is written or the worker has died."""
        deadline = time.monotonic() + timeout_s
        while self.pending > 0 and self.alive:
            if time.monotonic() > deadline:
                raise TimeoutError(f"saver still has {self.pending} frames after {timeout_s} s")
            time.sleep(0.005)

    def finish(self, timeout_s: float) -> list[int]:
        """Write what is queued, stop the worker, and return the frames it never wrote.

        The list is empty unless the worker died; those frames are booked as errors here so
        the caller can record them as failed.
        """
        self.wait_idle(timeout_s)
        self.stop()
        with self._lock:
            lost = sorted(self._inflight)
            self._inflight.clear()
            self.errors += len(lost)
        return lost

    def stop(self) -> None:
        if self._thread is None:
            return
        if not self._thread.is_alive():
            self._thread = None
            return
        try:
            self._q.put(None, timeout=10)
        except queue.Full as e:
            raise TimeoutError(f"saver queue stuck full with {self.pending} frames pending") from e
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise TimeoutError(f"saver did not stop; {self.pending} frames pending")
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
            Image.fromarray(picture.pixels).save(tmp, format="PNG", compress_level=1)
            if path.exists():
                raise _FrameExists(f"frame already exists: {path}")
            tmp.replace(path)
        except Exception as exc:  # noqa: BLE001 - every failure is journaled and reported upward
            self._write_failed(frame_number, tmp, exc)
            return
        # The frame is on disk. Anything failing from here is not a write failure; it
        # propagates, ends the worker, and `alive` goes false for the machine to fault on.
        try:
            self._journal.append(
                {
                    "type": "saved",
                    "t_ns": self._clock.now_ns(),
                    "frame": frame_number,
                    "picture_index": picture.index,
                    "t_pic_ns": picture.t_ns,
                }
            )
        except OSError:
            # The frame is complete on disk, so it is booked as saved (recovery lists it as
            # on disk but not journaled); then the worker ends and the machine faults.
            self._book_saved(frame_number)
            raise
        self._book_saved(frame_number)

    def _book_saved(self, frame_number: int) -> None:
        with self._lock:
            self.saved += 1
            self._inflight.discard(frame_number)
        self._on_saved(frame_number)

    def _write_failed(self, frame_number: int, tmp: Path, exc: Exception) -> None:
        """Remove the temp file, journal `failed`, report. Never dies on the way: a failure
        here (temp file stuck, journal unwritable) is added to what is reported."""
        reason = str(exc) if isinstance(exc, _FrameExists) else f"write error: {exc}"
        problems: list[str] = []
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError as e:
            problems.append(f"temp file not removed: {e}")
        with self._lock:
            self.errors += 1
            self._inflight.discard(frame_number)
        try:
            self._journal.append(
                {
                    "type": "failed",
                    "t_ns": self._clock.now_ns(),
                    "frame": frame_number,
                    "reason": reason,
                }
            )
        except OSError as e:
            problems.append(f"journal not written: {e}")
        if problems:
            self._on_error(frame_number, OSError("; ".join([reason, *problems])))
        else:
            self._on_error(frame_number, exc)
