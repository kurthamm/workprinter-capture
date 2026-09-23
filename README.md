# WorkPrinter Capture

Free, modern replacement for **CineCap**, the obsolete capture program for MovieStuff **WorkPrinter** 8mm film transfer machines. It turns a WorkPrinter into an automated film scanner. Built and tested first on the WorkPrinter XP.

Independent project; not affiliated with MovieStuff or AlternaWare.

## How it works

- **One mini PC** runs everything: it works the cameras, saves one full-quality picture for every film frame, stores the reels, makes the movies and runs the web page. One mini PC handles two WorkPrinters.
- On each WorkPrinter, a small **USB sync box** (Raspberry Pi Pico 2) plugs into the WorkPrinter's sync socket, where the old syncmouse went. Nothing inside the WorkPrinter is changed. A modern **USB camera** looks at the film gate. Both plug into the mini PC.
- You run everything from **a web browser on any phone, tablet or laptop**.

Load the film, start the WorkPrinter and walk away. Recording starts by itself with the first frame, and every frame is counted. At the end of the reel, or if anything goes wrong, it sounds an alarm and sends an alert to your phone. Then press Create Movie: MP4, lossless archive (FFV1) or ProRes, at 16, 18, 24 fps or any speed.

## Status

Planning. No code yet.

- `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` — version 1 design spec (one mini PC + USB sync boxes)
- `DECISIONS.md` — research (including MovieStuff's archived instructions) and every decision
- `WorkPrinter_Windows_Requirements_v2.md` — the owner's original requirements document (Windows design, superseded)
