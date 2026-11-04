"""Alerts: one bus per process. Machines call alert(); the page and ntfy listen."""

from __future__ import annotations

import queue
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass

from wpcap.config import NtfyConfig
from wpcap.machine import Alerter

LEVELS = ("info", "warning", "problem")
_PRIORITY = {"problem": "urgent", "warning": "high", "info": "default"}
_TAGS = {"problem": "rotating_light", "warning": "warning", "info": "white_check_mark"}


def should_forward(level: str, title: str) -> bool:
    """Spec 6.5: the phone hears about problems, warnings and a finished reel; other info
    (routine notices) stays on the page."""
    if level not in LEVELS:
        raise ValueError(f"bad alert level {level}")
    return level != "info" or title.startswith("Reel finished")


@dataclass(frozen=True)
class Alert:
    level: str
    title: str
    message: str
    t: float  # time.time()
    machine: str
    id: int

    def as_dict(self) -> dict:
        return asdict(self)


class NtfyError(Exception):
    pass


class NtfyAlerter:
    def __init__(self, cfg: NtfyConfig, timeout_s: float = 3.0) -> None:
        self._url = f"{cfg.url}/{cfg.topic}"
        self._timeout = timeout_s

    def alert(self, level: str, title: str, message: str) -> None:
        if level not in LEVELS:
            raise ValueError(f"bad alert level {level}")
        req = urllib.request.Request(
            self._url,
            data=message.encode("utf-8"),
            method="POST",
            headers={
                "Title": title.encode("utf-8").decode("latin-1", "replace"),
                "Priority": _PRIORITY[level],
                "Tags": _TAGS[level],
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                if r.status != 200:
                    raise NtfyError(f"ntfy answered {r.status}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise NtfyError(f"ntfy at {self._url}: {e}") from e


class Subscription:
    def __init__(self, bus: AlertBus, size: int = 100) -> None:
        self._bus = bus
        self._q: queue.Queue[Alert] = queue.Queue(maxsize=size)
        self._put_lock = threading.Lock()
        self.dropped = 0
        self.closed = False

    def _put(self, a: Alert) -> None:
        if self.closed:
            return
        with self._put_lock:
            while True:
                try:
                    self._q.put_nowait(a)
                    return
                except queue.Full:
                    try:
                        self._q.get_nowait()
                    except queue.Empty:
                        continue  # a reader just made room
                    self.dropped += 1

    def get(self, timeout: float) -> Alert | None:
        if self.closed:
            return None
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True
        self._bus._unsubscribe(self)


class _MachineAlerter:
    def __init__(self, bus: AlertBus, machine: str) -> None:
        self._bus, self._machine = bus, machine

    def alert(self, level: str, title: str, message: str) -> None:
        self._bus._publish(level, title, message, self._machine)


class AlertBus:
    """Keeps the last `keep` alerts, wakes subscribers, forwards to `forward` (ntfy)."""

    FORWARD_COMPLAINT_INTERVAL_S = 60.0

    def __init__(self, forward: Alerter | None = None, keep: int = 200) -> None:
        self._forward = forward
        self._recent: deque[Alert] = deque(maxlen=keep)
        self._subs: set[Subscription] = set()
        self._lock = threading.Lock()
        self._next_id = 1
        self._last_complaint = -1e12
        self._fq: queue.Queue[Alert | None] = queue.Queue(maxsize=100)
        self._fthread: threading.Thread | None = None
        self._fclosed = False
        self.forward_dropped = 0

    def for_machine(self, name: str) -> Alerter:
        return _MachineAlerter(self, name)

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subs)

    def recent(self, limit: int = 50) -> list[Alert]:
        with self._lock:
            return list(self._recent)[-limit:]

    def subscribe(self) -> Subscription:
        sub = Subscription(self)
        with self._lock:
            self._subs.add(sub)
        return sub

    def _unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subs.discard(sub)

    def _publish(
        self, level: str, title: str, message: str, machine: str, forward: bool = True
    ) -> None:
        if level not in LEVELS:
            raise ValueError(f"bad alert level {level}")
        with self._lock:
            a = Alert(level, title, message, time.time(), machine, self._next_id)
            self._next_id += 1
            self._recent.append(a)
            # Under the lock so two machine threads reach every subscriber in id order.
            # Subscription._put takes only its own lock and never calls back into the bus.
            for s in self._subs:
                s._put(a)
            # Also under it: the phone gets alerts in id order, and close() cannot slip its
            # stop sentinel in between the id and the enqueue.
            full = (
                forward
                and self._forward is not None
                and should_forward(level, title)
                and self._enqueue_forward_locked(a)
            )
        if full:
            self._complain("phone alert queue full", machine)

    def _complain(self, message: str, machine: str) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_complaint < self.FORWARD_COMPLAINT_INTERVAL_S:
                return
            self._last_complaint = now
        self._publish("warning", "Phone alert failed", message, machine, forward=False)

    def _enqueue_forward_locked(self, a: Alert) -> bool:
        """With self._lock held: hand the alert to the forwarder thread; never blocks, never
        raises. Returns True when the queue was full and the oldest alert was dropped."""
        if self._fclosed:
            return False
        if self._fthread is None:
            self._fthread = threading.Thread(
                target=self._forward_loop, name="alert-forwarder", daemon=True
            )
            self._fthread.start()
        full = False
        while True:
            try:
                self._fq.put_nowait(a)
                return full
            except queue.Full:
                full = True
                try:
                    self._fq.get_nowait()
                except queue.Empty:
                    continue
                self.forward_dropped += 1

    def _forward_loop(self) -> None:
        assert self._forward is not None
        while True:
            a = self._fq.get()
            if a is None:
                return
            try:
                self._forward.alert(a.level, a.title, a.message)
            except Exception as e:  # noqa: BLE001 - delivery failure must never reach capture
                self._complain(str(e), a.machine)

    def close(
        self, timeout_s: float = 5.0, per_alert_s: float = 3.5, max_wait_s: float = 60.0
    ) -> None:
        """Deliver what is queued, then stop the forwarder thread. Each queued alert may take a
        phone request's full timeout, so the wait grows with the backlog (up to max_wait_s);
        if it still runs out, the error says how many alerts were not delivered."""
        with self._lock:
            self._fclosed = True
            t = self._fthread
        if t is None:
            return
        deadline = time.monotonic() + min(max_wait_s, timeout_s + self._fq.qsize() * per_alert_s)
        try:
            self._fq.put(None, timeout=max(0.0, deadline - time.monotonic()))
        except queue.Full as e:
            raise TimeoutError(
                f"alert forwarder did not accept the stop sentinel; "
                f"{self._fq.qsize()} phone alerts undelivered"
            ) from e
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            raise TimeoutError(
                f"alert forwarder did not stop; {self._fq.qsize()} phone alerts undelivered"
            )
