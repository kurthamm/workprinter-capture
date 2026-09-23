# WorkPrinter Capture — Design Spec (Version 1)

**Date:** 2026-09-23
**Revision:** 2 — Raspberry Pi + mini PC design (replaces the Windows design in revision 1; see git history and `DECISIONS.md` section 10)
**Status:** Draft for owner review
**Background:** `DECISIONS.md` (all research and decisions), `WorkPrinter_Windows_Requirements_v2.md` (owner's original requirements; its intent is kept, its Windows platform is replaced)

---

## 1. What it is

**The modern replacement for CineCap**, for anyone who owns a MovieStuff WorkPrinter. Built and tested first on the owner's two WorkPrinter XPs, and published free on GitHub so other owners can use it. Independent project; not affiliated with MovieStuff or AlternaWare.

It turns a WorkPrinter into an automated 8mm film scanner:

- A **Raspberry Pi 5** on each WorkPrinter reads the frame switch, controls the lamp and motor, runs the camera and captures one full-quality picture per film frame.
- A **mini PC** stores the reels, makes the movies and serves the web page used to run everything. One mini PC serves both WorkPrinters.
- The operator uses **a web browser on any phone, tablet or laptop**. No software to install on the viewing device.

Everything runs on the owner's home network. No internet, account or subscription.

## 2. Goals

1. **Every frame, once, in order.** The Pi sees every switch closure directly, so every film frame is accounted for as one saved picture or one reported failure. Nothing is lost silently.
2. **Full quality.** Full camera resolution, lossless saved pictures, archival movie formats. No DV-era limits.
3. **Hands-off operation.** Load film, start the scan, walk away. The system runs the projector, stops cleanly at the end of the reel, and stops instantly on any problem.
4. **Always know it's working.** A live status page, loud alarm and optional phone alert.
5. **Never lose work.** Frames are saved on the Pi as they're captured and copied to the mini PC; a crash, network drop or power cut loses at most the frame being written.
6. **No changes to the WorkPrinter that can't be undone.** The sync connection just plugs in; lamp and motor control is added alongside the existing switches and can be removed.
7. **Built for every WorkPrinter owner.** Works with the original syncmouse cable, ordinary USB cameras, and common parts. Open source with a setup guide and parts list.
8. **Room to grow.** The design leaves space for the "best solution" upgrades (HDR, stepper motor, 12-bit cameras, automatic frame alignment, color restoration) without rework.

## 3. Physical setup

### 3.1 Overview

```text
 ┌──────────────────┐              ┌──────────────────┐
 │  WorkPrinter 1   │              │  WorkPrinter 2   │
 │ gate ◄── lamp    │              │ gate ◄── lamp    │
 └─┬──────┬─────▲───┘              └─┬──────┬─────▲───┘
   │sync  │lamp │camera looks        │sync  │lamp │
   │(RCA) │motor│at the gate         │(RCA) │motor│
   │      │relays                    │      │relays
 ┌─▼──────▼─────┴───┐              ┌─▼──────▼─────┴───┐
 │ Raspberry Pi 5   │              │ Raspberry Pi 5   │
 │ + USB camera     │              │ + USB camera     │
 │ + local SSD      │              │ + local SSD      │
 └────────┬─────────┘              └────────┬─────────┘
          │  wired Ethernet                 │
          └──────────────┬──────────────────┘
                  ┌──────▼───────┐
                  │   Mini PC    │  reel storage, movies, web page
                  └──────┬───────┘
                         │ home network
                         ▼
          Browser on any phone / tablet / laptop
```

### 3.2 On each WorkPrinter ("the node")

| Part | Choice | Purpose |
|---|---|---|
| Computer | **Raspberry Pi 5, 8 GB**, official 27 W power supply, official active cooler, case | Runs the node software |
| Local storage | **NVMe SSD (256–512 GB) on an M.2 HAT**, or a USB 3 SSD | Operating system and frame spool |
| Connections | **GPIO screw-terminal HAT** | Clean, screwed-down wiring for sync and relays |
| Sync input | **RCA cable (male–male)** + **RCA female to screw-terminal adapter** | WorkPrinter sync socket → Pi input pin |
| Lamp and motor control | **Relay HAT or opto-isolated relay module**, 2+ channels | Pi turns lamp and motor on and off |
| Camera | **USB 3 global-shutter camera** (baseline: ELP AR0234, 1920×1200) with a close-up/macro lens | Captures the frames |
| Network | Wired Ethernet to the home network | Link to the mini PC |

### 3.3 The mini PC ("the hub")

| Part | Choice | Purpose |
|---|---|---|
| Computer | Modern mini PC, **8+ cores (e.g. AMD Ryzen 7 or Intel Core Ultra), 32 GB RAM**, hardware video encoding | Fast movie creation; headroom for HDR and restoration later |
| System drive | 1 TB NVMe | Operating system and software |
| Reel storage | **4 TB or larger SSD or hard drive** | All reels (a 400 ft reel is about 120 GB of frames) |
| Operating system | **Ubuntu 24.04 LTS** | Same Linux as the Pis and the dev server |
| Network | Wired Ethernet | Link to the Pis |

### 3.4 Storage sizing

Each frame is about 3–5 MB at 1920×1200 (lossless PNG).

| Film | Frames | Frames on disk |
|---|---|---|
| 50 ft Super 8 (about 3 min at 18 fps) | about 3,600 | about 15 GB |
| 400 ft Super 8 (about 25 min) | about 28,800 | about 120 GB |

Super 8 has 72 frames per foot; Regular 8 has 80.

## 4. Connecting to the WorkPrinter

### 4.1 Sync input (no changes to the WorkPrinter)

The WorkPrinter's sync socket (where the syncmouse used to plug in) is an RCA socket across the frame microswitch. The switch closes once per frame.

```text
WorkPrinter sync socket ─► RCA cable ─► RCA-to-screw adapter ─┬─ centre ─► Pi GPIO input
                                                               └─ outer  ─► Pi ground
```

- The Pi input uses its internal pull-up resistor: switch open = high, switch closed = low. No extra electronics.
- The exact pin is fixed in the setup guide (default: GPIO 17, physical pin 11; ground on physical pin 9).
- **Alternative for owners who don't want to wire:** plug an existing USB syncmouse into the Pi. The node listens only to that mouse's left button. Same behavior, slightly less precise timing.

### 4.2 Lamp and motor control

- Each relay is wired **in series with the WorkPrinter's own switch** for that function:
  - WorkPrinter switch **on** = "enabled"; the Pi's relay decides run/stop.
  - WorkPrinter switch **off** = nothing runs, whatever the Pi does.
  - So **either the operator or the Pi can always stop the machine.**
- The operator can put the WorkPrinter back to original by removing the relay wiring.
- **Wiring is designed only after inspecting the owner's machine** (photos of the switch panel and inside the back cover). Newer XPs have a DC motor and LED with toggle switches on the back cover; older XPs have a tungsten bulb and push buttons. If a relay would switch mains voltage, that wiring must be done by someone qualified, using a relay rated for it.
- The node software supports relay control from day one; relay use is switched on per machine once the wiring is installed and tested.

### 4.3 Stopping with a frame in the gate

When the Pi stops the motor (end of reel, fault, or Stop), it cuts the motor relay a set delay after a sync click, so the film stops with a frame sitting in the gate, as MovieStuff's old remote did. The delay is calibrated per machine to account for the motor coasting.

### 4.4 The timing disk

- The switch closes at a point in each frame cycle set by the **timing disk** inside the WorkPrinter. On the owner's machines it may still be set for an old camcorder's delay.
- The new system does not depend on its position: the node measures when the film is still and applies a **software delay** (section 5.3).
- The setup guide includes MovieStuff's procedure to reset the disk to the "claw at bottom of pulldown" position (marks on the pulley and disk) for owners who want the switch to mark the exact moment the frame lands.

### 4.5 Camera placement

- The camera with a macro lens looks at the gate directly, replacing the old condenser-lens-plus-camcorder arrangement, or looks through the condenser lens if that gives a better image on a particular machine. The mount is designed after inspecting the owner's machine.
- The picture may be mirror-reversed depending on placement; flip and rotate are software settings.
- The LED light is daylight-balanced; the camera's white balance is set once and locked.

## 5. How capture works

### 5.1 Clocks

The sync switch and the camera are both read by the same Pi, and both are timestamped by the Linux kernel on the **same monotonic clock**, so "which picture goes with which click" is a direct comparison of times on one clock, with no guessing:

- **Sync:** GPIO edge events are timestamped by the kernel with `CLOCK_MONOTONIC` (libgpiod edge-event clock set to monotonic). The USB syncmouse alternative uses input-event timestamps, also set to `CLOCK_MONOTONIC`.
- **Camera:** the node checks that every V4L2 capture buffer reports `V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC`. A camera whose buffers report realtime or unknown timestamps is **rejected** in the Setup screen with a clear message. A timestamp taken by the software when a buffer is delivered is never used as a substitute for the capture timestamp.

### 5.2 Sync handling

- Every switch closure is timestamped and given a sequence number.
- **Contact bounce** is filtered: a closure within a set time after the previous one (default 20 ms, adjustable) is recorded as bounce and ignored. The filter is shown and adjustable; rejected closures are logged, never silently dropped.
- The node also measures the steady frame rate and flags any interval far outside it.

### 5.3 Continuous mode (standard, works with any USB camera)

1. The camera streams continuously (typically 30–60 pictures per second, uncompressed where the camera allows).
2. The node keeps the last second of pictures in a ring buffer.
3. For each click, the node picks the picture whose timestamp is closest to **click time + delay**. The delay is the **software timing disk**, set per machine.
4. If no picture falls within the allowed window, the frame is recorded as **failed** and the scan stops (section 6.4). A previous picture is never reused.

**Calibration screen:** the operator runs a few seconds of film. For several clicks the screen shows the pictures before and after each click side by side, with a sharpness/motion score under each. The operator clicks the sharpest; the delay is saved for that machine. The node proposes the best delay automatically from the scores.

**Fix it later without rescanning (from Velocity):** optionally the node also keeps the neighbouring pictures (one before, one after) for each frame. If a reel turns out slightly blurred, the operator changes the delay and the frames are re-picked from the kept neighbours. This triples storage, so it is off by default and on during calibration and test reels.

### 5.4 Triggered mode (upgrade, for cameras with a trigger input)

1. The camera's trigger input is wired to a Pi output pin.
2. For each click, the Pi sends a trigger pulse to the camera **after the software delay**, when the film is still.
3. The camera takes exactly one picture per pulse; there are no in-between pictures and no calibration by eye.
4. Because the Pi sent every pulse, it knows exactly how many pictures should arrive. Each pulse is matched to one picture or recorded as failed.

Supported only for cameras whose trigger mode has been tested and listed in the setup guide. Continuous mode remains available on every camera.

### 5.5 Camera settings

- The node lists the camera's modes and prefers uncompressed ones (YUYV/NV12). Compressed modes (MJPEG) are allowed with a visible "lower quality" warning; the mode used is recorded in the reel.
- Exposure, white balance, gain and focus are set in the Setup screen and **locked** for the scan. If a camera can't lock a setting, the Setup screen warns.

## 6. Operation

### 6.1 Starting a scan — two ways

**A. From the web page:** press **Scan Reel**. The node checks everything (camera streaming, storage space, sync connected, relays working), turns on the lamp, starts the motor, and starts recording when the first frame click arrives.

**B. From the projector:** with the node in **Ready**, the operator starts the WorkPrinter by hand. The first frame click tells the node a reel has started, and it starts recording automatically.

Either way a new reel is created, named with the machine and date/time (for example `WorkPrinter 1 — 2026-10-04 14:32`), and can be renamed later.

### 6.2 While scanning

The Scan screen shows:
- A big status: **green "Recording"**, **amber "Warning"**, or **red "Stopped — problem"**.
- Live camera picture and the last saved frame.
- Frames saved, frames failed, frames per second, feet scanned (by film type), resulting movie length at the chosen speed.
- Pi disk space, hub disk space, Pi temperature, network status.

### 6.3 End of reel

The frame switch keeps clicking after the film runs out (it is driven by the motor), so the end is detected by the **camera**:
- When the gate shows an **empty, evenly bright picture** for a set number of frames, the node stops the motor, turns off the lamp, and finishes the reel.
- To avoid stopping on clear leader at the start, end detection only becomes active after a set number of picture frames have been captured.
- A film break looks the same and also stops the machine.
- The empty-gate frames at the end are marked and excluded from the movie by default.

### 6.4 Problems

On any fault the node **stops the motor within one frame** — at the next frame-in-gate point (section 4.3), or at once if sync clicks have stopped — (if relay control is installed), keeps every saved frame, and the page turns **red** with a loud alarm and a plain message saying what happened and what to do. Faults:

| Fault | Examples |
|---|---|
| Camera | Unplugged, stopped sending pictures, changed mode |
| Missed frame | No picture for a click; far too long between clicks |
| Storage | Pi spool nearly full; write error |
| Sync | Clicks stop while the motor should be running |
| Pi health | Overheating |
| Operator | Stop pressed |

If relay control is not installed, the page shows **"STOP THE WORKPRINTER NOW"**, because the node cannot stop the motor itself.

**Network loss to the hub is not a fault:** the node keeps scanning and saving to its own SSD, shows a warning, and catches up when the network returns. It only stops if its own spool fills.

**Resume:** after a fault the operator fixes the problem and presses **Resume**. This starts a new segment in the same reel, after the operator confirms the film position (the page shows the last saved frame for comparison).

### 6.5 Alerts

- Browser: color, alarm sound, and a browser notification.
- **Phone alert (optional):** push notification through a self-hosted **ntfy** server on the hub, for "reel finished", "problem", and "movie ready".

## 7. Storage and reliability

### 7.1 Where frames live

1. The node writes each frame to its **local SSD spool** first (temporary file, then renamed into place, then logged).
2. The node sends each saved frame to the hub, with a checksum.
3. The hub writes it into the reel folder, checks the checksum, and acknowledges.
4. The node deletes spooled frames only after the hub has acknowledged them and the reel is closed. Spool retention is configurable.
5. **Retries are safe.** Each frame has a stable identity: reel ID, segment number and frame number. If an acknowledgement is lost and the node resends, the hub acknowledges a resend with the same identity and checksum without writing it twice, and rejects (and reports as a fault) a resend with the same identity but different content.

### 7.2 Reel folder on the hub

```text
reels/
  WorkPrinter 1 — 2026-10-04 1432/
    reel.json         name, notes, machine, film type, speeds, camera + settings used, delay, crop/rotation
    journal.jsonl     one line per event: click, frame saved, frame failed, bounce, fault, segment start/stop
    frames/
      000001.png
      000002.png
    neighbours/       (only if "keep neighbours" was on)
    exports/
      WorkPrinter 1 — 2026-10-04 1432 — 18fps.mp4
```

- **Pictures:** lossless PNG at full camera resolution; 16-bit PNG when a camera delivers more than 8 bits. Never cropped or altered.
- **Accounting rule:** clicks accepted = frames saved + frames pending + frames failed. It must balance for every segment.
- **Recovery:** when a node or hub restarts, it checks frames against the journal, keeps every complete frame, and flags any half-written one. Existing frames are never overwritten.

## 8. Review and movies (on the hub)

### 8.1 Review

- Step through frames, jump to a number, view full size.
- Frames flagged by the system (failed, suspicious interval, empty gate) are listed and clickable.
- Set rotation/flip, crop and first/last frame. Originals are never changed.
- **Keep / Throw** a reel (Throw asks for confirmation and deletes it).

### 8.2 Create Movie

| Preset | Use |
|---|---|
| **MP4 (H.264)** | Everyday viewing, sharing, TVs, phones. Default. |
| **Archival (FFV1 in MKV)** | Lossless master for long-term keeping. |
| **Editing (ProRes 422 HQ in MOV)** | For Premiere, DaVinci Resolve, Final Cut. |

- Speeds: 16, 18, 24 fps or custom; several speeds and formats per reel.
- One film frame = one video frame. Length = frames ÷ speed (1,800 frames at 18 fps = 100 seconds). No frame blending, no added frames.
- Before encoding: every frame in the range must exist and open; gaps block the export and are listed.
- After encoding: frame count and length are checked.
- Progress, cancel, Open/Download. Export again any time without rescanning.
- Optional: create an MP4 automatically when a reel finishes.
- Uses **FFmpeg** on the hub. Silent (no sound).

## 9. Software

### 9.1 Structure

Written in **Python 3.11+** (the version on Raspberry Pi OS Bookworm), one repository, three parts:

| Part | Runs on | Does |
|---|---|---|
| **core** | Node and hub | Reel format, journal, accounting, recovery, frame matching, bounce filter, end-of-gate detection, shared data types |
| **node** | Each Raspberry Pi | Sync input (libgpiod), relays (GPIO), camera (V4L2), ring buffer, frame picking, spool, forwarding to hub, safety supervisor, small HTTP API for the hub |
| **hub** | Mini PC | Web page (FastAPI + a simple browser front end), machine registry, reel storage, review, export (FFmpeg), alerts (ntfy) |

- **Hardware sits behind small interfaces** (sync source, relay driver, camera source). Simulated versions of each plug into the same interfaces for tests and a **Demo Mode**.
- The browser talks only to the hub. The hub talks to each node over the network. The live camera picture is passed through the hub.
- The node's **safety supervisor runs on the Pi**, independent of the hub and network: it can always stop the motor on a fault.
- Capture, saving, forwarding and the web page run in separate processes/threads with fixed-size queues, so a slow page or network never costs a frame.

### 9.2 Security

- Home network only; nothing is exposed to the internet.
- **All traffic is encrypted (HTTPS/TLS)**, browser → hub and hub → node, so the password and tokens are never sent in clear text on the home network.
  - The installer creates a small local certificate authority on the hub and issues certificates for the hub and each node. Browsers show a one-time "trust this certificate" step (documented in the setup guide).
  - Hub and node verify each other's certificates (mutual TLS); a node only accepts commands from its hub.
- Web page protected by a password set during installation.
- The node API accepts only the operations the hub needs (status, settings, start/stop, preview, frame transfer).

### 9.3 Installation

- **Node:** Raspberry Pi OS (64-bit, Bookworm) + an install script that sets up the node service. Later: a ready-made SD card image for other owners.
- **Hub:** Ubuntu 24.04 + an install script that sets up the hub service, FFmpeg and ntfy.
- Both run as system services that start at boot.

## 10. Testing

### 10.1 Automated (dev server, every change; run with `testrepo`)

Using the simulators:
- 1,000+ simulated frames with known numbers saved in order, none lost or doubled.
- Bounce filtering; missed clicks; clicks with no picture → failed frame + fault + motor stop.
- Continuous-mode picking: simulated pull-down blur frames are never chosen at the correct delay; delay changes pick the expected frames; neighbour re-picking.
- Triggered mode: every pulse matched to one picture or a failure.
- End of reel: empty gate stops the scan; clear leader at the start does not.
- Faults: camera stall, disk full, overheating, operator stop → motor relay off.
- Network loss: node keeps spooling; hub catches up with no gaps or duplicates.
- Recovery after simulated crashes on node and hub.
- Accounting balances for every segment.
- Movies: 1,800 frames at 18 fps = 1,800 frames and 100 s, for each of the three presets.

### 10.2 Hardware (owner's equipment)

1. **Hub install:** Demo Mode scan and movie on the mini PC.
2. **Pi bench test, no WorkPrinter:** camera live, focus, settings lock, test frame.
3. **Sync by hand:** tap the RCA wire; each tap = one frame; bounce filter checked.
4. **Relays by hand:** lamp and motor relays click on command; stop works from the page and from the safety supervisor.
5. **WorkPrinter 1, test reel:** calibrate the delay, scan at least 500 frames, inspect every frame by eye — sharp, in order, no gaps or repeats. Check end-of-reel stop and stop-with-frame-in-gate. Watch the movie.
6. **WorkPrinter 2:** same, with its own settings.
7. **Full reel** on each machine start to finish with no slowdown, spool growth or memory growth.
8. **Fault drill:** unplug the camera mid-scan; the motor stops, the alarm sounds, all earlier frames are kept.

The system is not called hardware-ready until steps 5–8 pass.

## 11. Delivery

- Source code on GitHub (public), with install scripts, pinned dependency versions and automated tests.
- `README.md` as the setup guide for any WorkPrinter owner: parts list, wiring pictures, installation, first scan, calibration, timing-disk reset procedure, tested cameras.
- `CHANGELOG.md` from the first release.

## 12. Build order

1. **Core, simulators, hub web page, export** — everything testable on the dev server.
2. **Node on a real Pi** with camera and sync (bench tests 2–3).
3. **Relays**, after the owner's machine is inspected and wired (bench test 4).
4. **Film tests** on both machines (tests 5–8).
5. **Packaging** and the setup guide.

## 13. Not in version 1 (designed for, built later)

- HDR (several exposures per frame) — needs a controllable light and camera; the hub has the power for it.
- Stepper motor conversion for exact frame-by-frame motion.
- 12-bit industrial (GenICam) cameras.
- Automatic frame alignment on sprocket holes, stabilization.
- Automatic color restoration, dust and scratch removal.
- Sound.
- Ready-made SD card image.
- Windows or Mac versions.

## 14. Risks

| Risk | What we do |
|---|---|
| Owner's XP switch/motor wiring is unknown | Relay wiring designed only after photos/inspection; sync input and capture work without relays. |
| Relay would switch mains voltage | Rated relay; wiring done by someone qualified; documented clearly. |
| DC motor coasts, so stop-with-frame-in-gate is imprecise | Calibrate the stop delay per machine; worst case, stop anywhere and the operator jogs by hand. |
| Camera trigger mode doesn't work as advertised | Continuous mode works with any USB camera. |
| Camera can't lock exposure/white balance | Warn; list tested cameras in the guide. |
| Clear leader or very bright scenes look like an empty gate | End detection only after picture frames have been seen, and requires many consecutive empty frames; thresholds adjustable. |
| Pi overheats in long scans | Active cooler; temperature monitored; fault before throttling affects capture. |
