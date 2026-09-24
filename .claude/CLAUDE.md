# Movie Stuff — Claude context

## What this is
Replacement capture software for the owner's two MovieStuff WorkPrinter XP 8mm film machines (original software: CineCap, obsolete). Full research and decisions: `DECISIONS.md`. Owner's requirements doc: `WorkPrinter_Windows_Requirements_v2.md`.

## Files
- `README.md` — overview
- `DECISIONS.md` — all research, decisions, open questions (the complete record)
- `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` — version 1 design spec (draft, awaiting owner review)
- `WorkPrinter_Windows_Requirements_v2.md` — owner-supplied requirements (61 requirements); partly superseded, see DECISIONS.md section 6

## Status (2026-09-23)
- Planning only. No code yet. Public repo: https://github.com/kurthamm/workprinter-capture (PR workflow, CodeRabbit reviews). PR #1 holds all planning docs.
- **Current design (spec revision 3): one mini PC runs both WorkPrinters (same room). Per machine: USB camera + USB "sync box" (Raspberry Pi Pico 2) reading the RCA sync socket with µs timestamps, optional camera trigger. WorkPrinters are NOT modified (owner is not an electrician); no relays — operator runs the machine, system alarms/alerts.** Pi-5-per-machine (rev 2) and Windows (rev 1) designs dropped. App: Python 3.12, FastAPI, V4L2, FFmpeg on Ubuntu 24.04. Firmware: C, Pico SDK. Camera: modern camcorder (Panasonic HC-V800 recommended) as a plain live video feed via Elgato Cam Link 4K (HDMI→USB); each click grabs the picture from the feed (CineCap's method, better timed). Camera sits where the old camcorder did, into the condenser lens box. Syncmouse (owner's is PS/2) not needed; kept as no-wiring option via active PS/2-to-USB converter.
- Spec revision 3 awaiting owner review. Next: implementation plan (writing-plans skill).
- Open questions: XP model (owner thinks both have bulbs → flicker-safe exposure; photos for camera mount), optics, timing disk position, camera purchase, mini PC model (needs 2× USB 3 on separate controllers), license (MIT recommended).
- .NET SDK was installed earlier for the abandoned Windows plan; not needed now.

## Working with the owner
- Keep answers high-level and short. Don't dive into technical details unless asked.
- Owner wants the best solution and objects to penny-pinching ("Quit being cheap!") but also to overkill (a $600 camera for 8mm). Recommend the right tool for the job, not the cheapest or the most expensive.
- Everything is Linux (dev server, mini PC); develop and test against a simulated camera and simulated sync box here.
- Owner is not technical and memory is uncertain: confirm hardware facts against MovieStuff's archived pages (Wayback) rather than asking the owner to recall. Owner wants the best solution, not a minimal one.
