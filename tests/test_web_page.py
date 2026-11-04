import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_web_api import app_config  # reuse the fixture helper

from wpcap.service import Service
from wpcap.web.app import create_app

STATIC = Path(__file__).parent.parent / "src/wpcap/web/static"


def test_page_and_assets_are_served(tmp_path):
    svc = Service(app_config(tmp_path))
    svc.start()
    try:
        with TestClient(create_app(svc, svc.config), base_url="https://testserver") as c:
            r = c.get("/")
            assert r.status_code == 200 and "WorkPrinter Capture" in r.text
            assert r.headers["cache-control"] == "no-store"
            assert c.get("/static/app.js").status_code == 200
            assert c.get("/static/style.css").status_code == 200
    finally:
        svc.stop()


def test_javascript_only_calls_endpoints_that_exist(tmp_path):
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    pattern = (
        r"""['"`](/api/[a-z\-]+"""
        r"""(?:/\$\{[a-zA-Z.()]+\}|/[a-z\-]+|/\$\{i\}\.jpg)*(?:\.jpg)?)"""
    )
    called = set(re.findall(pattern, js))
    svc = Service(app_config(tmp_path))
    app = create_app(svc, svc.config)
    routes = {r.path for r in app.routes}
    base = (
        "/api/machines/${encodeURIComponent(name)}"  # app.js prefix
    )
    assert base in called, "app.js no longer builds machine paths from the expected prefix"
    called.discard(base)
    called |= {base + s for s in re.findall(r"\$\{path\}(/[a-z\-]+(?:\.jpg)?)", js)}
    for c in called:
        normalized = re.sub(r"\$\{[^}]+\}", "{x}", c)
        assert any(
            re.fullmatch(re.sub(r"\{[a-z_]+\}", r"[^/]+", rp), normalized.replace("{x}", "X"))
            for rp in routes
        ), f"app.js calls {c} which has no route"
    assert called, "the regex found no API calls; check app.js uses string literals for paths"


def test_page_mentions_every_state_and_the_alarm():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for s in ("not_ready", "ready", "recording", "reel_finished", "stopped", "shut_down"):
        assert s in js, s
    assert "AudioContext" in js and "Notification" in js
    assert "Silence" in html and "New Reel" in html and "Resume" in html and "Calibrate" in html


def test_page_never_swallows_errors_and_forgets_silenced_faults_once_gone():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"catch\(\s*\(\)\s*=>\s*(\{\s*\}|\(\{\s*\}\))\s*\)", js)
    assert "console.error" in js and "instanceof LoginRequired" in js
    assert "silencedFaults.delete" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to parse app.js")
def test_javascript_parses():
    r = subprocess.run(
        ["node", "--check", str(STATIC / "app.js")], capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 0, r.stderr


def test_page_chimes_for_alerts_missed_while_disconnected_and_silences_before_the_next_status():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "d.alerts.filter((a) => a.id > since).forEach(react)" in js
    assert "pendingSilence" in js and "alertedMachines.add(a.machine)" in js


def test_machine_grid_column_never_exceeds_the_screen():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "minmax(min(340px, 100%), 1fr)" in css
