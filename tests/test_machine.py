import os
import stat
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from wpcap.machine import MachineConfig, MachineState, ReelMeta
from wpcap.reel import Journal, ReelFolder
from wpcap.sim.camera import decode_number
from wpcap.sim.film import SimFilm
from wpcap.sim.rig import SimRig

S = 1_000_000_000


def cfg(tmp_path, **kw):
    base = dict(
        name="WorkPrinter 1", reel_root=tmp_path / "reels", gate_min_frames=20, gate_empty_needed=8
    )
    base.update(kw)
    return MachineConfig(**base)


def frame_numbers(folder: ReelFolder) -> list[int | None]:
    out = []
    for p in sorted(folder.frames_dir.glob("*.png")):
        out.append(decode_number(np.asarray(Image.open(p))))
    return out


def test_becomes_ready_after_sync_and_first_picture(tmp_path):
    rig = SimRig(cfg(tmp_path), SimFilm(frames=0, start_ns=10 * S))
    assert rig.machine.status().state == MachineState.NOT_READY
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.READY


def test_scans_every_frame_once_in_order(tmp_path):
    film = SimFilm(frames=200, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(3 * S + 260 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.REEL_FINISHED
    assert st.frames_failed == 0
    assert st.frames_saved == 200 + 8  # 200 pictures + the 8 empty frames that proved the end
    rig.machine.shutdown()
    nums = frame_numbers(ReelFolder.open(rig.machine.reel.path))
    assert nums[:200] == list(range(1, 201))
    assert all(n == 2**24 - 1 for n in nums[200:])  # empty gate frames
    assert any("Reel finished" in a[1] for a in rig.alerts)
    assert rig.machine.accounting.balanced()


def test_delay_absorbs_switch_offset(tmp_path):
    # Switch closes 40 ms before the frame is still (old timing-disk setting).
    film = SimFilm(frames=60, start_ns=3 * S, switch_offset_ms=-40.0)
    rig = SimRig(cfg(tmp_path, delay_ms=45.0), film)
    rig.run_until(3 * S + 70 * film.period_ns)
    rig.machine.shutdown()
    nums = frame_numbers(ReelFolder.open(rig.machine.reel.path))
    assert nums[:60] == list(range(1, 61))


def test_wrong_delay_lands_on_blur_and_is_visible(tmp_path):
    film = SimFilm(frames=30, start_ns=3 * S, switch_offset_ms=-20.0)
    rig = SimRig(cfg(tmp_path, delay_ms=0.0), film)  # click is 20 ms before still → blurred
    rig.run_until(3 * S + 40 * film.period_ns)
    rig.machine.shutdown()
    nums = frame_numbers(ReelFolder.open(rig.machine.reel.path))
    assert nums[:30].count(None) > 20


def test_leader_does_not_finish_reel(tmp_path):
    film = SimFilm(frames=80, leader_frames=30, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, gate_min_frames=20), film)
    rig.run_until(3 * S + 40 * film.period_ns)
    assert rig.machine.status().state == MachineState.RECORDING


def test_bounce_is_counted_not_saved(tmp_path):
    film = SimFilm(frames=20, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.switch_times.insert(5, film.switch_ns(5) + 3_000_000)  # 3 ms after click 5
    rig.run_until(3 * S + 30 * film.period_ns)
    st = rig.machine.status()
    assert st.bounces == 1 and st.frames_saved >= 20 and st.frames_failed == 0


def test_dropped_sync_message_is_fault_and_frames_kept(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 50 * film.period_ns)
    rig.box.drop_next = True
    rig.run_until(3 * S + 60 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "sync"
    assert st.frames_saved >= 49
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    rig.machine.resume()
    rig.run_for(S)
    assert rig.machine.status().state in (MachineState.READY, MachineState.RECORDING)
    rig.machine.shutdown()
    assert rig.machine.accounting.balanced()


def test_missing_click_is_missed_frame_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    del rig.switch_times[40:43]  # three clicks never happen: 500 ms gap
    rig.run_until(3 * S + 60 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "missed_frame"


def test_camera_stall_is_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.camera.stop()  # no more pictures
    rig.run_until(3 * S + 40 * film.period_ns)
    st = rig.machine.status()
    # The camera health check (no picture for stall_ms) fires before the picker's per-click
    # stall, which needs stall_ms past the click's own window.
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "camera"
    assert "stopped sending pictures" in st.last_fault.message
    assert st.frames_failed >= 1
    rig.machine.shutdown()
    assert rig.machine.accounting.balanced() and rig.machine.accounting.pending == 0


def test_camera_mode_change_is_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    saved_before = rig.machine.status().frames_saved
    rig.camera.width, rig.camera.height = 96, 54
    rig.run_until(3 * S + 32 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "camera"
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    rig.machine.shutdown()
    frames = sorted(rig.machine.reel.frames_dir.glob("*.png"))
    assert saved_before >= 25 and len(frames) >= saved_before  # earlier frames kept
    assert frame_numbers(rig.machine.reel)[:saved_before] == list(range(1, saved_before + 1))


def test_operator_stop_then_resume_continues_numbering(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.machine.stop()
    assert rig.machine.status().state == MachineState.STOPPED
    saved_before = rig.machine.status().frames_saved
    clicks_before = rig.machine.status().clicks
    rig.run_for(2 * S)  # clicks keep coming while stopped: ignored
    rig.machine.resume()
    assert rig.machine.status().state == MachineState.READY
    rig.run_until(3 * S + 120 * film.period_ns)
    st = rig.machine.status()
    assert st.segment == 2 and st.frames_saved > saved_before
    events = Journal(rig.machine.reel.journal_path).read_all()
    assert [e["segment"] for e in events if e["type"] == "segment_start"] == [1, 2]
    first_frames = [e["first_frame"] for e in events if e["type"] == "segment_start"]
    assert first_frames[1] == clicks_before + 1


def test_stop_with_click_pending_fails_it_and_books_balance(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(film.switch_ns(30))  # click 30 has just arrived; its picture is not taken yet
    pending_at_stop = rig.machine.status().frames_pending
    assert pending_at_stop >= 1
    rig.machine.stop()
    st = rig.machine.status()
    assert st.frames_pending == 0 and st.frames_failed == pending_at_stop
    rig.machine.shutdown()
    assert rig.machine.accounting.balanced()
    events = Journal(rig.machine.reel.journal_path).read_all()
    clicked = {e["frame"] for e in events if e["type"] == "click"}
    resolved = {e["frame"] for e in events if e["type"] in ("saved", "failed")}
    assert clicked == resolved
    failed = [e for e in events if e["type"] == "failed"]
    assert all(e["reason"] == "segment stopped" for e in failed)
    stop_at = next(i for i, e in enumerate(events) if e["type"] == "segment_stop")
    assert all(events.index(e) < stop_at for e in failed)


def test_disk_space_keeps_machine_not_ready(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, min_free_bytes=10**15), film)
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.NOT_READY


def test_sync_error_over_limit_keeps_machine_not_ready(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, sync_error_limit_ms=0.0001), film)
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.NOT_READY


def test_new_reel_metadata_written(tmp_path):
    film = SimFilm(frames=30, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_for(2 * S)
    rig.machine.new_reel(
        ReelMeta(name="Smith wedding", customer="Smith", job_number="J-001", notes="box 2")
    )
    rig.run_until(3 * S + 5 * film.period_ns)
    meta = rig.machine.reel.read_reel_json()
    assert meta["name"] == "Smith wedding" and meta["job_number"] == "J-001"
    assert meta["camera"]["mode"].startswith("sim-rgb") and meta["delay_ms"] == 0.0
    assert rig.machine.reel.path == Path(tmp_path / "reels" / "Smith wedding")


def test_two_machines_do_not_interfere(tmp_path):
    f1 = SimFilm(frames=150, start_ns=3 * S)
    f2 = SimFilm(frames=150, start_ns=3 * S + 37_000_000)
    r1 = SimRig(cfg(tmp_path, name="WorkPrinter 1", delay_ms=40.0), f1)
    r2 = SimRig(
        cfg(tmp_path, name="WorkPrinter 2", delay_ms=40.0), f2, offset_us=123_456, drift_ppm=40
    )
    end = 3 * S + 170 * f1.period_ns
    while r1.clock.now_ns() < end:
        r1.run_for(10_000_000)
        r2.run_for(10_000_000)
        if r1.clock.now_ns() == 3 * S + 50 * f1.period_ns:
            r1.box.drop_next = True
    assert r1.machine.status().state == MachineState.STOPPED
    assert r2.machine.status().state == MachineState.REEL_FINISHED
    assert r2.machine.status().frames_failed == 0
    r1.machine.shutdown()
    r2.machine.shutdown()
    assert frame_numbers(ReelFolder.open(r2.machine.reel.path))[:150] == list(range(1, 151))


def test_thousand_frames_none_lost_or_doubled(tmp_path):
    film = SimFilm(frames=1000, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film, drift_ppm=25, offset_us=-777_000)
    rig.run_until(3 * S + 1040 * film.period_ns)
    rig.machine.shutdown()
    st = rig.machine.status()
    assert st.state == MachineState.REEL_FINISHED and st.frames_failed == 0
    assert frame_numbers(ReelFolder.open(rig.machine.reel.path))[:1000] == list(range(1, 1001))
    assert rig.machine.accounting.balanced()


def test_shutdown_with_frames_queued_does_not_deadlock(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 10 * film.period_ns)
    m = rig.machine
    assert m.state == MachineState.RECORDING
    # Step by hand without draining the saver, holding the machine lock: the saver thread
    # blocks in its on_saved callback, so later frames stay queued.
    with m._lock:
        end = rig.clock.now_ns() + 5 * film.period_ns
        while rig.clock.now_ns() < end:
            rig.clock.advance(1_000_000)
            now = rig.clock.now_ns()
            rig.camera.emit_until(now)
            while rig._next_switch < len(rig.switch_times) and (
                rig.switch_times[rig._next_switch] <= now
            ):
                rig.box.close_switch()
                rig._next_switch += 1
            rig.box.tick()
            m.tick()
        assert m._saver.pending > 0
    t0 = time.monotonic()
    m.shutdown()
    assert time.monotonic() - t0 < 2
    assert m.accounting.balanced() and m.accounting.pending == 0


def test_resume_after_pause_does_not_trip_interval_rule(tmp_path):
    film = SimFilm(frames=200, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(3 * S + 40 * film.period_ns)  # well over 20 intervals known
    rig.machine.stop()
    now = rig.clock.now_ns()
    # The operator winds back: no clicks for 2 s.
    rig.switch_times[:] = [t for t in rig.switch_times if not now < t <= now + 2 * S]
    rig.run_for(2 * S)
    saved_at_resume = rig.machine.status().frames_saved
    rig.machine.resume()
    rig.run_for(3 * S)
    st = rig.machine.status()
    assert st.state in (MachineState.RECORDING, MachineState.REEL_FINISHED)
    assert st.last_fault.kind == "operator"
    assert st.segment == 2 and st.frames_saved > saved_at_resume
    rig.machine.shutdown()
    assert rig.machine.accounting.balanced()


def camera_faults(m):
    return [f for f in m.fault_history if f.kind == "camera"]


def test_camera_mode_change_faults_once_and_blocks_ready(tmp_path):
    film = SimFilm(frames=200, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.camera.width, rig.camera.height = 96, 54
    rig.run_for(2 * S)  # 120 more wrong-size pictures while stopped
    assert len(camera_faults(rig.machine)) == 1
    assert sum(a[0] == "problem" for a in rig.alerts) == 1
    rig.machine.resume()
    rig.run_for(2 * S)  # the camera is still wrong: no segment may open
    st = rig.machine.status()
    assert st.state == MachineState.NOT_READY
    assert st.segment == 2 and len(camera_faults(rig.machine)) <= 2
    rig.camera.width, rig.camera.height = 192, 108  # put right again
    rig.run_for(S)
    assert rig.machine.status().state in (MachineState.READY, MachineState.RECORDING)
    rig.machine.shutdown()


def test_silent_sync_box_raises_one_fault_not_one_per_tick(tmp_path):
    rig = SimRig(cfg(tmp_path), SimFilm(frames=0, start_ns=10 * S))
    rig.box.tick = lambda: None  # the box never speaks
    rig.run_for(5 * S)  # silent for 2 s past the 3 s hello timeout: 2000 ticks
    assert [f.kind for f in rig.machine.fault_history] == ["sync_box"]
    assert sum("no message from sync box" in a[2] for a in rig.alerts) == 1
    assert rig.machine.status().state == MachineState.NOT_READY


def test_unplugged_sync_box_is_sync_box_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    rig.machine.link._t.close()  # the USB serial port vanished
    rig.run_for(2 * S)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "sync_box"
    assert [f.kind for f in rig.machine.fault_history] == ["sync_box"]
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    rig.machine.shutdown()
    assert rig.machine.accounting.balanced() and rig.machine.accounting.pending == 0


def test_film_moving_before_ready_warns_once(tmp_path):
    film = SimFilm(frames=200, start_ns=0)  # the operator starts the film at once
    rig = SimRig(cfg(tmp_path), film)
    rig.run_for(3 * S)
    warnings = [a for a in rig.alerts if a[0] == "warning" and "not ready" in a[2]]
    assert len(warnings) == 1 and "WorkPrinter 1" in warnings[0][2]
    assert rig.machine.link.clicks_before_sync >= 1


@pytest.mark.parametrize("close", ["shutdown", "new_reel"])
def test_click_pending_at_reel_finished_is_failed_when_reel_closes(tmp_path, close):
    film = SimFilm(frames=60, start_ns=3 * S)
    # A delay longer than the frame period: the next click is already waiting for its
    # picture when the frame that finishes the reel is picked.
    rig = SimRig(cfg(tmp_path, delay_ms=130.0), film)
    m = rig.machine
    while m.state != MachineState.REEL_FINISHED:
        assert rig.clock.now_ns() < 3 * S + 100 * film.period_ns, "reel never finished"
        rig.run_for(1_000_000)
    assert m._picker.pending_count >= 1
    reel, accounting = m.reel, m.accounting
    if close == "shutdown":
        m.shutdown()
    else:
        m.new_reel(ReelMeta())
    assert accounting.balanced() and accounting.pending == 0
    events = Journal(reel.journal_path).read_all()
    clicked = {e["frame"] for e in events if e["type"] == "click"}
    resolved = {e["frame"] for e in events if e["type"] in ("saved", "failed")}
    assert clicked == resolved
    assert any(e["type"] == "failed" and e["reason"] == "reel closed" for e in events)


def test_double_click_far_too_short_is_sync_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.switch_times.insert(40, film.switch_ns(40) + 60_000_000)  # 60 ms: beats the 20 ms filter
    rig.run_until(3 * S + 50 * film.period_ns)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "sync"
    assert "double click" in st.last_fault.message and st.bounces == 0


def test_camera_stopping_while_ready_demotes_to_not_ready(tmp_path):
    rig = SimRig(cfg(tmp_path), SimFilm(frames=0, start_ns=10 * S))
    rig.run_for(2 * S)
    assert rig.machine.status().state == MachineState.READY
    rig.camera.stop()
    rig.run_for(300_000_000)
    assert rig.machine.status().state == MachineState.NOT_READY


def test_reel_drive_unusable_at_first_click_is_storage_fault(tmp_path):
    (tmp_path / "reels").write_text("a file where the reel folder should be")
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 10 * film.period_ns)
    m = rig.machine
    st = m.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "storage"
    assert m.reel is None and st.clicks == 0
    assert [f.kind for f in m.fault_history] == ["storage"]
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    with pytest.raises(RuntimeError, match="no reel"):
        m.resume()
    m.shutdown()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_journal_write_failure_mid_reel_is_storage_fault(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    m = rig.machine
    reel = m.reel
    saved_before = m.status().frames_saved
    reel.journal_path.rename(reel.path / "journal.moved")
    reel.journal_path.mkdir()  # every append now raises IsADirectoryError
    rig.run_for(2 * S)  # must not raise
    st = m.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "storage"
    assert "journal" in st.last_fault.message
    assert [f.kind for f in m.fault_history] == ["storage"]
    assert sum(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts) == 1
    m.shutdown()  # must not raise either
    assert m.accounting.balanced() and m.accounting.pending == 0
    assert len(list(reel.frames_dir.glob("*.png"))) >= saved_before


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="needs POSIX directory permissions as a non-root user",
)
def test_frame_write_failure_is_storage_fault_and_earlier_frames_kept(tmp_path):
    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    m = rig.machine
    reel = m.reel
    before = {p.name: p.read_bytes() for p in reel.frames_dir.glob("*.png")}
    os.chmod(reel.frames_dir, stat.S_IRUSR | stat.S_IXUSR)  # the next frame write fails
    try:
        rig.run_for(S)
    finally:
        os.chmod(reel.frames_dir, stat.S_IRWXU)
    st = m.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "storage"
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    m.shutdown()
    events = Journal(reel.journal_path).read_all()
    assert any(e["type"] == "failed" and "write error" in e["reason"] for e in events)
    assert len(before) >= 25
    assert {p.name: p.read_bytes() for p in reel.frames_dir.glob("*.png")} == before
    assert not list(reel.frames_dir.glob("*.tmp"))
    assert m.accounting.balanced() and m.accounting.pending == 0


def test_directory_sync_failure_while_recording_is_storage_fault(tmp_path, monkeypatch):
    import wpcap.saver as saver_mod

    def failing_sync(directory):
        raise OSError("sync boom")

    film = SimFilm(frames=100, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 5 * film.period_ns)
    m = rig.machine
    monkeypatch.setattr(saver_mod, "_fsync_dir", failing_sync)
    rig.run_for(S)
    st = m.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "storage"
    assert "did not confirm" in st.last_fault.message
    assert any(a[0] == "problem" and "STOP WorkPrinter 1 NOW" in a[1] for a in rig.alerts)
    reel = m.reel
    m.shutdown()
    assert len(list(reel.frames_dir.glob("*.png"))) >= 1
    assert m.accounting.balanced() and m.accounting.pending == 0


def test_late_error_from_closed_reel_warns_and_leaves_new_reel_recording(tmp_path):
    film = SimFilm(frames=60, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    m = rig.machine
    while m.state != MachineState.REEL_FINISHED:
        assert rig.clock.now_ns() < 3 * S + 100 * film.period_ns, "reel never finished"
        rig.run_for(1_000_000)
    old = m._saver
    m.new_reel(ReelMeta(name="second"))
    while m.state != MachineState.RECORDING:
        assert rig.clock.now_ns() < 3 * S + 200 * film.period_ns, "second reel never started"
        rig.run_for(1_000_000)
    problems = sum(a[0] == "problem" for a in rig.alerts)
    old._on_error(5, OSError("late"))
    old._on_durability_error(6, OSError("late sync"))
    assert m.state == MachineState.RECORDING
    late = [a for a in rig.alerts if a[0] == "warning" and "previous reel" in a[2]]
    assert len(late) == 2
    assert sum(a[0] == "problem" for a in rig.alerts) == problems
    m.shutdown()
    assert m.accounting.balanced() and m.accounting.pending == 0


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_dead_saver_blocks_resume_until_a_new_reel(tmp_path):
    film = SimFilm(frames=200, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    assert rig.machine.status().state == MachineState.RECORDING
    saver = rig.machine._saver
    original = saver._journal.append

    def dying_append(event):
        if event["type"] == "saved":
            raise OSError(5, "Input/output error")
        original(event)

    saver._journal.append = dying_append  # the next saved frame ends the worker
    rig.run_for(2 * S)
    assert not saver.alive
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED
    assert st.last_fault.kind == "storage" and "saver stopped" in st.last_fault.message
    rig.machine.resume()
    assert rig.machine.status().state == MachineState.NOT_READY
    rig.run_for(2 * S)  # ticks must not promote to Ready, and must say why once
    assert rig.machine.status().state == MachineState.NOT_READY
    assert [f.message for f in rig.machine.fault_history].count("saver stopped unexpectedly") == 2
    assert "new reel" in rig.machine.fault_history[-1].action
    rig.machine.new_reel(ReelMeta(name="Reel 2"))
    rig.run_for(1 * S)
    assert rig.machine.status().state in (MachineState.READY, MachineState.RECORDING)


def test_vanished_reel_drive_is_a_storage_fault_not_a_crash(tmp_path):
    film = SimFilm(frames=200, start_ns=3 * S)
    present = {"drive": True}

    def free_bytes(path: Path) -> int:
        if not present["drive"]:
            raise PermissionError(13, "Permission denied", str(path))
        return 10**12

    rig = SimRig(cfg(tmp_path), film, free_bytes=free_bytes)
    rig.run_until(3 * S + 30 * film.period_ns)
    assert rig.machine.status().state == MachineState.RECORDING
    present["drive"] = False
    rig.run_for(1 * S)
    st = rig.machine.status()  # must not raise
    assert st.state == MachineState.STOPPED and st.free_bytes is None
    assert st.last_fault.kind == "storage" and "reel drive not found" in st.last_fault.message
    rig.machine.resume()
    assert rig.machine.status().state == MachineState.NOT_READY
    present["drive"] = True
    rig.run_for(1 * S)
    assert rig.machine.status().state in (MachineState.READY, MachineState.RECORDING)


def test_reel_folder_vanishing_under_a_live_mount_point_is_a_storage_fault(tmp_path):
    import shutil

    film = SimFilm(frames=200, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    rig.run_until(3 * S + 30 * film.period_ns)
    assert rig.machine.status().state == MachineState.RECORDING
    shutil.rmtree(rig.machine.reel.path)  # the drive unmounted; the mount point remains
    rig.run_for(1 * S)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.free_bytes is None
    assert st.last_fault.kind == "storage"
    rig.machine.resume()
    rig.run_for(1 * S)
    assert rig.machine.status().state == MachineState.NOT_READY
