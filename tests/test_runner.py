import time
from pathlib import Path

import pytest

from wpcap.alerts import AlertBus
from wpcap.config import MachineSpec
from wpcap.machine import MachineState, ReelMeta
from wpcap.runner import SimRunner


def spec(tmp_path: Path, frames: int = 40) -> MachineSpec:
    return MachineSpec(
        name="WorkPrinter 1", kind="sim", reel_root=tmp_path / "reels", delay_ms=40.0,
        debounce_us=20000, film_type="super8", sim_frames=frames,
    )


def wait_for(pred, timeout_s: float):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def test_sim_runner_scans_a_reel_in_real_time_and_stops_cleanly(tmp_path):
    bus = AlertBus()
    r = SimRunner(spec(tmp_path, frames=40), bus.for_machine("WorkPrinter 1"))
    r.start()
    assert r.alive
    assert wait_for(lambda: r.machine.status().state == MachineState.RECORDING, 10)
    assert wait_for(lambda: r.machine.status().state == MachineState.REEL_FINISHED, 20)
    st = r.machine.status()
    assert st.frames_saved >= 40 and st.frames_failed == 0
    assert any(a.title.startswith("Reel finished") for a in bus.recent())
    r.stop()
    assert not r.alive and r.error is None
    assert r.machine.status().state == MachineState.SHUT_DOWN


def test_stop_before_anything_happens_is_fine(tmp_path):
    r = SimRunner(spec(tmp_path), AlertBus().for_machine("WorkPrinter 1"))
    r.start()
    r.stop()
    assert not r.alive and r.error is None


def test_thread_death_is_reported_not_hidden(tmp_path, monkeypatch):
    bus = AlertBus()
    r = SimRunner(spec(tmp_path), bus.for_machine("WorkPrinter 1"))

    def boom(*a, **k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(r.rig, "run_realtime", boom)
    r.start()
    assert wait_for(lambda: not r.alive, 5)
    assert r.error is not None and "simulated crash" in r.error
    assert bus.recent()[-1].level == "problem" and "capture stopped" in bus.recent()[-1].title
    r.stop()  # idempotent after death


def test_new_reel_threads_fresh_film_and_the_demo_scans_again(tmp_path):
    bus = AlertBus()
    r = SimRunner(spec(tmp_path, frames=30), bus.for_machine("WorkPrinter 1"))
    r.start()
    assert wait_for(lambda: r.machine.status().state == MachineState.REEL_FINISHED, 20)
    first = r.machine.reel.path
    r.new_reel(ReelMeta(name="Second"))
    assert wait_for(lambda: r.machine.status().state == MachineState.RECORDING, 10)
    assert r.machine.reel.path != first
    r.stop()


def test_stop_twice_leaves_machine_shut_down(tmp_path):
    r = SimRunner(spec(tmp_path), AlertBus().for_machine("WorkPrinter 1"))
    r.start()
    r.stop()
    r.stop()
    assert r.machine.status().state == MachineState.SHUT_DOWN


def test_stop_after_crash_shuts_machine_down(tmp_path, monkeypatch):
    r = SimRunner(spec(tmp_path), AlertBus().for_machine("WorkPrinter 1"))

    def boom(*a, **k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(r.rig, "run_realtime", boom)
    r.start()
    assert wait_for(lambda: not r.alive, 5)
    r.stop()
    r.stop()
    assert r.machine.status().state == MachineState.SHUT_DOWN


def test_start_twice_raises(tmp_path):
    r = SimRunner(spec(tmp_path), AlertBus().for_machine("WorkPrinter 1"))
    r.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            r.start()
    finally:
        r.stop()


def test_new_reel_refused_by_the_machine_raises_here_and_keeps_the_runner_going(tmp_path):
    r = SimRunner(spec(tmp_path, frames=300), AlertBus().for_machine("WorkPrinter 1"))
    r.start()
    try:
        assert wait_for(lambda: r.machine.status().state == MachineState.RECORDING, 10)
        with pytest.raises(RuntimeError):
            r.new_reel(ReelMeta(name="Too soon"))  # recording: Stop first
        with pytest.raises(ValueError):
            r.new_reel(ReelMeta(name="what?"))
        assert r.alive and r.error is None
        assert r.machine.status().state == MachineState.RECORDING
    finally:
        r.stop()


def test_new_reel_on_a_dead_runner_raises(tmp_path):
    r = SimRunner(spec(tmp_path), AlertBus().for_machine("WorkPrinter 1"))
    with pytest.raises(RuntimeError, match="not running"):
        r.new_reel(ReelMeta(name="x"))


def test_a_second_new_reel_is_refused_until_the_first_has_been_applied(tmp_path, monkeypatch):
    r = SimRunner(spec(tmp_path), AlertBus().for_machine("WorkPrinter 1"))
    seen = []

    def new_reel(meta):
        seen.append(r._pending_job)  # still the job being applied, so a second request is refused

    monkeypatch.setattr(r.machine, "new_reel", new_reel)
    from wpcap.runner import _NewReelJob

    job = _NewReelJob(ReelMeta())
    r._pending_job = job
    r._apply(job)
    assert seen == [job] and r._pending_job is None and job.done.is_set()
