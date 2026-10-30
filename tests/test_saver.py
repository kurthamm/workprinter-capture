import os
import stat

import numpy as np
import pytest
from PIL import Image

from wpcap.camera import Picture
from wpcap.clock import SystemClock
from wpcap.reel import Journal, ReelFolder
from wpcap.saver import Accounting, AccountingError, QueueFull, Saver


def pic(i: int, level: int = 100) -> Picture:
    return Picture(i, i * 1_000_000, np.full((16, 24, 3), level, dtype=np.uint8))


def make(tmp_path, queue_size=120):
    folder = ReelFolder.create(tmp_path, "Reel")
    journal = Journal(folder.journal_path)
    errors = []
    saved = []
    s = Saver(
        folder, journal, SystemClock(), queue_size,
        lambda n, e: errors.append((n, e)), saved.append,
    )
    return folder, journal, s, errors, saved


def test_saves_png_then_journals(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path)
    s.start()
    s.submit(1, pic(10, 77))
    s.join(5)
    s.stop()
    assert errors == [] and saved == [1]
    img = np.asarray(Image.open(folder.frame_path(1)))
    assert img.shape == (16, 24, 3) and img.min() == 77 and img.max() == 77
    assert not list(folder.frames_dir.glob("*.tmp"))
    ev = journal.read_all()
    assert ev[-1]["type"] == "saved" and ev[-1]["frame"] == 1 and ev[-1]["picture_index"] == 10
    assert s.saved == 1 and s.pending == 0


def test_queue_full_raises_immediately(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path, queue_size=2)
    # not started: nothing drains
    s.submit(1, pic(1))
    s.submit(2, pic(2))
    with pytest.raises(QueueFull):
        s.submit(3, pic(3))


def test_never_overwrites_existing_frame(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path)
    folder.frame_path(1).write_bytes(b"existing")
    s.start()
    with pytest.raises(FileExistsError):
        s.submit(1, pic(1))
    s.stop()
    assert folder.frame_path(1).read_bytes() == b"existing"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_write_error_is_fault_not_half_frame(tmp_path):
    folder, journal, s, errors, saved = make(tmp_path)
    s.start()
    s.submit(1, pic(1))
    s.join(5)
    os.chmod(folder.frames_dir, stat.S_IRUSR | stat.S_IXUSR)  # read-only: next write fails
    try:
        s.submit(2, pic(2))
        s.join(5)
    finally:
        os.chmod(folder.frames_dir, stat.S_IRWXU)
    s.stop()
    assert len(errors) == 1 and errors[0][0] == 2
    assert not folder.frame_path(2).exists()
    assert not list(folder.frames_dir.glob("*.tmp"))
    ev = journal.read_all()
    assert ev[-1]["type"] == "failed" and ev[-1]["frame"] == 2 and "write error" in ev[-1]["reason"]
    assert s.errors == 1 and s.saved == 1


def test_accounting_balances():
    a = Accounting()
    a.click()
    a.click()
    a.click()
    assert a.pending == 3 and a.balanced()
    a.saved_one()
    a.failed_one()
    assert (a.saved, a.failed, a.pending) == (1, 1, 1) and a.balanced()
    a.saved = 5
    assert not a.balanced()
    with pytest.raises(AccountingError):
        a.assert_balanced()
