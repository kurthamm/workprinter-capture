"""Command line: `python -m wpcap demo` runs a simulated reel end to end."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from wpcap.machine import MachineConfig, MachineState
from wpcap.reel import ReelFolder
from wpcap.sim.camera import is_blurred
from wpcap.sim.film import SimFilm
from wpcap.sim.rig import SimRig

S = 1_000_000_000


def demo(args: argparse.Namespace) -> int:
    config = MachineConfig(
        name="Demo WorkPrinter",
        reel_root=Path(args.reels),
        delay_ms=args.delay_ms,
        gate_min_frames=20,
        gate_empty_needed=8,
    )
    film = SimFilm(frames=args.frames, start_ns=3 * S, switch_offset_ms=args.switch_offset_ms)
    rig = SimRig(config, film)
    total_s = 3 + args.frames / 8.0 + 3
    seconds_run = 0
    while seconds_run < total_s:
        if args.realtime:
            rig.run_realtime(1.0)
        else:
            rig.run_for(S)
        seconds_run += 1
        _print_status(rig)
    rig.machine.shutdown()
    st = rig.machine.status()
    reel = rig.machine.reel
    blurred = 0
    if reel is not None:
        for p in sorted(ReelFolder.open(reel.path).frames_dir.glob("*.png")):
            if is_blurred(np.asarray(Image.open(p))):
                blurred += 1
    print(f"final: {st.state} saved {st.frames_saved} failed {st.frames_failed} blurred {blurred}")
    if reel is not None:
        print(f"reel: {reel.path}")
    for level, title, message in rig.alerts:
        print(f"alert [{level}] {title}: {message}")
    ok = st.state == MachineState.REEL_FINISHED and st.frames_failed == 0 and blurred == 0
    return 0 if ok else 1


def _print_status(rig: SimRig) -> None:
    st = rig.machine.status()
    print(
        f"t={rig.clock.now_ns() / S:6.1f}s {st.state:14s} saved {st.frames_saved:5d} "
        f"failed {st.frames_failed:3d} fps {st.fps:4.1f} sync {st.sync_error_ms:.3f} ms"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wpcap")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="scan a simulated reel")
    d.add_argument("--reels", required=True, help="folder for reel folders")
    d.add_argument("--frames", type=int, default=300)
    d.add_argument("--delay-ms", type=float, default=40.0)
    d.add_argument("--switch-offset-ms", type=float, default=0.0)
    d.add_argument("--realtime", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "demo":
        return demo(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
