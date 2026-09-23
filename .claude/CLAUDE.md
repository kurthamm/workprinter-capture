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
- **Current design: WorkPrinter XP + Raspberry Pi 5 per machine ("node": sync via RCA to GPIO, lamp/motor relays, USB camera, local SSD spool) + one mini PC ("hub": reels, FFmpeg movies, web UI) + browser.** Windows design abandoned. Python 3.11+, FastAPI, libgpiod, V4L2.
- Spec revision 2 (Pi + mini PC) awaiting owner review. Next: implementation plan (writing-plans skill).
- Open questions: XP model (photos of switches/inside back), optics, timing disk position, camera purchase, mini PC model, license (MIT recommended).
- .NET SDK was installed earlier for the abandoned Windows plan; not needed now.

## Working with the owner
- Keep answers high-level and short. Don't dive into technical details unless asked.
- Owner wants the best solution and objects to penny-pinching ("Quit being cheap!") but also to overkill (a $600 camera for 8mm). Recommend the right tool for the job, not the cheapest or the most expensive.
- Everything is Linux (dev server, Pi, mini PC); develop and test against simulated camera/sync/relays here.
- Owner is not technical and memory is uncertain: confirm hardware facts against MovieStuff's archived pages (Wayback) rather than asking the owner to recall. Owner wants the best solution, not a minimal one.
