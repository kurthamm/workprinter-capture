"""After a crash or power cut: compare the journal with the frames on disk (spec 7.2)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from wpcap.reel import Journal, JournalCorrupt, ReelFolder

_FRAME_RE = re.compile(r"^(\d{6})\.png$")
_TMP_RE = re.compile(r"^(\d{6})\.png\.tmp$")


@dataclass(frozen=True)
class RecoveryReport:
    reel: Path
    complete_frames: tuple[int, ...]
    half_written: tuple[Path, ...]
    journaled_but_missing: tuple[int, ...]
    on_disk_not_journaled: tuple[int, ...]
    journal_truncated: bool
    last_frame: int
    open_segment: int | None
    orphan_clicks: tuple[int, ...]  # clicked, never saved or failed, no complete frame on disk
    missing_final_newline: bool  # the last line is whole but unterminated


def _trim_to_last_newline(path: Path) -> None:
    """Cut the unfinished last line in place, as bytes (it may end mid-character)."""
    with path.open("r+b") as f:
        data = f.read()
        f.truncate(data.rfind(b"\n") + 1)


def _terminate_last_line(path: Path) -> None:
    with path.open("ab") as f:
        f.write(b"\n")


def recover(folder: ReelFolder) -> RecoveryReport:
    complete: list[int] = []
    half: list[Path] = []
    for p in sorted(folder.frames_dir.iterdir()):
        if m := _FRAME_RE.match(p.name):
            complete.append(int(m.group(1)))
        elif _TMP_RE.match(p.name):
            half.append(p)
    journal = Journal(folder.journal_path)
    events, truncated = journal.read_all_tolerant()
    # read_all_tolerant forgives only a truncated last line; any other bad line raises.
    journaled = sorted({e["frame"] for e in events if e["type"] == "saved"})
    resolved = {e["frame"] for e in events if e["type"] in ("saved", "failed")}
    clicked = {e["frame"] for e in events if e["type"] == "click"}
    missing_newline = (
        not truncated
        and folder.journal_path.exists()
        and folder.journal_path.stat().st_size > 0
        and not folder.journal_path.read_bytes().endswith(b"\n")
    )
    open_segment: int | None = None
    for e in events:
        if e["type"] == "segment_start":
            open_segment = e["segment"]
        elif e["type"] == "segment_stop" and e.get("segment") == open_segment:
            open_segment = None
    complete_set, journaled_set = set(complete), set(journaled)
    return RecoveryReport(
        reel=folder.path,
        complete_frames=tuple(complete),
        half_written=tuple(half),
        journaled_but_missing=tuple(sorted(journaled_set - complete_set)),
        on_disk_not_journaled=tuple(sorted(complete_set - journaled_set)),
        journal_truncated=truncated,
        last_frame=max(complete) if complete else 0,
        open_segment=open_segment,
        orphan_clicks=tuple(sorted(clicked - resolved - complete_set)),
        missing_final_newline=missing_newline,
    )


def repair(folder: ReelFolder, report: RecoveryReport) -> None:
    if report.journal_truncated:
        _trim_to_last_newline(folder.journal_path)
    elif report.missing_final_newline:
        _terminate_last_line(folder.journal_path)
    journal = Journal(folder.journal_path)
    now = time.perf_counter_ns()
    half_frames: set[int] = set()
    for p in report.half_written:
        m = _TMP_RE.match(p.name)
        if m is None:
            raise ValueError(f"not a half-written frame file: {p}")
        n = int(m.group(1))
        half_frames.add(n)
        journal.append(
            {"type": "failed", "t_ns": now, "frame": n, "reason": "half-written at recovery"}
        )
        p.unlink()
    for n in report.orphan_clicks:
        if n not in half_frames:
            journal.append({"type": "failed", "t_ns": now, "frame": n, "reason": "lost at crash"})
    if report.open_segment is not None:
        journal.append(
            {"type": "segment_stop", "t_ns": now, "segment": report.open_segment, "reason": "crash"}
        )
    journal.append(
        {
            "type": "recovered",
            "t_ns": now,
            "complete": len(report.complete_frames),
            "half_written": len(report.half_written),
            "journaled_but_missing": list(report.journaled_but_missing),
            "on_disk_not_journaled": list(report.on_disk_not_journaled),
            "lost_at_crash": [n for n in report.orphan_clicks if n not in half_frames],
            "last_frame": report.last_frame,
        }
    )


__all__ = ["JournalCorrupt", "RecoveryReport", "recover", "repair"]
