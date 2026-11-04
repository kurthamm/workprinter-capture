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
        self.dropped = 0
        self.closed = False

    def _put(self, a: Alert) -> None:
        if self.closed:
            return
        try:
            self._q.put_nowait(a)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            self._q.put_nowait(a)

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
            subs = list(self._subs)
        for s in subs:
            s._put(a)
        if forward and self._forward is not None:
            try:
                self._forward.alert(level, title, message)
            except Exception as e:  # noqa: BLE001 - delivery failure must never reach capture
                now = time.monotonic()
                if now - self._last_complaint >= self.FORWARD_COMPLAINT_INTERVAL_S:
                    self._last_complaint = now
                    self._publish("warning", "Phone alert failed", str(e), machine, forward=False)
