import time
from pathlib import Path

import pytest

from wpcap.config import AppConfig, MachineSpec, ServerConfig
from wpcap.machine import MachineState
from wpcap.reel import Journal, ReelFolder
from wpcap.service import Service, ServiceError


def app_config(tmp_path: Path, names=("WorkPrinter 1", "WorkPrinter 2"), frames=30) -> AppConfig:
    machines = []
    for n in names:
        root = tmp_path / n
        root.mkdir(parents=True, exist_ok=True)
        machines.append(
            MachineSpec(name=n, kind="sim", reel_root=root, delay_ms=40.0, debounce_us=20000,
                        film_type="super8" if n.endswith("1") else "regular8", sim_frames=frames)
        )
    server = ServerConfig(
        "127.0.0.1", 8443, "scrypt$00$00", "x" * 64, tmp_path / "c", tmp_path / "k"
    )
    return AppConfig(server=server, machines=machines, ntfy=None)


def wait_for(pred, timeout_s):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def test_two_sim_machines_scan_at_once_and_snapshot_reports_both(tmp_path):
    # 40 frames: round(40 / 72, 1) = 0.6 but round(40 / 80, 1) = 0.5, so a wrong divisor shows.
    svc = Service(app_config(tmp_path, frames=40))
    svc.start()
    try:
        before = svc.machine("WorkPrinter 1").status()
        assert list(svc.runners) == ["WorkPrinter 1", "WorkPrinter 2"]
        assert wait_for(
            lambda: all(m["state"] == "reel_finished" for m in svc.snapshot()["machines"]), 25
        )
        snap = svc.snapshot()
        m1, m2 = snap["machines"]
        assert m1["saved"] >= 30 and m2["saved"] >= 30 and m1["failed"] == m2["failed"] == 0
        assert m1["film_type"] == "super8" and m2["film_type"] == "regular8"
        assert m1["feet"] == round(m1["saved"] / 72, 1) and m2["feet"] == round(m2["saved"] / 80, 1)
        assert m1["length_s"] == round(m1["saved"] / 18, 1)
        assert ReelFolder(tmp_path / "WorkPrinter 2" / m2["reel"]).read_reel_json()[
            "film_type"
        ] == "regular8"
        assert m1["saved"] >= before.frames_saved
        assert m1["saved"] + m1["pending"] + m1["failed"] == m1["clicks"]
        assert m1["free_gb"] is None or m1["free_gb"] > 0
        assert set(snap["pc"]) == {"cpu_percent", "memory_percent", "temperature_c"}
        assert m1["runner_alive"] and m1["runner_error"] is None
        assert svc.machine("WorkPrinter 2").status().state == MachineState.REEL_FINISHED
        with pytest.raises(KeyError):
            svc.machine("nope")
    finally:
        svc.stop()
    assert all(not r.alive for r in svc.runners.values())


def test_missing_reel_root_stops_startup(tmp_path):
    cfg = app_config(tmp_path)
    bad = cfg.machines[1].reel_root
    bad.rmdir()
    svc = Service(cfg)
    with pytest.raises(ServiceError, match="WorkPrinter 2") as e:
        svc.start()
    assert str(bad) in str(e.value)
    assert not bad.exists()  # never created on the wrong disk
    assert svc.runners == {}


def test_startup_recovery_repairs_and_warns(tmp_path):
    cfg = app_config(tmp_path, names=("WorkPrinter 1",))
    root = cfg.machines[0].reel_root
    folder = ReelFolder.create(root, "Old reel")
    j = Journal(folder.journal_path)
    j.append({"type": "segment_start", "t_ns": 1, "segment": 1, "first_frame": 1})
    j.append({"type": "click", "t_ns": 2, "frame": 1, "seq": 1})
    with folder.journal_path.open("ab") as f:
        f.write(b'{"type": "click", "fra')  # cut mid-line by a crash
    (folder.frames_dir / "000002.png.tmp").write_bytes(b"half")
    svc = Service(cfg)
    svc.start()
    try:
        assert len(svc.recovery_reports) == 1
        rep = svc.recovery_reports[0]
        # the stored report is the post-repair one: clean now (the journal was trimmed, tmp removed)
        assert not rep.journal_truncated and rep.half_written == ()
        assert rep.orphan_clicks == () and not rep.missing_final_newline
        assert not (folder.frames_dir / "000002.png.tmp").exists()
        warn = [a for a in svc.bus.recent() if a.title.startswith("Recovered reel")]
        assert len(warn) == 1 and warn[0].level == "warning" and "Old reel" in warn[0].title
    finally:
        svc.stop()


def test_stop_is_idempotent_and_start_twice_is_an_error(tmp_path):
    svc = Service(app_config(tmp_path, names=("WorkPrinter 1",)))
    svc.start()
    with pytest.raises(ServiceError):
        svc.start()
    svc.stop()
    svc.stop()


def test_failed_start_stops_every_runner_and_keeps_original_error(tmp_path, monkeypatch):
    stops = []

    class Fake:
        alive = False
        error = None

        def __init__(self, name, boom):
            self.name, self.boom = name, boom

        def start(self):
            if self.boom:
                raise RuntimeError("boom")

        def stop(self):
            stops.append(self.name)
            if self.name == "WorkPrinter 1":
                raise OSError("stop failed")

    monkeypatch.setattr(
        Service, "_build_runner", lambda self, spec: Fake(spec.name, spec.name.endswith("2"))
    )
    svc = Service(app_config(tmp_path))
    with pytest.raises(RuntimeError, match="boom") as e:
        svc.start()
    assert stops == ["WorkPrinter 1", "WorkPrinter 2"]
    assert any("OSError: stop failed" in n for n in e.value.__notes__)


def test_a_journaled_frame_with_no_picture_is_repaired_and_reported(tmp_path):
    from wpcap.recovery import RecoveryReport
    from wpcap.service import _needs_repair

    r = RecoveryReport.__new__(RecoveryReport)
    for f in RecoveryReport.__dataclass_fields__:
        object.__setattr__(r, f, () if f == "journaled_but_missing" else False)
    assert not _needs_repair(r)
    object.__setattr__(r, "journaled_but_missing", (7,))
    assert _needs_repair(r)
