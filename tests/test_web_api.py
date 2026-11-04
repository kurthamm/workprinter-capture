import io
import json
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from wpcap.config import AppConfig, MachineSpec, ServerConfig, hash_password, new_secret
from wpcap.machine import MachineState
from wpcap.service import Service
from wpcap.web.app import create_app

PW = "open sesame"


def app_config(tmp_path: Path, frames=30) -> AppConfig:
    machines = []
    for n in ("WorkPrinter 1", "WorkPrinter 2"):
        root = tmp_path / n
        root.mkdir(parents=True)
        machines.append(MachineSpec(n, "sim", root, 40.0, 20000, "super8", frames))
    server = ServerConfig(
        "127.0.0.1", 8443, hash_password(PW), new_secret(), tmp_path / "c", tmp_path / "k"
    )
    return AppConfig(server=server, machines=machines, ntfy=None)


def wait_for(pred, timeout_s):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


@pytest.fixture
def svc(tmp_path):
    s = Service(app_config(tmp_path))
    s.start()
    yield s
    s.stop()


@pytest.fixture
def client(svc):
    app = create_app(svc, svc.config)
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def login(c):
    r = c.post("/api/login", json={"password": PW})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert "wpcap_session" in c.cookies


def test_healthz_is_public_and_api_is_not(client):
    assert client.get("/healthz").json() == {"ok": True}
    r = client.get("/api/status")
    assert r.status_code == 401 and r.json() == {"error": "login required"}
    assert client.post("/api/machines/WorkPrinter 1/stop").status_code == 401


def test_wrong_password_is_slow_and_rejected(client):
    t0 = time.monotonic()
    r = client.post("/api/login", json={"password": "nope"})
    assert r.status_code == 401 and r.json()["error"] == "wrong password"
    assert time.monotonic() - t0 >= 0.9
    assert "wpcap_session" not in client.cookies
    login(client)  # the right one still works


def test_login_cookie_is_httponly_secure_strict(client):
    r = client.post("/api/login", json={"password": PW})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "secure" in sc and "samesite=strict" in sc


def test_logout_clears_access(client):
    login(client)
    assert client.get("/api/status").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/status").status_code == 401


def test_status_lists_both_machines(client):
    login(client)
    s = client.get("/api/status").json()
    assert [m["name"] for m in s["machines"]] == ["WorkPrinter 1", "WorkPrinter 2"]
    assert "pc" in s


def test_unknown_machine_is_404(client):
    login(client)
    r = client.get("/api/machines/Nope/live.jpg")
    assert r.status_code == 404 and "Nope" in r.json()["error"]


def test_live_and_last_frame_jpegs(client, svc):
    login(client)
    assert wait_for(lambda: svc.machine("WorkPrinter 1").last_saved() is not None, 15)
    r = client.get("/api/machines/WorkPrinter 1/live.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"
    im = Image.open(io.BytesIO(r.content))
    assert im.format == "JPEG" and im.width <= 640
    r = client.get("/api/machines/WorkPrinter 1/last.jpg")
    assert r.status_code == 200 and int(r.headers["x-frame-number"]) >= 1


def test_stop_resume_and_new_reel_flow(client, svc):
    login(client)
    m = svc.machine("WorkPrinter 1")
    assert wait_for(lambda: m.status().state == MachineState.RECORDING, 15)
    assert client.post("/api/machines/WorkPrinter 1/stop").status_code == 200
    assert m.status().state == MachineState.STOPPED
    r = client.post("/api/machines/WorkPrinter 1/resume")
    assert r.status_code == 200
    assert m.status().state in (MachineState.READY, MachineState.NOT_READY)
    r = client.post("/api/machines/WorkPrinter 1/resume")
    assert r.status_code == 409 and "resume" in r.json()["error"]
    # the sim film is still running after Resume; a new reel needs the machine stopped
    assert client.post("/api/machines/WorkPrinter 1/stop").status_code == 200
    r = client.post(
        "/api/machines/WorkPrinter 1/new-reel",
        json={
            "name": "Smith job 12 reel 3",
            "film_type": "regular8",
            "notes": "n",
            "customer": "Smith",
            "job_number": "12",
        },
    )
    assert r.status_code == 200 and r.json()["reel"] == "Smith job 12 reel 3", r.json()
    assert wait_for(lambda: m.status().state == MachineState.RECORDING, 15)  # fresh sim film
    assert m.reel.read_reel_json()["customer"] == "Smith"


def test_new_reel_bad_name_is_400(client, svc):
    login(client)
    m = svc.machine("WorkPrinter 2")
    assert wait_for(lambda: m.status().state == MachineState.RECORDING, 15)
    before = m.reel.path
    client.post("/api/machines/WorkPrinter 2/stop")
    for bad in ("CON", "ends with dot.", "what?"):
        r = client.post(
            "/api/machines/WorkPrinter 2/new-reel", json={"name": bad, "film_type": "super8"}
        )
        assert r.status_code == 400, bad
        assert r.json()["error"]
    assert m.reel.path == before and m.status().state == MachineState.STOPPED


def test_calibration_and_delay(client, svc):
    login(client)
    m = svc.machine("WorkPrinter 1")
    assert wait_for(lambda: m.last_saved() is not None, 15)
    cal_url = "/api/machines/WorkPrinter 1/calibration"
    # the window around the latest click fills as the pictures after it arrive
    got: list[dict] = []

    def full_window() -> bool:
        got[:] = [client.get(cal_url).json()]
        return len(got[0]["pictures"]) == 7

    assert wait_for(full_window, 15)
    cal = got[0]
    assert cal["delay_ms"] == 40.0 and len(cal["pictures"]) == 7
    offsets = [p["offset_ms"] for p in cal["pictures"]]
    assert offsets == sorted(offsets)
    r = client.get(cal["pictures"][3]["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    r = client.post("/api/machines/WorkPrinter 1/delay", json={"delay_ms": 55.0})
    assert r.status_code == 409  # recording
    client.post("/api/machines/WorkPrinter 1/stop")
    assert (
        client.post("/api/machines/WorkPrinter 1/delay", json={"delay_ms": 55.0}).status_code == 200
    )
    assert client.get("/api/status").json()["machines"][0]["delay_ms"] == 55.0
    assert (
        client.post("/api/machines/WorkPrinter 1/delay", json={"delay_ms": -5}).status_code == 400
    )
    assert client.post("/api/machines/WorkPrinter 1/delay", json={"delay": 5}).status_code == 400


def test_events_stream_sends_hello_status_and_alerts(client, svc):
    login(client)
    with client.stream("GET", "/api/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        seen = {"hello": False, "status": False, "alert": False}
        buf = ""
        start = time.monotonic()
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                lines = block.splitlines()
                ev = next((x[7:] for x in lines if x.startswith("event: ")), None)
                data = next((x[6:] for x in lines if x.startswith("data: ")), None)
                if ev == "hello":
                    assert "alerts" in json.loads(data)
                    svc.bus.for_machine("WorkPrinter 1").alert("problem", "STOP", "test alarm")
                if ev == "status":
                    assert json.loads(data)["machines"][0]["name"] == "WorkPrinter 1"
                if ev == "alert" and json.loads(data)["title"] == "STOP":
                    seen["alert"] = True
                if ev in seen:
                    seen[ev] = True
            if all(seen.values()) or time.monotonic() - start > 10:
                break
        assert all(seen.values()), seen


def test_alerts_endpoint(client, svc):
    login(client)
    svc.bus.for_machine("WorkPrinter 2").alert("warning", "w", "m")
    a = client.get("/api/alerts").json()["alerts"]
    assert a[-1]["title"] == "w" and a[-1]["machine"] == "WorkPrinter 2"


def test_to_jpeg_scales_down_only():
    from wpcap.pictures import to_jpeg

    big = np.zeros((900, 1600, 3), dtype=np.uint8)
    im = Image.open(io.BytesIO(to_jpeg(big, max_width=640)))
    assert (im.width, im.height) == (640, 360)
    small = np.zeros((108, 192, 3), dtype=np.uint8)
    im = Image.open(io.BytesIO(to_jpeg(small, max_width=640)))
    assert (im.width, im.height) == (192, 108)
