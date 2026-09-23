# Movie Stuff — Claude context

## What this is
Replacement capture software for the owner's two MovieStuff WorkPrinter XP 8mm film machines (original software: CineCap, obsolete). Full research and decisions: `DECISIONS.md`. Owner's requirements doc: `WorkPrinter_Windows_Requirements_v2.md`.

## Files
- `README.md` — overview
- `DECISIONS.md` — all research, decisions, open questions (the complete record)
- `WorkPrinter_Windows_Requirements_v2.md` — owner-supplied requirements (61 requirements); partly superseded, see DECISIONS.md section 6

## Status (2026-09-23)
- Planning only. No code, no git repo yet.
- Brainstorming (architectural path) in progress. Next: owner approves writing the spec, then spec review, then implementation plan.
- Open questions: XP optics (projection/condenser lens present?), first camera purchase (ELP AR0234 proposed), which Windows PC, which modern features go in v1.

## Working with the owner
- Keep answers high-level and short. Don't dive into technical details unless asked.
- Quality matters, but be cost-sensible: recommend the cheapest option that meets the quality bar, explain what spending more buys.
- Target is Windows 11; this dev server is Linux. Core logic must be testable here; Windows-only parts get tested on the owner's PC.
