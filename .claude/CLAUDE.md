# Movie Stuff — Claude context

## What this is
Replacement capture software for the owner's two MovieStuff WorkPrinter XP 8mm film machines (original software: CineCap, obsolete). Full research and decisions: `DECISIONS.md`. Owner's requirements doc: `WorkPrinter_Windows_Requirements_v2.md`.

## Files
- `README.md` — overview
- `DECISIONS.md` — all research, decisions, open questions (the complete record)
- `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` — version 1 design spec (draft, awaiting owner review)
- `WorkPrinter_Windows_Requirements_v2.md` — owner-supplied requirements (61 requirements); partly superseded, see DECISIONS.md section 6

## Status (2026-09-23)
- Planning only. No code yet. Public repo: https://github.com/kurthamm/workprinter-capture (PR workflow, CodeRabbit reviews).
- Goal: THE CineCap replacement for all WorkPrinter owners, not just the owner's two XPs. Syncmouse mode is standard; camera-triggered is optional.
- Brainstorming (architectural path). Next: owner reviews the draft v1 spec, then implementation plan.
- Open questions: XP optics (projection/condenser lens present?), first camera purchase (ELP AR0234 proposed), which Windows PC, license (MIT recommended).
- .NET 10 SDK installed from Ubuntu apt (10.0.112); building a WPF win-x64 app on Linux verified with `-p:EnableWindowsTargeting=true`.

## Working with the owner
- Keep answers high-level and short. Don't dive into technical details unless asked.
- Quality matters, but be cost-sensible: recommend the cheapest option that meets the quality bar, explain what spending more buys.
- Target is Windows 11; this dev server is Linux. Core logic must be testable here; Windows-only parts get tested on the owner's PC.
