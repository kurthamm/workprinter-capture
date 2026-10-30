import json

import pytest

from wpcap.reel import Journal, JournalCorrupt, ReelFolder


def test_create_makes_layout(tmp_path):
    r = ReelFolder.create(tmp_path, "WorkPrinter 1 — 2026-10-30 1800")
    assert r.path == tmp_path / "WorkPrinter 1 — 2026-10-30 1800"
    for sub in ("frames", "neighbours", "exports"):
        assert (r.path / sub).is_dir()
    assert r.frame_path(1) == r.path / "frames" / "000001.png"
    assert r.frame_path(123456) == r.path / "frames" / "123456.png"


def test_reel_folder_name_collision_gets_suffix(tmp_path):
    a = ReelFolder.create(tmp_path, "Reel")
    b = ReelFolder.create(tmp_path, "Reel")
    c = ReelFolder.create(tmp_path, "Reel")
    assert (a.name, b.name, c.name) == ("Reel", "Reel (2)", "Reel (3)")
    assert a.path.exists() and b.path.exists() and c.path.exists()


def test_bad_names_rejected(tmp_path):
    with pytest.raises(ValueError):
        ReelFolder.create(tmp_path, "a/b")
    with pytest.raises(ValueError):
        ReelFolder.create(tmp_path, "")


def test_open_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ReelFolder.open(tmp_path / "nope")


def test_reel_json_round_trip(tmp_path):
    r = ReelFolder.create(tmp_path, "Reel")
    r.write_reel_json({"name": "Reel", "machine": "WorkPrinter 1"})
    assert r.read_reel_json() == {"name": "Reel", "machine": "WorkPrinter 1"}


def test_journal_append_and_read(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    j.append({"type": "click", "t_ns": 1, "seq": 5})
    j.append({"type": "saved", "t_ns": 2, "frame": 1})
    assert j.read_all() == [
        {"type": "click", "t_ns": 1, "seq": 5},
        {"type": "saved", "t_ns": 2, "frame": 1},
    ]


def test_journal_requires_type_and_time(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    with pytest.raises(ValueError):
        j.append({"type": "click"})
    with pytest.raises(ValueError):
        j.append({"t_ns": 1})


def test_journal_corrupt_middle_line_raises(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text(
        json.dumps({"type": "a", "t_ns": 1})
        + "\n{not json\n"
        + json.dumps({"type": "b", "t_ns": 2})
        + "\n"
    )
    with pytest.raises(JournalCorrupt) as e:
        Journal(p).read_all()
    assert e.value.line_number == 2


def test_journal_truncated_last_line_is_tolerated_only_by_tolerant_reader(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text(json.dumps({"type": "a", "t_ns": 1}) + "\n" + '{"type": "b", "t_ns": 2')
    with pytest.raises(JournalCorrupt):
        Journal(p).read_all()
    events, truncated = Journal(p).read_all_tolerant()
    assert events == [{"type": "a", "t_ns": 1}] and truncated


def test_journal_last_line_cut_mid_character_is_truncated_not_a_crash(tmp_path):
    p = tmp_path / "journal.jsonl"
    full = json.dumps({"type": "b", "t_ns": 2, "note": "—"}, ensure_ascii=False).encode("utf-8")
    cut = full[: full.index("—".encode()) + 1]  # first byte of the 3-byte character
    p.write_bytes(json.dumps({"type": "a", "t_ns": 1}).encode() + b"\n" + cut)
    with pytest.raises(JournalCorrupt):
        Journal(p).read_all()
    events, truncated = Journal(p).read_all_tolerant()
    assert events == [{"type": "a", "t_ns": 1}] and truncated


def test_journal_appends_from_two_threads_stay_whole_lines(tmp_path, monkeypatch):
    # On Windows (and network drives) an append is seek-to-end + write, not one atomic
    # write. Model that: every write goes out in small pieces with a thread switch between.
    import pathlib
    import threading
    import time

    real_open = pathlib.Path.open

    class Chunky:
        def __init__(self, f):
            self._f = f

        def write(self, s):
            for i in range(0, len(s), 7):
                self._f.write(s[i : i + 7])
                self._f.flush()
                time.sleep(0)
            return len(s)

        def flush(self):
            self._f.flush()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._f.close()

    def chunky_open(self, *args, **kwargs):
        return Chunky(real_open(self, *args, **kwargs))

    monkeypatch.setattr(pathlib.Path, "open", chunky_open)
    j = Journal(tmp_path / "journal.jsonl")

    def writer(name):
        for i in range(200):
            j.append({"type": name, "t_ns": i, "pad": "x" * 40})

    threads = [threading.Thread(target=writer, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    monkeypatch.undo()
    events = j.read_all()
    assert len(events) == 400
    assert sorted(e["t_ns"] for e in events if e["type"] == "a") == list(range(200))
    assert sorted(e["t_ns"] for e in events if e["type"] == "b") == list(range(200))
