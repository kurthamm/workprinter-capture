import pytest
from PIL import Image

from wpcap.recovery import recover, repair
from wpcap.reel import Journal, JournalCorrupt, ReelFolder

PNG_END = b"IEND\xaeB`\x82"


def write_png(path):
    Image.new("RGB", (2, 2)).save(path)


def reel_with(
    tmp_path, frames=(1, 2, 3), saved=(1, 2, 3), tmp=(), open_segment=True, truncate=False
):
    r = ReelFolder.create(tmp_path, "Reel")
    j = Journal(r.journal_path)
    j.append({"type": "segment_start", "t_ns": 1, "segment": 1, "first_frame": 1})
    for n in frames:
        write_png(r.frame_path(n))
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


def test_repair_trims_a_line_cut_mid_character(tmp_path):
    r, j = reel_with(tmp_path, open_segment=False)
    full = '{"type": "warning", "t_ns": 7, "text": "— check camcorder"}'.encode()
    with r.journal_path.open("ab") as f:
        f.write(full[: full.index("—".encode()) + 1])  # first byte of a 3-byte character
    rep = recover(r)
    assert rep.journal_truncated
    repair(r, rep)
    events = j.read_all()
    assert events[-1]["type"] == "recovered"
    assert [e["type"] for e in events[:-1]] == ["segment_start"] + ["saved"] * 3 + ["segment_stop"]


def test_complete_last_line_without_newline_is_flagged_and_kept(tmp_path):
    r, j = reel_with(tmp_path)
    data = r.journal_path.read_bytes()
    r.journal_path.write_bytes(data.rstrip(b"\n"))  # last saved line is whole but unterminated
    rep = recover(r)
    assert rep.missing_final_newline and not rep.journal_truncated
    repair(r, rep)
    events = j.read_all()
    assert [e["frame"] for e in events if e["type"] == "saved"] == [1, 2, 3]
    assert [e["type"] for e in events[-2:]] == ["segment_stop", "recovered"]


def test_clicks_queued_at_crash_are_reported_and_closed(tmp_path):
    r, j = reel_with(tmp_path, frames=(1, 2), saved=(1, 2), tmp=(3,))
    for n in (1, 2, 3, 4, 5):
        j.append({"type": "click", "t_ns": 20 + n, "frame": n, "seq": n, "segment": 1})
    j.append({"type": "failed", "t_ns": 40, "frame": 5, "reason": "no picture within window"})
    rep = recover(r)
    assert rep.orphan_clicks == (3, 4)
    assert not rep.missing_final_newline
    repair(r, rep)
    events = j.read_all()
    tail = [(e["type"], e.get("frame"), e.get("reason")) for e in events[-4:]]
    assert tail == [
        ("failed", 3, "half-written at recovery"),
        ("failed", 4, "lost at crash"),
        ("segment_stop", None, "crash"),
        ("recovered", None, None),
    ]
    assert recover(r).orphan_clicks == ()


def test_zero_byte_and_cut_frames_are_corrupt_not_complete(tmp_path):
    r, j = reel_with(tmp_path, frames=(1, 2), saved=(1, 2, 3))
    r.frame_path(3).write_bytes(b"")
    r.frame_path(4).write_bytes(b"\x89PNG cut short")
    rep = recover(r)
    assert rep.corrupt_frames == (3, 4)
    assert 3 not in rep.complete_frames and 4 not in rep.complete_frames
    assert rep.last_frame == 2 and rep.journaled_but_missing == ()
    assert r.frame_path(3).exists()  # recover never deletes
    repair(r, rep)
    events = j.read_all()
    failed = [(e["frame"], e["reason"]) for e in events if e["type"] == "failed"]
    assert failed == [(3, "corrupt after crash"), (4, "corrupt after crash")]
    assert r.frame_path(3).exists() and r.frame_path(4).exists()


def test_iend_only_and_damaged_pngs_are_corrupt(tmp_path):
    r, _ = reel_with(tmp_path, frames=(1, 2), saved=(1, 2))
    r.frame_path(3).write_bytes(PNG_END)
    write_png(r.frame_path(4))
    data = bytearray(r.frame_path(4).read_bytes())
    data[len(data) // 2 : len(data) // 2 + 4] = b"\xff\xff\xff\xff"
    r.frame_path(4).write_bytes(bytes(data))
    rep = recover(r)
    assert rep.corrupt_frames == (3, 4) and rep.complete_frames == (1, 2)


def test_jpeg_under_png_name_and_png_cut_at_the_end_are_corrupt(tmp_path):
    r, _ = reel_with(tmp_path, frames=(1, 2), saved=(1, 2))
    Image.new("RGB", (2, 2)).save(r.frame_path(4), format="JPEG")
    write_png(r.frame_path(5))
    data = r.frame_path(5).read_bytes()
    r.frame_path(5).write_bytes(data[:-4])  # the final CRC is gone; verify() does not notice
    rep = recover(r)
    assert rep.corrupt_frames == (4, 5) and rep.complete_frames == (1, 2)
