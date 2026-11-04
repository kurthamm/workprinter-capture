import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wpcap.alerts import AlertBus, NtfyAlerter, NtfyError, should_forward
from wpcap.config import NtfyConfig


def test_bus_keeps_recent_and_stamps_machine_and_ids():
    bus = AlertBus(keep=3)
    a = bus.for_machine("WorkPrinter 1")
    a.alert("info", "Reel finished", "100 frames")
    a.alert("warning", "w", "m")
    bus.for_machine("WorkPrinter 2").alert("problem", "STOP", "camera")
    a.alert("info", "fourth", "x")
    rec = bus.recent()
    assert [r.title for r in rec] == ["w", "STOP", "fourth"]  # keep=3 drops the oldest
    assert rec[1].machine == "WorkPrinter 2" and rec[1].level == "problem"
    assert [r.id for r in rec] == [2, 3, 4]
    assert rec[0].as_dict()["machine"] == "WorkPrinter 1"


def test_bus_rejects_bad_level():
    with pytest.raises(ValueError):
        AlertBus().for_machine("m").alert("loud", "t", "m")


def test_subscribers_get_alerts_in_order_and_time_out_quietly():
    bus = AlertBus()
    sub = bus.subscribe()
    assert sub.get(0.01) is None
    bus.for_machine("m").alert("info", "one", "")
    bus.for_machine("m").alert("info", "two", "")
    assert [sub.get(1).title, sub.get(1).title] == ["one", "two"]
    sub.close()
    assert bus.subscribers == 0


def test_subscriber_queue_is_bounded_and_dropped_on_close():
    bus = AlertBus()
    sub = bus.subscribe()
    for i in range(150):
        bus.for_machine("m").alert("info", str(i), "")
    assert sub.dropped == 50
    assert sub.get(0.1).title == "50"  # the oldest surviving one
    sub.close()
    bus.for_machine("m").alert("info", "after close", "")
    assert sub.get(0.01) is None
    assert bus.subscribers == 0


def test_alert_from_another_thread_reaches_a_waiting_subscriber():
    bus = AlertBus()
    sub = bus.subscribe()
    threading.Timer(
        0.05, lambda: bus.for_machine("m").alert("problem", "late", "")
    ).start()
    got = sub.get(2)
    assert got is not None and got.title == "late"


class _Ntfy(BaseHTTPRequestHandler):
    received: list[dict] = []
    fail = False

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = self.rfile.read(n).decode()
        _Ntfy.received.append(
            {
                "path": self.path,
                "body": body,
                "title": self.headers["Title"],
                "priority": self.headers["Priority"],
                "tags": self.headers["Tags"],
            }
        )
        self.send_response(500 if _Ntfy.fail else 200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture
def ntfy_server():
    _Ntfy.received, _Ntfy.fail = [], False
    srv = HTTPServer(("127.0.0.1", 0), _Ntfy)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_ntfy_posts_title_priority_and_tags(ntfy_server):
    n = NtfyAlerter(NtfyConfig(url=ntfy_server, topic="wp"))
    n.alert("problem", "STOP WorkPrinter 1 NOW", "camera stopped")
    n.alert("warning", "w", "m")
    n.alert("info", "Reel finished", "x")
    assert [r["path"] for r in _Ntfy.received] == ["/wp"] * 3
    assert [r["priority"] for r in _Ntfy.received] == ["urgent", "high", "default"]
    assert _Ntfy.received[0]["title"] == "STOP WorkPrinter 1 NOW"
    assert _Ntfy.received[0]["body"] == "camera stopped"
    assert _Ntfy.received[0]["tags"] == "rotating_light"


def test_ntfy_failure_raises(ntfy_server):
    _Ntfy.fail = True
    with pytest.raises(NtfyError):
        NtfyAlerter(NtfyConfig(url=ntfy_server, topic="wp")).alert("info", "t", "m")
    dead = NtfyConfig(url="http://127.0.0.1:9", topic="wp")
    with pytest.raises(NtfyError):
        NtfyAlerter(dead, timeout_s=0.5).alert("info", "t", "m")


def test_bus_reports_forward_failure_once_per_minute_and_keeps_going():
    class Dead:
        calls = 0

        def alert(self, level, title, message):
            Dead.calls += 1
            raise NtfyError("down")

    bus = AlertBus(forward=Dead())
    a = bus.for_machine("m")
    a.alert("warning", "one", "")
    a.alert("warning", "two", "")
    bus.close()
    titles = [r.title for r in bus.recent()]
    # the complaint arrives from the forwarder thread, so its position among
    # the machine's own alerts is not fixed; it is there exactly once
    assert [t for t in titles if t != "Phone alert failed"] == ["one", "two"]
    assert titles.count("Phone alert failed") == 1
    assert Dead.calls == 2  # it keeps trying; only the complaint is throttled


def test_forward_failure_warning_is_not_forwarded_again():
    class Dead:
        calls = 0

        def alert(self, level, title, message):
            Dead.calls += 1
            raise NtfyError("down")

    bus = AlertBus(forward=Dead())
    bus.for_machine("m").alert("problem", "p", "")
    bus.close()
    assert [r.title for r in bus.recent()] == ["p", "Phone alert failed"]
    assert Dead.calls == 1  # the "Phone alert failed" warning did not recurse into ntfy


def test_concurrent_publishers_on_a_full_subscriber_never_raise():
    bus = AlertBus()
    sub = bus.subscribe()  # never drained
    errors = []

    def publish(k):
        try:
            for i in range(200):
                bus.for_machine("m").alert("info", f"{k}-{i}", "")
        except Exception as e:  # noqa: BLE001 - the test reports it
            errors.append(e)

    threads = [threading.Thread(target=publish, args=(k,)) for k in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sub.dropped == 8 * 200 - 100
    held = [sub.get(0.1) for _ in range(100)]
    assert all(h is not None for h in held)
    assert sub.get(0.01) is None
    ids = [h.id for h in held]
    assert len(set(ids)) == 100
    assert all(1 <= i <= 8 * 200 for i in ids)


def test_slow_forwarder_does_not_delay_alert():
    class Slow:
        def alert(self, level, title, message):
            time.sleep(1)

    bus = AlertBus(forward=Slow())
    a = bus.for_machine("m")
    a.alert("warning", "warm", "")  # starts the thread; the next ones queue behind the sleep
    t0 = time.monotonic()
    a.alert("problem", "STOP", "")
    assert time.monotonic() - t0 < 0.05
    assert [r.title for r in bus.recent()] == ["warm", "STOP"]


def test_forward_queue_overflow_drops_oldest_and_complains():
    gate = threading.Event()
    seen = []

    class Blocked:
        def alert(self, level, title, message):
            gate.wait()
            seen.append(title)

    bus = AlertBus(forward=Blocked())
    a = bus.for_machine("m")
    for i in range(105):
        a.alert("warning", str(i), "")
    gate.set()
    bus.close()
    assert bus.forward_dropped >= 4
    assert any(r.title == "Phone alert failed" and r.message == "phone alert queue full"
               for r in bus.recent(200))
    assert seen[-1] == "104"


def test_only_problems_warnings_and_reel_finished_go_to_the_phone():
    assert should_forward("problem", "STOP WorkPrinter 1 NOW")
    assert should_forward("warning", "WorkPrinter 1")
    assert should_forward("info", "Reel finished — switch off WorkPrinter 1")
    assert not should_forward("info", "Recovered reel")
    with pytest.raises(ValueError):
        should_forward("loud", "x")


def test_bus_forwards_by_should_forward_and_keeps_everything_on_the_page():
    sent = []

    class Phone:
        def alert(self, level, title, message):
            sent.append(title)

    bus = AlertBus(forward=Phone())
    a = bus.for_machine("m")
    a.alert("info", "routine", "")
    a.alert("info", "Reel finished — switch off m", "")
    a.alert("problem", "STOP m NOW", "")
    bus.close()
    assert sent == ["Reel finished — switch off m", "STOP m NOW"]
    assert [r.title for r in bus.recent()] == [
        "routine", "Reel finished — switch off m", "STOP m NOW"
    ]


def test_close_waits_for_a_slow_backlog_instead_of_giving_up_after_one_timeout():
    class Slow:
        sent: list[str] = []

        def alert(self, level, title, message):
            time.sleep(0.3)
            Slow.sent.append(title)

    bus = AlertBus(forward=Slow())
    for n in range(3):
        bus.for_machine("m").alert("problem", f"p{n}", "")
    # 3 x 0.3 s of delivery against a 0.2 s base timeout: only a backlog-sized wait gets through
    bus.close(timeout_s=0.2, per_alert_s=1.0)
    assert Slow.sent == ["p0", "p1", "p2"]


def test_close_reports_how_many_alerts_were_not_delivered():
    release = threading.Event()

    class Stuck:
        def alert(self, level, title, message):
            release.wait(30)

    bus = AlertBus(forward=Stuck())
    for n in range(3):
        bus.for_machine("m").alert("problem", f"p{n}", "")
    try:
        with pytest.raises(TimeoutError, match=r"\d+ phone alerts undelivered"):
            bus.close(timeout_s=0.2, per_alert_s=0.1)
    finally:
        release.set()


def test_forwarded_alerts_are_queued_while_the_id_lock_is_held():
    class Quiet:
        def alert(self, level, title, message):
            pass

    bus = AlertBus(forward=Quiet())
    held = []
    real = bus._enqueue_forward_locked

    def spy(a):
        held.append(bus._lock.locked())
        return real(a)

    bus._enqueue_forward_locked = spy
    bus.for_machine("m").alert("problem", "x", "")
    bus.close()
    assert held == [True]
