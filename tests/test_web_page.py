import re
from pathlib import Path

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
