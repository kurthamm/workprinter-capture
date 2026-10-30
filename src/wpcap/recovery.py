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


def _trim_truncated_line(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: text.rfind("\n") + 1], encoding="utf-8")


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
    )


def repair(folder: ReelFolder, report: RecoveryReport) -> None:
    if report.journal_truncated:
        _trim_truncated_line(folder.journal_path)
    journal = Journal(folder.journal_path)
    now = time.perf_counter_ns()
    for p in report.half_written:
        m = _TMP_RE.match(p.name)
        if m is None:
            raise ValueError(f"not a half-written frame file: {p}")
        n = int(m.group(1))
        journal.append(
            {"type": "failed", "t_ns": now, "frame": n, "reason": "half-written at recovery"}
        )
        p.unlink()
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
            "last_frame": report.last_frame,
        }
    )


__all__ = ["JournalCorrupt", "RecoveryReport", "recover", "repair"]
