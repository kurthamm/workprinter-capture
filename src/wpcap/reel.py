"""Reel folder layout (spec 7.2) and the append-only journal."""

from __future__ import annotations

import json
import threading
from pathlib import Path

_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class JournalCorrupt(Exception):
    def __init__(self, path: Path, line_number: int) -> None:
        super().__init__(f"journal {path} line {line_number} is not valid JSON")
        self.line_number = line_number


class ReelFolder:
    SUBDIRS = ("frames", "neighbours", "exports")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name
        self.frames_dir = path / "frames"
        self.journal_path = path / "journal.jsonl"
        self.reel_json_path = path / "reel.json"

    @staticmethod
    def check_name(name: str) -> None:
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"bad reel name: {name!r}")
        if bad := sorted(set(name) & set('<>:"|?*')):
            raise ValueError(f"reel name {name!r} has characters Windows rejects: {''.join(bad)}")
        if any(ord(c) < 32 for c in name):
            raise ValueError(f"reel name {name!r} has a control character")
        if name.endswith((" ", ".")):
            raise ValueError(f"reel name {name!r} ends in a space or a dot, which Windows drops")
        if name.split(".")[0].upper() in _RESERVED_NAMES:
            raise ValueError(f"reel name {name!r} is a reserved Windows device name")

    @classmethod
    def create(cls, root: Path, name: str) -> ReelFolder:
        cls.check_name(name)
        root.mkdir(parents=True, exist_ok=True)
        candidate = root / name
        n = 2
        while candidate.exists():
            candidate = root / f"{name} ({n})"
            n += 1
        candidate.mkdir()
        for sub in cls.SUBDIRS:
            (candidate / sub).mkdir()
        return cls(candidate)

    @classmethod
    def open(cls, path: Path) -> ReelFolder:
        if not (path / "frames").is_dir():
            raise FileNotFoundError(f"not a reel folder: {path}")
        return cls(path)

    def frame_path(self, n: int) -> Path:
        if n < 1:
            raise ValueError("frames are numbered from 1")
        return self.frames_dir / f"{n:06d}.png"

    def write_reel_json(self, data: dict) -> None:
        tmp = self.reel_json_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.reel_json_path)

    def read_reel_json(self) -> dict:
        return json.loads(self.reel_json_path.read_text(encoding="utf-8"))


class Journal:
    """Append-only event log. The machine thread and the saver thread both append, so every
    append holds one lock: an append is not one atomic write on every OS (Windows, network
    drives), and interleaved pieces would corrupt both lines."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(self, event: dict) -> None:
        if "type" not in event or "t_ns" not in event:
            raise ValueError(f"journal event needs 'type' and 't_ns': {event}")
        line = json.dumps(event, ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    def read_all(self) -> list[dict]:
        events, truncated = self._read()
        if truncated:
            raise JournalCorrupt(self.path, len(events) + 1)
        return events

    def read_all_tolerant(self) -> tuple[list[dict], bool]:
        return self._read()

    def _read(self) -> tuple[list[dict], bool]:
        if not self.path.exists():
            return [], False
        data = self.path.read_bytes()
        ends_with_newline = data.endswith(b"\n")
        lines = data.split(b"\n")
        if ends_with_newline:
            lines = lines[:-1]
        events: list[dict] = []
        for i, line in enumerate(lines, start=1):
            is_last = i == len(lines)
            try:
                events.append(json.loads(line.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                if is_last and not ends_with_newline:
                    return events, True
                raise JournalCorrupt(self.path, i) from e
        return events, False
