import pytest

from wpcap.machine import MachineConfig, MachineState
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


def test_click_window_brackets_the_last_click(tmp_path):
    film = SimFilm(frames=50, start_ns=3 * S)
    rig = SimRig(cfg(tmp_path, delay_ms=40.0), film)
    assert rig.machine.click_window() == []
    # click 21, its 40 ms delay, then 70 ms more so 3+ pictures follow the target
    rig.run_until(film.switch_ns(21) + 40_000_000 + 70_000_000)
    window = rig.machine.click_window(before=3, after=3)
    offsets = [ms for ms, _ in window]
    assert len(window) == 7
    assert offsets == sorted(offsets)
    assert offsets[3] == min(offsets, key=abs)  # the middle one is the picked time
    assert abs(offsets[3]) <= 9  # within one 60 fps camera interval (16.7 ms) of the target


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
