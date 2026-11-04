# WorkPrinter Capture

Free, modern replacement for **CineCap**, the obsolete capture program for MovieStuff **WorkPrinter** 8mm film transfer machines. It turns a WorkPrinter into an automated film scanner. Built and tested first on the WorkPrinter XP.

Independent project; not affiliated with MovieStuff or AlternaWare.

## How it works

- **One Windows PC** runs everything: it takes the camcorder's live video, saves one full-quality picture for every film frame, stores the reels, makes the movies and runs the web page. One PC handles two WorkPrinters.
- On each WorkPrinter, a small **USB sync box** (Raspberry Pi Pico 2) plugs into the WorkPrinter's sync socket, where the old syncmouse went. Nothing inside the WorkPrinter is changed. A modern **camcorder** sits where the old one did and feeds live video over HDMI. Both plug into the PC.
- You run everything from **a web browser on any phone, tablet or laptop**.

Load the film, start the WorkPrinter and walk away. Recording starts by itself with the first frame, and every frame is counted. At the end of the reel, or if anything goes wrong, it sounds an alarm on the web page, and can also send an alert to your phone (optional; set up during installation). Then press Create Movie: MP4, lossless archive (FFV1) or ProRes, at 16, 18, 24 fps or any speed.

## The whole process

Scanning is stage one. The same PC then runs **DaVinci Resolve** (free) to stabilize, clean up and color-restore the film, put reels in order and add music and narration, and finally delivers **MP4 files** (USB stick, home server) and **DVDs** for relatives. See `DECISIONS.md` section 12.

## Status

The capture core and the web page/service exist and their tests pass (Python, simulated camera and sync box). Still to come: Review and Create Movie, the Pico firmware, the Windows camera backend and the installer.

## Run it (Demo Mode)

Demo Mode runs two simulated WorkPrinters, so no hardware is needed. The full setup guide comes later.

```
python -m wpcap init-config --out wpcap.toml --reels DIR --certs DIR
python -m wpcap serve --config wpcap.toml
```

`init-config` asks for a password. Optional flags: `--bind`, `--port` (default 8443), `--sim-frames`, `--host`, `--ip` (names and addresses for the certificate).

Then open `https://<pc-name-or-ip>:8443/` on a phone or PC and log in. Both simulated machines start a simulated reel when `serve` starts. With the default `--sim-frames` of 300, each reel runs about 40 seconds, so log in promptly. When a reel finishes, press New Reel to record another.

**One-time certificate step.** The page uses HTTPS with a certificate made by "WorkPrinter Capture Local CA". Import `certs/ca.crt` (in the folder given to `--certs`) into the phone or PC as a trusted certificate, and the browser shows no warning.

**Phone alerts (optional).** Install ntfy (ntfy.sh) and run `ntfy serve --listen-http :2586`. Uncomment the `[ntfy]` section in `wpcap.toml`, then subscribe to its topic in the ntfy phone app.

- `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md` — version 1 design spec (one Windows PC + USB sync boxes)
- `DECISIONS.md` — research (including MovieStuff's archived instructions) and every decision
- `HARDWARE.md` — agreed parts list and purchase tracker
- `WorkPrinter_Windows_Requirements_v2.md` — the owner's original requirements document (partly superseded)
