# WorkPrinter Capture — Design Spec (Version 1)

**Date:** 2026-09-23
**Revision:** 3. One mini PC runs both WorkPrinters, with a small USB sync box (Raspberry Pi Pico 2) on each machine. The WorkPrinters are not modified: everything plugs into their existing sockets. This replaces the Pi-per-machine design of revision 2 and the Windows design of revision 1. See git history and `DECISIONS.md` section 10.
**Status:** Draft for owner review
**Background:** `DECISIONS.md` (all research and decisions), `WorkPrinter_Windows_Requirements_v2.md` (owner's original requirements; its intent is kept, its Windows platform is replaced)

---

## 1. What it is

**The modern replacement for CineCap**, for anyone who owns a MovieStuff WorkPrinter. It is built and tested first on the owner's two WorkPrinter XPs and published free on GitHub so other owners can use it. It is an independent project, not affiliated with MovieStuff or AlternaWare.

It turns a WorkPrinter into an automated 8mm film scanner:

- **One mini PC** runs everything. It works the cameras, captures one full-quality picture per film frame, stores the reels, makes the movies and serves the web page. One mini PC runs both WorkPrinters.
- **A sync box on each WorkPrinter** (Raspberry Pi Pico 2, plugged into the mini PC by USB) plugs into the WorkPrinter's sync socket in place of the old syncmouse. It reads the frame switch with microsecond timing.
- **A USB camera on each WorkPrinter** looks at the film gate and plugs into the mini PC.
- The operator uses **a web browser on any phone, tablet or laptop**, or on a screen plugged into the mini PC. Nothing needs installing on the viewing device.

Everything runs on the owner's home network. No internet, account or subscription is needed.

## 2. Goals

1. **Every frame, once, in order.** The sync box sees every switch closure and numbers it, so every film frame is accounted for as one saved picture or one reported failure. Nothing is lost silently.
2. **Full quality.** Full camera resolution, lossless saved pictures and archival movie formats. No DV-era limits.
3. **Walk-away operation.** Load film, start the WorkPrinter and walk away. The system records every frame and calls the operator back (alarm and phone alert) at the end of the reel or on any problem.
4. **Always know it's working.** A live status page, a loud alarm and an optional phone alert.
5. **Never lose work.** Frames are saved to disk as they're captured, so a crash or power cut loses at most the frame being written.
6. **No changes to the WorkPrinter.** Everything plugs into its existing sync socket and the camera looks at the gate. Nothing inside the machine is touched. The operator runs the WorkPrinter with its own switches, as always.
7. **Built for every WorkPrinter owner.** It works with ordinary USB cameras and common parts, and has a no-wiring option using an existing syncmouse. It is open source, with a setup guide and parts list.
8. **Room to grow.** The design leaves space for the "best solution" upgrades (HDR, stepper motor, 12-bit cameras, automatic frame alignment, color restoration) without rework.

## 3. Physical setup

### 3.1 Overview

Both WorkPrinters sit in the same room, with the mini PC between them.

```text
 ┌──────────────────┐                  ┌──────────────────┐
 │  WorkPrinter 1   │                  │  WorkPrinter 2   │
 │ sync      gate   │                  │ sync      gate   │
 │ socket     ▲     │                  │ socket     ▲     │
 └──┬─────────┼─────┘                  └──┬─────────┼─────┘
    │RCA      │ camera looks              │RCA      │ camera looks
    │cable    │ at the gate               │cable    │ at the gate
 ┌──▼──────┐ ┌┴───────────┐            ┌──▼──────┐ ┌┴───────────┐
 │Sync box │ │ USB camera │            │Sync box │ │ USB camera │
 │(Pico 2) │ └─────┬──────┘            │(Pico 2) │ └─────┬──────┘
 └────┬────┘       │                   └────┬────┘       │
      │ USB        │ USB 3                  │ USB        │ USB 3
      └────────────┴──────────┐  ┌──────────┴────────────┘
                          ┌───▼──▼────┐
                          │  Mini PC  │  capture, reels, movies, web page
                          └─────┬─────┘
                                │ home network (Ethernet or Wi-Fi)
                                ▼
              Browser on any phone / tablet / laptop
```

### 3.2 On each WorkPrinter

| Part | Choice | Purpose |
|---|---|---|
| Sync box | **Raspberry Pi Pico 2 H** (headers already fitted, no soldering) on a **screw-terminal breakout board**, in a small case | Reads the frame switch; triggers the camera (optional) |
| Sync input | **RCA cable (male–male)** + **RCA female to screw-terminal adapter** (inside the sync box, so the box has an RCA socket) | WorkPrinter sync socket → sync box |
| Camera | **USB 3 global-shutter camera** (baseline: ELP AR0234, 1920×1200) with a close-up/macro lens | Captures the frames |
| Cables | USB cable sync box → mini PC; USB 3 cable camera → mini PC (see 3.4) | |

### 3.3 The mini PC (one for both WorkPrinters)

| Part | Choice | Purpose |
|---|---|---|
| Computer | Modern mini PC, **8+ cores (e.g. AMD Ryzen 7 or Intel Core Ultra), 32 GB RAM**, hardware video encoding | Two cameras capturing at once, fast movie creation, headroom for HDR and restoration later |
| USB | **At least two USB 3 (10 Gbps) ports, ideally on separate USB controllers**, plus two more ports for the sync boxes | One full-speed port per camera |
| System drive | 1 TB NVMe | Operating system and software |
| Reel storage | **4 TB or larger SSD** (internal second drive or USB 3/USB-C) | All reels (a 400 ft reel is about 120 GB of frames) |
| Operating system | **Ubuntu 24.04 LTS** | Same Linux as the dev server |
| Network | Ethernet or Wi-Fi to the home network | Browser access |
| Screen (optional) | Any monitor, keyboard and mouse | Run the web page directly on the mini PC |

### 3.4 Cable lengths

- **Cameras:** a plain USB 3 cable works reliably up to about 3 m (10 ft). Place the mini PC between the machines. For a longer run, use an **active USB 3 extension cable**, not a passive one.
- **Sync boxes:** USB 2 speed, so plain cables up to 5 m (16 ft).

### 3.5 Storage sizing

Each frame is about 3–5 MB at 1920×1200 (lossless PNG).

| Film | Frames | Frames on disk |
|---|---|---|
| 50 ft Super 8 (about 3 min at 18 fps) | about 3,600 | about 15 GB |
| 400 ft Super 8 (about 25 min) | about 28,800 | about 120 GB |

Super 8 has 72 frames per foot; Regular 8 has 80.

## 4. Connecting to the WorkPrinter

### 4.1 Sync input (no changes to the WorkPrinter)

The WorkPrinter's sync socket (where the syncmouse cable used to plug in) is an RCA socket across the frame microswitch. The switch closes once per frame.

```text
WorkPrinter sync socket ─► RCA cable ─► RCA-to-screw adapter ─┬─ centre ─► sync box input pin
                                                               └─ outer  ─► sync box ground
```

- The input uses the board's internal pull-up resistor: switch open = high, switch closed = low. No extra electronics are needed.
- The exact pins are fixed in the setup guide.
- **The syncmouse itself is not used.** It only converted the switch into a mouse click for CineCap. Owners keep it so the machine can go back to original.

### 4.2 No-wiring option: USB syncmouse

For owners who don't want to wire anything, an existing syncmouse can plug straight into the mini PC instead of a sync box:

- The software listens only to **that mouse's left button**, identified by its USB device, never by the screen pointer.
- A syncmouse with the old round **PS/2 plug** needs an **active PS/2-to-USB converter**. Cheap passive adapters only work with some mice.
- Timing is less precise than the sync box (about 1 ms instead of microseconds). This is still well within what continuous mode needs.

### 4.3 The operator runs the WorkPrinter

The software does not start or stop the WorkPrinter. The operator uses the machine's own switches, as with CineCap. The software records every frame from the first click, and calls the operator back at the end of the reel or on any problem (section 6).

Automatic lamp and motor control (relays wired into the WorkPrinter's switches) was considered and **left out**: it means opening the machine and rewiring its switches, and on bulb models those carry wall voltage. See section 13.

### 4.4 The timing disk

- The **timing disk** inside the WorkPrinter sets the point in each frame cycle where the switch closes. On the owner's machines it may still be set for an old camcorder's delay.
- The new system does not depend on its position. It measures when the film is still and applies a **software delay** (section 5.3).
- The setup guide includes MovieStuff's procedure to reset the disk to the "claw at bottom of pulldown" position (marks on the pulley and disk), for owners who want the switch to mark the exact moment the frame lands.

### 4.5 Camera placement

- The camera with a macro lens looks straight at the gate, replacing the old condenser-lens-plus-camcorder arrangement. If looking through the condenser lens gives a better image on a particular machine, it does that instead. The mount is designed after inspecting the owner's machine.
- The picture may be mirror-reversed depending on placement. Flip and rotate are software settings.
- **Light source:** the owner believes both machines have the older **bulb** (to be confirmed from photos); newer XPs have a daylight LED. Either way, the camera's white balance is set once for that light and locked.
- **Bulb flicker:** a bulb on wall power brightens and dims at twice the mains frequency (120 Hz in North America, 100 Hz elsewhere). MovieStuff warned it causes flicker and banding with fast shutter speeds. The Setup screen offers **flicker-safe exposure times** (whole multiples of 1/120 s or 1/100 s, per the mains setting), and warns if a bulb machine uses any other exposure. An LED retrofit is a possible later upgrade (section 13).

## 5. How capture works

### 5.1 The sync box

The sync box runs small, fixed firmware. It does only the jobs that need exact timing:

- **Timestamps every switch closure** with its microsecond hardware timer and gives it a sequence number.
- **Filters contact bounce** (section 5.3) and reports rejected closures.
- **Fires the camera trigger** in triggered mode (section 5.5).
- **Answers time-sync requests** from the mini PC (section 5.2).

It talks to the mini PC over USB serial. Every message from the box carries a sequence number, so a lost message shows up as a gap and is a fault. It is never silently skipped.

### 5.2 Clocks

"Which picture goes with which click" is decided by comparing times, so both must be on one clock:

- **Camera:** the software checks that every V4L2 capture buffer reports `V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC` (kernel `CLOCK_MONOTONIC`, stamped when the picture arrives). A camera whose buffers report realtime or unknown timestamps is **rejected** in the Setup screen with a clear message. A timestamp taken by the software when a buffer is delivered is never used as a substitute.
- **Clicks:** the sync box's timestamps are converted to the mini PC's `CLOCK_MONOTONIC` using a continuous time-sync exchange over USB. The mini PC regularly asks the box for its time. It keeps the fastest round trips, and it fits the offset and drift between the two clocks.
  - The expected conversion error is well under 1 ms. At 60 camera pictures per second, pictures are about 17 ms apart.
  - The Setup and Scan screens show the current sync error. If it goes over a set limit (default 2 ms), that is a fault.
- **Syncmouse option:** input-event timestamps from the kernel, set to `CLOCK_MONOTONIC`.

### 5.3 Sync handling

- Every switch closure is timestamped and given a sequence number.
- **Contact bounce** is filtered: a closure within a set time after the previous one (default 20 ms, adjustable) is recorded as bounce and ignored. The filter setting is shown and can be adjusted. Rejected closures are logged, never silently dropped.
- The software also measures the steady frame rate and flags any interval far outside it.

### 5.4 Continuous mode (standard, works with any USB camera)

1. The camera streams continuously (typically 30–60 pictures per second, uncompressed where the camera allows).
2. The software keeps the last second of pictures in a ring buffer.
3. For each click, it picks the picture whose timestamp is closest to **click time + delay**. The delay is the **software timing disk**, set per machine.
4. If no picture falls within the allowed window, the frame is recorded as **failed** and the scan stops (section 6.4). A previous picture is never reused.

**Calibration screen:** the operator runs a few seconds of film. For several clicks, the screen shows the pictures before and after each click side by side, with a sharpness/motion score under each. The software proposes the best delay from the scores. The operator confirms it or clicks the sharpest picture, and the delay is saved for that machine.

**Fix it later without rescanning (from Velocity):** optionally, the software also keeps the neighbouring pictures (one before and one after each frame). If a reel turns out slightly blurred, the operator changes the delay and the frames are re-picked from the kept neighbours. This triples storage, so it is off by default and on during calibration and test reels.

### 5.5 Triggered mode (upgrade, for cameras with a trigger input)

1. The camera's trigger input is wired to a sync box output pin, through a small opto-isolator if the camera needs one.
2. For each click, the box sends a trigger pulse to the camera **after the software delay**, when the film is still. The box times this itself, to the microsecond.
3. The camera takes exactly one picture per pulse. There are no in-between pictures and no calibration by eye.
4. The box reports every pulse it sent, so the software knows exactly how many pictures should arrive. Each pulse is matched to one picture or recorded as failed.

This mode is supported only for cameras whose trigger mode has been tested and listed in the setup guide. Continuous mode remains available on every camera.

### 5.6 Camera settings

- The software lists the camera's modes and prefers uncompressed ones (YUYV/NV12). Compressed modes (MJPEG) are allowed with a visible "lower quality" warning, and the mode used is recorded in the reel.
- Exposure, white balance, gain and focus are set in the Setup screen and **locked** for the scan. If a camera can't lock a setting, the Setup screen warns.

### 5.7 Two machines, one computer

- Each WorkPrinter is a **machine** in the software: one sync box (or syncmouse) plus one camera, paired in the Setup screen. Sync boxes are recognised by their built-in serial number and cameras by their USB serial number or port. Plugging them into different ports doesn't mix up the machines.
- Each machine has its **own capture process**. A problem with one machine never stops or slows the other.
- Both machines can scan at the same time. The Setup screen checks that both cameras can stream at full rate together. If the USB ports can't sustain both, it says which cable to move.

## 6. Operation

### 6.1 Starting a scan

With the machine **Ready** (camera streaming, storage space, sync box and clock sync, or syncmouse, all checked and shown green), the operator starts the WorkPrinter with its own switches. The first frame click starts a new reel and recording begins automatically.

Optionally, the operator presses **New Reel** first to enter a name, film type and notes. Otherwise the reel is named with the machine and date/time (for example `WorkPrinter 1 — 2026-10-04 14:32`) and can be renamed later.

### 6.2 While scanning

The Scan screen shows, for each machine:
- A big status: **green "Recording"**, **amber "Warning"**, or **red "Stopped — problem"**.
- The live camera picture and the last saved frame.
- Frames saved, frames failed, frames per second, feet scanned (by film type), and the resulting movie length at the chosen speed.
- Disk space, clock-sync error, and the mini PC's temperature.

### 6.3 End of reel

The frame switch keeps clicking after the film runs out (it is driven by the motor), so the **camera** detects the end:
- When the gate shows an **empty, evenly bright picture** for a set number of frames, the software finishes the reel and calls the operator: **"Reel finished — switch off WorkPrinter 1"**. Clicks after that are ignored until the next reel.
- To avoid finishing on clear leader at the start, end detection only switches on after a set number of picture frames have been captured.
- A film break looks the same and is reported the same way.
- The empty-gate frames at the end are marked and left out of the movie by default.

### 6.4 Problems

On any fault, recording for that segment stops, every saved frame is kept, and the page turns **red** with a loud alarm, a phone alert and a plain message: **"STOP WORKPRINTER 1 NOW"**, what happened and what to do. Faults:

| Fault | Examples |
|---|---|
| Camera | Unplugged, stopped sending pictures, changed mode |
| Missed frame | No picture for a click; far too long between clicks |
| Storage | Reel drive nearly full; write error |
| Sync | Lost message from the sync box; clock-sync error over the limit |
| Sync box | Unplugged or not responding |
| Mini PC health | Overheating |
| Operator | Stop pressed on the page |

**Resume:** the operator stops the WorkPrinter, fixes the problem, and winds the film back to just before the last saved frame (the page shows it for comparison). Pressing **Resume** and starting the WorkPrinter starts a new segment in the same reel. In Review, the overlap between segments is found by comparing pictures and trimmed, so no frame appears twice in the movie.

### 6.5 Alerts

- Browser: color, alarm sound and a browser notification.
- **Phone alert (optional):** push notification through a self-hosted **ntfy** server on the mini PC, for "reel finished", "problem" and "movie ready".

## 7. Storage and reliability

### 7.1 Saving frames

1. Each frame is written straight to the reel folder on the reel drive: first to a temporary file, then renamed into place, then logged in the journal.
2. Saving runs in its own worker with a fixed-size queue. A slow disk or busy web page never costs a frame. If the queue fills, that is a fault, never a silent drop.

### 7.2 Reel folder

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
- **Recovery:** after a restart, the software checks frames against the journal, keeps every complete frame and flags any half-written one. Existing frames are never overwritten.

## 8. Review and movies

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
- Before encoding, every frame in the range must exist and open. Gaps block the export and are listed.
- After encoding, the frame count and length are checked.
- Progress, cancel, Open/Download. Export again any time without rescanning.
- Optional: create an MP4 automatically when a reel finishes.
- Uses **FFmpeg**. Silent (no sound).
- Movie making runs at lower priority than capture, so it can run while a scan is in progress without costing frames.

## 9. Software

### 9.1 Structure

One repository, three parts:

| Part | Language / runs on | Does |
|---|---|---|
| **app** | **Python 3.12** (Ubuntu 24.04), mini PC | Machine registry, sync-box link and clock sync, camera (V4L2), ring buffer, frame picking, saving, journal, accounting, recovery, end-of-gate detection, web page (FastAPI + a simple browser front end), review, export (FFmpeg), alerts (ntfy) |
| **firmware** | **C (official Raspberry Pi Pico SDK)**, sync box | Switch timestamps, bounce filter, trigger pulses, time sync |
| **protocol** | Shared definition | The messages between the app and the sync box, with sequence numbers and checksums |

- **Hardware sits behind small interfaces** (sync source, camera source). Simulated versions of each, including a simulated sync box that speaks the real protocol, plug into the same interfaces for tests and a **Demo Mode**.
- Capture, saving and the web page run in separate processes with fixed-size queues, so a slow page never costs a frame.
- The firmware is kept deliberately small. Its logic (bounce filter, trigger timing, time sync) is also compiled and unit-tested on the dev server.

### 9.2 Security

- Home network only; nothing is exposed to the internet.
- **The web page uses HTTPS**, so the password is never sent in clear text on the home network. The installer creates a small local certificate authority and a certificate for the mini PC. Browsers show a one-time "trust this certificate" step, documented in the setup guide.
- The web page is protected by a password set during installation.
- The sync boxes are reachable only by USB from the mini PC, not over the network.

### 9.3 Installation

- **Mini PC:** Ubuntu 24.04 + an install script that sets up the service, FFmpeg and ntfy. It runs as a system service that starts at boot.
- **Sync box:** the firmware is published as a ready-made file. Hold the Pico's BOOTSEL button, plug it in, and it appears as a USB drive. Copy the file onto it. The install script can also do this automatically.

## 10. Testing

### 10.1 Automated (dev server, every change; run with `testrepo`)

Using the simulators:
- 1,000+ simulated frames with known numbers are saved in order, none lost or doubled, on two machines scanning at once.
- Bounce filtering; missed clicks; clicks with no picture → failed frame + fault + alarm.
- Clock sync: simulated sync box clock offset and drift converge within the limit; excess error raises a fault.
- Protocol: lost, duplicated or corrupted messages are detected as faults.
- Firmware logic (bounce filter, trigger timing, time sync) unit-tested on the dev server.
- Continuous-mode picking: at the correct delay, simulated pull-down blur frames are never chosen. Delay changes pick the expected frames. Neighbour re-picking works.
- Triggered mode: every pulse is matched to one picture or a failure.
- End of reel: an empty gate finishes the reel and alerts; clear leader at the start does not.
- Faults: camera stall, disk full, overheating, sync box unplugged, operator stop → segment ends, alarm and alert. A fault on one machine doesn't affect the other.
- Resume: overlapping frames between segments are detected and trimmed.
- Recovery after simulated crashes.
- Accounting balances for every segment.
- Movies: 1,800 frames at 18 fps = 1,800 frames and 100 s, for each of the three presets.

### 10.2 Hardware (owner's equipment)

1. **Mini PC install:** Demo Mode scan and movie.
2. **Cameras on the bench, no WorkPrinter:** both cameras live at once at full rate, focus, settings lock, test frame.
3. **Sync box, sync by hand:** tap the RCA wire; each tap = one frame; bounce filter checked; clock-sync error shown and within the limit.
4. **WorkPrinter 1, test reel:** calibrate the delay, scan at least 500 frames, and inspect every frame by eye: sharp, in order, no gaps or repeats. Check the end-of-reel alert. Watch the movie.
5. **WorkPrinter 2:** same, with its own settings.
6. **Both machines at once,** a full reel each, start to finish, with no slowdown or memory growth.
7. **Fault drill:** unplug a camera mid-scan. The alarm sounds, all earlier frames are kept, and the other machine keeps scanning. Resume after winding back; the movie has no repeated or missing frames.

The system is not called hardware-ready until steps 4–7 pass.

## 11. Delivery

- Source code on GitHub (public), with an install script, ready-made firmware file, pinned dependency versions and automated tests.
- `README.md` as the setup guide for any WorkPrinter owner: parts list, wiring pictures, installation, first scan, calibration, timing-disk reset procedure, tested cameras.
- `CHANGELOG.md` from the first release.

## 12. Build order

1. **App core, simulators, web page, export:** everything testable on the dev server.
2. **Firmware** with its logic unit-tested on the dev server, then on a real sync box (bench test 3).
3. **Cameras on the real mini PC** (bench tests 1–2).
4. **Film tests** on both machines (tests 4–7).
5. **Packaging** and the setup guide.

## 13. Not in version 1 (designed for, built later)

- **Automatic lamp and motor control** (relays wired into the WorkPrinter's own switches, for stopping by itself at the end of the reel or on a fault). Left out because it means opening and rewiring the machine, and on bulb models the switches carry wall voltage. Could be offered later as a separate, professionally installed option for owners who want it.
- HDR (several exposures per frame). Needs a controllable light and camera.
- LED light retrofit for bulb machines (steady light, less heat, no bulbs to replace; MovieStuff once sold this upgrade).
- Stepper motor conversion for exact frame-by-frame motion (the sync box could drive a stepper driver).
- 12-bit industrial (GenICam) cameras.
- Automatic frame alignment on sprocket holes, stabilization.
- Automatic color restoration, dust and scratch removal.
- Sound.
- Windows or Mac versions.

## 14. Risks

| Risk | What we do |
|---|---|
| Bulb flicker causes brightness changes between frames | Flicker-safe exposure times only; brightness of each frame logged and sudden jumps flagged in Review. |
| Software can't stop the WorkPrinter, so film runs on uncaptured after a problem | Loud alarm and phone alert; Resume after winding back; overlap trimmed automatically. |
| Two cameras share USB bandwidth | Mini PC chosen with separate USB 3 controllers; Setup screen checks both at full rate together. |
| One computer runs both machines | Each machine has its own capture process; a problem on one never affects the other. |
| Clock sync between board and mini PC drifts | Continuous sync, error shown on screen, fault over the limit. |
| Camera trigger mode doesn't work as advertised | Continuous mode works with any USB camera. |
| Camera can't lock exposure/white balance | Warn; list tested cameras in the guide. |
| Clear leader or very bright scenes look like an empty gate | End detection only after picture frames have been seen, and requires many consecutive empty frames; thresholds adjustable. |
