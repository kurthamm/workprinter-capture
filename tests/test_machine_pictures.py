import pytest

from wpcap.machine import MachineConfig, MachineState, ReelMeta
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


def test_live_picture_is_the_newest_camera_picture(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path), film)
    assert rig.machine.live_picture() is None
    rig.run_until(2 * S)
    live = rig.machine.live_picture()
    assert live is not None
    rig.run_for(S // 2)
    assert rig.machine.live_picture().t_ns > live.t_ns


def test_last_saved_matches_the_frame_count(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    assert rig.machine.last_saved() is None
    # click 21, its 40 ms delay, then 70 ms more so 3+ pictures follow the target
    rig.run_until(film.switch_ns(21) + 40_000_000 + 70_000_000)
    n, pic = rig.machine.last_saved()
    assert n == rig.machine.status().frames_saved + rig.machine.status().frames_pending
    assert decode_number(pic.pixels) == n


def test_last_saved_only_shows_frames_on_disk(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(film.switch_ns(20) + 40_000_000 + 70_000_000)
    assert rig.machine.last_saved()[0] == 20  # written: shown
    reel = rig.machine.reel
    real_frame_path = reel.frame_path
    # frame 21's write fails: the drive is gone under it
    reel.frame_path = lambda n: (
        tmp_path / "gone" / "f.png" if n == 21 else real_frame_path(n)
    )
    rig.run_until(film.switch_ns(21) + 40_000_000 + 70_000_000)
    st = rig.machine.status()
    assert st.state == MachineState.STOPPED and st.last_fault.kind == "storage"
    n, pic = rig.machine.last_saved()
    assert n == 20 and decode_number(pic.pixels) == 20  # never the failed frame


def test_click_window_brackets_the_last_click(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    assert rig.machine.click_window() == []
    # click 21, its 40 ms delay, then 70 ms more so 3+ pictures follow the target
    rig.run_until(film.switch_ns(21) + 40_000_000 + 70_000_000)
    window = rig.machine.click_window()
    offsets = [ms for ms, _ in window]
    assert len(window) == 7
    assert offsets == sorted(offsets)
    assert offsets[3] == min(offsets, key=abs)  # the middle one is the picked time
    assert abs(offsets[3]) <= 9  # within one 60 fps camera interval (16.7 ms) of the target


def test_click_window_survives_stop_and_the_camera_streaming_on(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(film.switch_ns(21) + 40_000_000 + 70_000_000)
    rig.machine.stop()
    n, _ = rig.machine.last_saved()
    # the ring buffer holds about one second; the operator calibrates later than that
    rig.run_for(2 * S)
    window = rig.machine.click_window()
    offsets = [ms for ms, _ in window]
    assert len(window) == 7
    assert all(abs(ms) <= 60 for ms in offsets), offsets
    assert offsets[3] == min(offsets, key=abs)
    assert decode_number(window[3][1].pixels) == n  # the picture of the last click's frame


def test_click_window_is_empty_on_a_new_reel(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(film.switch_ns(21) + 40_000_000 + 70_000_000)
    rig.machine.stop()
    assert len(rig.machine.click_window()) == 7
    rig.machine.new_reel(ReelMeta())
    assert rig.machine.click_window() == []


def test_set_delay_takes_effect_next_click_and_is_recorded(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(2 * S)
    rig.machine.set_delay_ms(55.0)
    assert rig.machine.config.delay_ms == 55.0
    rig.run_until(3 * S + 5 * film.period_ns)
    assert rig.machine.reel.read_reel_json()["delay_ms"] == 55.0
    with pytest.raises(RuntimeError, match="recording"):
        rig.machine.set_delay_ms(60.0)
    assert rig.machine.status().state == MachineState.RECORDING


def test_set_delay_moves_the_picture_picked_by_the_next_click(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(2 * S)
    rig.machine.set_delay_ms(120.0)
    rig.run_until(film.switch_ns(5) + 120_000_000 + 70_000_000)
    n, pic = rig.machine.last_saved()
    # the picked picture is ~120 ms (not the old 40 ms) after its click, within one 60 fps interval
    assert abs(pic.t_ns - (film.switch_ns(n) + 120_000_000)) <= 9_000_000


def test_set_delay_leaves_the_delay_alone_when_the_reel_record_cannot_be_written(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    rig.run_until(film.switch_ns(5) + 100_000_000)
    rig.machine.stop()  # the delay can change only when stopped; the reel stays open
    reel = rig.machine.reel
    assert reel is not None

    def broken(data):
        raise OSError("disk gone")

    reel.write_reel_json = broken
    with pytest.raises(OSError):
        rig.machine.set_delay_ms(55.0)
    assert rig.machine.config.delay_ms == 40.0
    assert reel.read_reel_json()["delay_ms"] == 40.0


def test_set_delay_rejects_nonsense(tmp_path):
    rig = SimRig(cfg(tmp_path), SimFilm(frames=10, start_ns=3 * S))
    for bad in (-1.0, 1000.0, float("nan")):
        with pytest.raises(ValueError):
            rig.machine.set_delay_ms(bad)


def test_set_delay_refused_when_shut_down(tmp_path):
    rig = SimRig(cfg(tmp_path), SimFilm(frames=10, start_ns=3 * S))
    rig.machine.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        rig.machine.set_delay_ms(50.0)
