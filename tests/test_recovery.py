import pytest

from wpcap.recovery import recover, repair
from wpcap.reel import Journal, JournalCorrupt, ReelFolder


def reel_with(
    tmp_path, frames=(1, 2, 3), saved=(1, 2, 3), tmp=(), open_segment=True, truncate=False
):
    r = ReelFolder.create(tmp_path, "Reel")
    j = Journal(r.journal_path)
    j.append({"type": "segment_start", "t_ns": 1, "segment": 1, "first_frame": 1})
    for n in frames:
        r.frame_path(n).write_bytes(b"png")
    for n in saved:
        j.append({"type": "saved", "t_ns": 10 + n, "frame": n, "picture_index": n, "t_pic_ns": n})
    for n in tmp:
        (r.frames_dir / f"{n:06d}.png.tmp").write_bytes(b"partial")
    if not open_segment:
        j.append({"type": "segment_stop", "t_ns": 99, "segment": 1, "reason": "reel finished"})
    if truncate:
        with r.journal_path.open("a") as f:
            f.write('{"type": "saved", "t_ns": 5')
    return r, j


def test_clean_reel(tmp_path):
    r, _ = reel_with(tmp_path, open_segment=False)
    rep = recover(r)
    assert rep.complete_frames == (1, 2, 3) and rep.half_written == () and rep.open_segment is None
    assert rep.last_frame == 3 and not rep.journal_truncated


def test_crash_mid_write(tmp_path):
    r, _ = reel_with(tmp_path, frames=(1, 2), saved=(1, 2), tmp=(3,), truncate=True)
    rep = recover(r)
    assert rep.complete_frames == (1, 2)
    assert [p.name for p in rep.half_written] == ["000003.png.tmp"]
    assert rep.open_segment == 1 and rep.journal_truncated and rep.last_frame == 2
    assert (r.frames_dir / "000003.png.tmp").exists()  # recover never deletes


def test_frame_on_disk_but_not_journaled_and_vice_versa(tmp_path):
    r, _ = reel_with(tmp_path, frames=(1, 2, 3), saved=(1, 2, 4))
    rep = recover(r)
    assert rep.on_disk_not_journaled == (3,) and rep.journaled_but_missing == (4,)


def test_corrupt_middle_line_raises(tmp_path):
    r, _ = reel_with(tmp_path)
    lines = r.journal_path.read_text().split("\n")
    lines.insert(1, "{broken")
    r.journal_path.write_text("\n".join(lines))
    with pytest.raises(JournalCorrupt):
        recover(r)


def test_repair_closes_segment_and_removes_tmp(tmp_path):
    r, j = reel_with(tmp_path, frames=(1, 2), saved=(1, 2), tmp=(3,), truncate=True)
    rep = recover(r)
    repair(r, rep)
    assert not (r.frames_dir / "000003.png.tmp").exists()
    events = j.read_all()  # no longer truncated
    assert [e["type"] for e in events[-3:]] == ["failed", "segment_stop", "recovered"]
    assert events[-2]["reason"] == "crash"
    assert events[-3]["frame"] == 3
    assert recover(r).open_segment is None
