import numpy as np

from wpcap.gate import ExposureWatcher, GateDetector, is_empty_gate


def flat(level):
    return np.full((54, 96, 3), level, dtype=np.uint8)


def textured(level=110):
    img = np.full((54, 96, 3), level, dtype=np.uint8)
    img[:, ::3, :] = level + 60
    return img


def test_is_empty_gate():
    assert is_empty_gate(flat(235), 200, 8.0)
    assert not is_empty_gate(flat(120), 200, 8.0)
    assert not is_empty_gate(textured(190), 200, 8.0)


def test_leader_at_start_does_not_finish():
    g = GateDetector(empty_needed=5, min_frames_before=10)
    for k in range(1, 40):
        assert g.observe(k, flat(235)) is False
    assert not g.finished and g.picture_frames_seen == 0


def test_empty_gate_after_pictures_finishes_once():
    g = GateDetector(empty_needed=5, min_frames_before=10)
    k = 0
    for _ in range(10):
        k += 1
        assert g.observe(k, textured()) is False
    results = []
    for _ in range(7):
        k += 1
        results.append(g.observe(k, flat(235)))
    assert results == [False, False, False, False, True, False, False]
    assert g.finished


def test_non_empty_frame_resets_run():
    g = GateDetector(empty_needed=3, min_frames_before=2)
    g.observe(1, textured())
    g.observe(2, textured())
    g.observe(3, flat(235))
    g.observe(4, flat(235))
    assert g.empty_run == 2
    g.observe(5, textured())
    assert g.empty_run == 0
    assert g.observe(6, flat(235)) is False


def test_exposure_watcher_flags_jump_only():
    w = ExposureWatcher(window=5, jump=25.0)
    for _ in range(5):
        assert w.observe(flat(100)) is None
    assert w.observe(flat(110)) is None
    j = w.observe(flat(160))
    assert j is not None and j > 25
