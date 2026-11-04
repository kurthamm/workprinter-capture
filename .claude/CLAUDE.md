# Movie Stuff — Claude context

## What this is
Replacement capture software for the owner's two MovieStuff WorkPrinter XP 8mm film machines (original software: CineCap, obsolete). Full research and decisions: `DECISIONS.md`. Owner's requirements doc: `WorkPrinter_Windows_Requirements_v2.md`.

## Files
- `README.md` — overview
- `DECISIONS.md` — all research, decisions, open questions (the complete record)
- `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` — version 1 design spec (revision 4, Windows)
- `HARDWARE.md` — agreed parts list and purchase tracker (tick items as the owner reports them)
- `WorkPrinter_Windows_Requirements_v2.md` — owner-supplied requirements (61 requirements); partly superseded, see DECISIONS.md section 6

## Status (2026-10-11)
- Planning only. No code yet. Public repo: https://github.com/kurthamm/workprinter-capture (PR workflow, CodeRabbit reviews). PR #1 holds all planning docs.
- **2026-10-11: Windows 11 decided (DECISIONS §12).** The scan is stage 1 of 3: scan (this app) → restore/assemble in DaVinci Resolve (owner does it, with a written step-by-step) → deliver MP4 on USB + DVD (Blu-ray on request). PC is a used Windows **tower with an Nvidia GPU 6 GB+, 32 GB RAM** (Resolve needs it); bought on shopgoodwill, one WorkPrinter first. Camera backend is Windows Media Foundation (timestamp check is the first bench test). App developed/tested on Linux with simulators; Windows backend via GitHub Windows runners + owner's PC. HC-V800 discontinued → HC-V900. Backup mandatory. App does NOT restore or capture audio.
- **Design (spec revision 3→4): one PC runs both WorkPrinters (same room). Per machine: USB camera + USB "sync box" (Raspberry Pi Pico 2) reading the RCA sync socket with µs timestamps, optional camera trigger. WorkPrinters are NOT modified (owner is not an electrician); no relays — operator runs the machine, system alarms/alerts.** Pi-5-per-machine (rev 2) and Windows (rev 1) designs dropped. App: Python 3.12, FastAPI, Media Foundation, FFmpeg on Windows 11. Firmware: C, Pico SDK. Camera: modern camcorder (Panasonic HC-V900) as a plain live video feed via Elgato Cam Link 4K (HDMI→USB); each click grabs the picture from the feed (CineCap's method, better timed). Camera sits where the old camcorder did, into the condenser lens box. Syncmouse (owner's is PS/2) not needed; kept as no-wiring option via active PS/2-to-USB converter.
- Owner agreed to the end-to-end process and all core decisions on 2026-10-11. Next: owner buys PC + phase 2/3 parts; implementation plan (writing-plans skill).
- Open questions: XP model (owner thinks both have bulbs → flicker-safe exposure; photos for camera mount), optics, timing disk position, camera purchase, license (MIT recommended).

## Working with the owner
- Keep answers high-level and short. Don't dive into technical details unless asked.
- Owner wants the best solution and objects to penny-pinching ("Quit being cheap!") but also to overkill (a $600 camera for 8mm). Recommend the right tool for the job, not the cheapest or the most expensive.
- Dev server is Linux; target PC is Windows 11. Develop and test against a simulated camera and simulated sync box here; keep the Windows-only code to the camera backend.
- **Partner, not pleaser:** judge what the owner mentions on merit and say "not needed" plainly; don't bend the plan to accommodate. Research the whole process before answering; no quick piecemeal decisions.
- Owner is not technical and memory is uncertain: confirm hardware facts against MovieStuff's archived pages (Wayback) rather than asking the owner to recall. Owner wants the best solution, not a minimal one.
