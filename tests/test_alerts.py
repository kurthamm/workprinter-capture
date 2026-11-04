import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wpcap.alerts import AlertBus, NtfyAlerter, NtfyError
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
    a.alert("info", "one", "")
    a.alert("info", "two", "")
    titles = [r.title for r in bus.recent()]
    assert titles == ["one", "Phone alert failed", "two"]
    assert Dead.calls == 2  # it keeps trying; only the complaint is throttled


def test_forward_failure_warning_is_not_forwarded_again():
    class Dead:
        calls = 0

        def alert(self, level, title, message):
            Dead.calls += 1
            raise NtfyError("down")

    bus = AlertBus(forward=Dead())
    bus.for_machine("m").alert("problem", "p", "")
    assert Dead.calls == 1  # the "Phone alert failed" warning did not recurse into ntfy
