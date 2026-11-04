import numpy as np
import pytest

from wpcap.camera import Picture
from wpcap.clock import SimClock
from wpcap.sim.camera import SimCamera, decode_number, encode_number, is_blurred
from wpcap.sim.film import SimFilm


def test_picture_validates_shape_and_dtype():
    with pytest.raises(ValueError):
        Picture(1, 0, np.zeros((10, 10), dtype=np.uint8))
    with pytest.raises(ValueError):
        Picture(1, 0, np.zeros((10, 10, 3), dtype=np.float32))


def test_number_strip_round_trips():
    img = np.full((108, 192, 3), 110, dtype=np.uint8)
    encode_number(img, 123_456)
    assert decode_number(img) == 123_456


def test_film_timeline():
    f = SimFilm(frames=3, fps=8.0, pulldown_ms=30.0)
    period = 125_000_000
    assert f.frame_landed_ns(1) == 0
    assert f.frame_landed_ns(2) == period
    assert f.state_at(10_000_000) == (1, False)
    assert f.state_at(period - 10_000_000) == (1, True)  # last 30 ms before frame 2 lands
    assert f.state_at(2 * period + 10_000_000) == (3, False)
    assert f.state_at(3 * period + 1) == (None, False)  # film ran out: empty gate
    assert len(f.switch_times()) == 3 + 50


def test_switch_offset_moves_clicks():
    f = SimFilm(frames=2, switch_offset_ms=-20.0)
    assert f.switch_ns(2) == f.frame_landed_ns(2) - 20_000_000


def test_camera_renders_still_blurred_and_empty():
    clock = SimClock()
    film = SimFilm(frames=2, leader_frames=0)
    cam = SimCamera(clock, film)
    still = cam.render(10_000_000)
    assert decode_number(still.pixels) == 1 and not is_blurred(still.pixels)
    moving = cam.render(125_000_000 - 5_000_000)
    assert decode_number(moving.pixels) is None and is_blurred(moving.pixels)
    empty = cam.render(10 * 125_000_000)
    assert empty.pixels.min() == 235 and empty.pixels.max() == 235


def test_leader_frames_look_empty_but_count():
    cam = SimCamera(SimClock(), SimFilm(frames=5, leader_frames=2))
    assert cam.render(10_000_000).pixels.min() == 235
    assert decode_number(cam.render(2 * 125_000_000 + 10_000_000).pixels) == 3


def test_emit_until_delivers_60_per_second_with_timestamps():
    clock = SimClock()
    cam = SimCamera(clock, SimFilm(frames=100), fps=60.0)
    got = []
    cam.start(got.append)
    cam.emit_until(999_000_000)
    assert len(got) == 60
    assert got[0].t_ns == 0 and got[1].t_ns - got[0].t_ns == pytest.approx(16_666_667, abs=1)
    assert [p.index for p in got] == list(range(60))
