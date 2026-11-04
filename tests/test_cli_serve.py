import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from wpcap.config import load_config, verify_password


def run(*args, input_text=None, timeout=60):
    return subprocess.run(
        [sys.executable, "-m", "wpcap", *args],
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
    )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_hash_password_from_stdin_and_flag():
    r = run("hash-password", input_text="secret\n")
    assert r.returncode == 0 and verify_password("secret", r.stdout.strip())
    r = run("hash-password", "--password", "secret")
    assert r.returncode == 0 and verify_password("secret", r.stdout.strip())


def test_init_config_writes_everything_and_refuses_overwrite(tmp_path):
    out = tmp_path / "wpcap.toml"
    r = run(
        "init-config",
        "--out",
        str(out),
        "--reels",
        str(tmp_path / "reels"),
        "--certs",
        str(tmp_path / "certs"),
        "--password",
        "pw",
    )
    assert r.returncode == 0, r.stderr
    cfg = load_config(out)
    assert verify_password("pw", cfg.server.password_hash)
    assert cfg.server.cert_file.exists() and cfg.server.key_file.exists()
    assert (tmp_path / "certs" / "ca.crt").exists()
    assert all(m.reel_root.is_dir() for m in cfg.machines)
    r = run(
        "init-config",
        "--out",
        str(out),
        "--reels",
        str(tmp_path / "reels"),
        "--certs",
        str(tmp_path / "certs"),
        "--password",
        "pw",
    )
    assert r.returncode != 0 and "exists" in r.stderr


def test_gen_cert_adds_names(tmp_path):
    out = tmp_path / "wpcap.toml"
    assert (
        run(
            "init-config",
            "--out",
            str(out),
            "--reels",
            str(tmp_path / "r"),
            "--certs",
            str(tmp_path / "c"),
            "--password",
            "pw",
        ).returncode
        == 0
    )
    r = run("gen-cert", "--certs", str(tmp_path / "c"), "--host", "scanpc", "--ip", "100.73.196.61")
    assert r.returncode != 0 and "replace" in r.stderr
    r = run(
        "gen-cert",
        "--certs",
        str(tmp_path / "c"),
        "--host",
        "scanpc",
        "--ip",
        "100.73.196.61",
        "--replace",
    )
    assert r.returncode == 0, r.stderr
    from cryptography import x509

    cert = x509.load_pem_x509_certificate((tmp_path / "c" / "wpcap.crt").read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "scanpc" in san.get_values_for_type(x509.DNSName)


def test_serve_bad_config_exits_with_message(tmp_path):
    bad = tmp_path / "wpcap.toml"
    bad.write_text("[server]\nport = 1\n")
    r = run("serve", "--config", str(bad))
    assert r.returncode == 2 and "missing server." in r.stderr


@pytest.mark.skipif(os.name == "nt", reason="SIGINT handling differs; covered on Linux")
def test_serve_runs_https_scans_and_stops_on_sigint(tmp_path):
    out = tmp_path / "wpcap.toml"
    port = free_port()
    assert (
        run(
            "init-config",
            "--out",
            str(out),
            "--reels",
            str(tmp_path / "r"),
            "--certs",
            str(tmp_path / "c"),
            "--password",
            "pw",
            "--port",
            str(port),
            "--bind",
            "127.0.0.1",
            "--sim-frames",
            "40",
        ).returncode
        == 0
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "wpcap", "serve", "--config", str(out)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        ctx = ssl.create_default_context(cafile=str(tmp_path / "c" / "ca.crt"))
        url = f"https://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(f"{url}/healthz", context=ctx, timeout=2) as r:
                    assert json.loads(r.read()) == {"ok": True}
                    break
            except (OSError, urllib.error.URLError):
                if time.monotonic() > deadline:
                    proc.kill()
                    pytest.fail("server did not come up:\n" + proc.stdout.read())
                time.sleep(0.3)
        # the certificate is trusted through our CA, so the login works over HTTPS
        req = urllib.request.Request(
            f"{url}/api/login",
            data=b'{"password": "pw"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, context=ctx, timeout=5) as r:
            cookie = r.headers["set-cookie"].split(";")[0]
        deadline = time.monotonic() + 30
        while True:
            req = urllib.request.Request(f"{url}/api/status", headers={"Cookie": cookie})
            with urllib.request.urlopen(req, context=ctx, timeout=5) as r:
                snap = json.loads(r.read())
            if all(m["state"] == "reel_finished" for m in snap["machines"]):
                break
            assert time.monotonic() < deadline, snap
            time.sleep(0.5)
        assert all(m["saved"] >= 40 and m["failed"] == 0 for m in snap["machines"])
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("serve did not stop on SIGINT")
    out_text = proc.stdout.read()
    assert proc.returncode == 0, out_text
    assert "stopped" in out_text.lower()
    # the reels were closed cleanly: journals end with a terminated line and no temp files remain
    for root in (tmp_path / "r").iterdir():
        for reel in root.iterdir():
            assert not list((reel / "frames").glob("*.tmp"))
            assert (reel / "journal.jsonl").read_bytes().endswith(b"\n")


def test_scan_continues_with_no_web_client(tmp_path):
    """Review Focus 2: nobody is looking; the scan still completes. (The service alone.)"""
    from test_service import app_config, wait_for

    from wpcap.service import Service

    svc = Service(app_config(tmp_path, names=("WorkPrinter 1",), frames=30))
    svc.start()
    try:
        assert wait_for(lambda: svc.snapshot()["machines"][0]["state"] == "reel_finished", 25)
        assert svc.bus.subscribers == 0
        assert len(svc.bus.recent()) >= 1
    finally:
        svc.stop()


@pytest.mark.skipif(os.name == "nt", reason="signal handling differs; covered on Linux")
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_serve_stops_while_event_stream_is_open(tmp_path, sig):
    out = tmp_path / "wpcap.toml"
    port = free_port()
    args = ["init-config", "--out", str(out), "--reels", str(tmp_path / "r")]
    args += ["--certs", str(tmp_path / "c"), "--password", "pw", "--port", str(port)]
    args += ["--bind", "127.0.0.1", "--sim-frames", "40"]
    assert run(*args).returncode == 0
    cmd = [sys.executable, "-m", "wpcap", "serve", "--config", str(out)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    stream = None
    try:
        ctx = ssl.create_default_context(cafile=str(tmp_path / "c" / "ca.crt"))
        url = f"https://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                req = urllib.request.Request(
                    f"{url}/api/login",
                    data=b'{"password": "pw"}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, context=ctx, timeout=2) as r:
                    cookie = r.headers["set-cookie"].split(";")[0]
                break
            except OSError:
                if time.monotonic() > deadline:
                    proc.kill()
                    pytest.fail("server did not come up:\n" + proc.stdout.read())
                time.sleep(0.3)
        req = urllib.request.Request(f"{url}/api/events", headers={"Cookie": cookie})
        stream = urllib.request.urlopen(req, context=ctx, timeout=10)
        assert b"event: hello" in stream.readline() + stream.readline()
    finally:
        proc.send_signal(sig)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("serve did not stop with the event stream open")
        finally:
            if stream is not None:
                stream.close()
    out_text = proc.stdout.read()
    assert proc.returncode == 0, out_text
    assert "stopped" in out_text.lower()


def test_stop_signals_cover_every_signal_uvicorn_reraises():
    import uvicorn.server

    from wpcap.__main__ import stop_signals

    assert set(uvicorn.server.HANDLED_SIGNALS) <= set(stop_signals())
    if sys.platform == "win32":
        assert signal.SIGBREAK in stop_signals()
