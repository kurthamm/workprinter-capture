# Movie Stuff

Free replacement for **CineCap**, the obsolete capture program for MovieStuff **WorkPrinter** 8mm film transfer machines. Built and tested first on the WorkPrinter XP.

Independent project; not affiliated with MovieStuff or AlternaWare.

## What it will do

1. Pick which WorkPrinter you're using (saved profiles, one per machine).
2. Press Capture and run the reel. The WorkPrinter's frame switch signals each frame (through the syncmouse, like CineCap), and every frame is saved at full camera resolution.
3. Press Create Movie to get a video file at 16, 18, 24 fps or a custom speed.

## Setup

- A WorkPrinter with its syncmouse (existing hardware, unchanged)
- Windows 11 PC or laptop with USB
- A USB camera that Windows recognizes as a standard webcam. A global-shutter camera is preferred; a trigger input is an optional upgrade (see `DECISIONS.md`, section 5)
- This software

## Status

Planning. No code yet.

- `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` — version 1 design spec
- `DECISIONS.md` — research and decisions
- `WorkPrinter_Windows_Requirements_v2.md` — the owner's original requirements document
