# WorkPrinter Capture — Design Spec (Version 1)

**Date:** 2026-09-23
**Status:** Draft for owner review
**Background:** `DECISIONS.md` (research and decisions), `WorkPrinter_Windows_Requirements_v2.md` (owner's requirements; this spec keeps its intent and replaces its capture approach where noted).

---

## 1. What it is

**The replacement for CineCap**, for anyone who owns a MovieStuff WorkPrinter. It is built and tested first on the owner's two WorkPrinter XPs, and published free on GitHub so other WorkPrinter owners can use it with the syncmouse they already have. It is an independent project, not affiliated with MovieStuff or AlternaWare.

A Windows 11 program that turns a WorkPrinter, a modern USB camera and a PC into an 8mm film scanner.

The operator picks a machine, presses **Capture**, and runs the reel on the WorkPrinter. The software saves one full-quality picture for every film frame. When the reel is done, the operator presses **Create Movie** and gets a video file at the chosen speed.

Everything runs on the PC. No internet, account or subscription.

## 2. Goals

1. **Every frame, once, in order.** No lost frames, no doubled frames, and if something does go wrong the software says so — it never hides it.
2. **Full quality.** Full camera resolution, lossless saved pictures. No DV-era limits.
3. **Simple to operate.** No command lines, no manual assembly of images in a video editor.
4. **Never lose work.** Frames are saved as they arrive; a crash or power cut loses at most the frame being written.
5. **Works with what WorkPrinter owners have.** Any WorkPrinter that signals frames through the syncmouse, and any USB camera Windows recognizes as a standard webcam (UVC). Trigger-capable cameras are an optional upgrade.
6. **Maintainable forever.** Open source on GitHub, with build instructions and pinned versions, so it can't disappear the way CineCap did.

### Camera input contract

- The software lists every mode the camera offers and **prefers uncompressed modes** (YUY2, NV12, RGB).
- **Compressed modes (MJPEG) are allowed** because many ordinary webcams only reach full resolution that way. When one is selected the Setup and Capture screens show a visible "compressed camera mode — lower quality" warning, and the mode is recorded in `reel.json`.
- The negotiated resolution, frame rate and pixel format are always shown and recorded.
- Cameras that Windows does not present as a standard webcam (UVC), including industrial GenICam cameras, are not supported in version 1.

## 3. How capture works

The WorkPrinter closes a switch once per frame, when the frame is still in the gate. That switch is on the RCA jack on the front of the machine. The software supports two ways of using it.

### 3.1 Syncmouse mode (standard)

This is how CineCap worked, and what every WorkPrinter owner already has. It works with any supported USB camera. It is the default mode.

- The camera streams video continuously into a short buffer (about 1 second).
- The syncmouse click marks the moment the frame is still.
- The software picks the camera picture that matches the click, using a **timing offset** set per machine.
- A **calibration screen** shows the pictures around several clicks side by side; the operator picks the sharp one and the offset is saved.
- The software listens only to the chosen syncmouse (identified in a setup step). The ordinary mouse never adds frames. One click = one frame; button release and contact bounce are filtered.
- If no suitable picture exists for a click, that frame is recorded as **failed** and the operator is told. The previous picture is never reused.
- Every accepted click is reconciled to exactly one saved picture or one recorded failure.

### 3.2 Camera-triggered mode (optional upgrade)

For owners who wire the RCA switch to a camera's trigger input. The camera is put in external-trigger mode, so it takes **one picture only when the switch closes** and sends nothing otherwise. The software saves every picture that arrives as one film frame.

- No timing calibration is needed, and no blurred frames between film advances.
- **Limitation:** the software only sees the pictures that arrive. A standard USB camera gives no trigger count, so a trigger the camera misses cannot be proven missing. The software therefore:
  - **Flags gaps:** the WorkPrinter runs at a steady rate, so when the time between two frames is more than 1.5× the recent average (adjustable), the software records a **possible missed frame** in the journal, marks it on the Capture screen and lists it in Review.
  - **Warns on stalls:** no frames for a set time (default 2 seconds, adjustable) while armed shows a warning.
  - States on the Setup screen that this mode relies on the camera's reliability, and recommends syncmouse mode for anyone who needs a guaranteed frame count.
- Supported only for cameras whose trigger mode has been tested and listed in `README.md`.

### 3.3 Camera settings

Auto exposure, auto white balance and auto focus cause flicker and drift between frames. When capture starts, the software **locks exposure, white balance and focus** at the values the operator set during preview, and records them. If a camera does not allow these to be locked, the software warns.

## 4. Operator workflow and screens

1. **Start screen:** choose WorkPrinter 1 or WorkPrinter 2 (renameable profiles), open an existing reel or start a new one (name, notes, film type Super 8 / Regular 8, playback speed).
2. **Setup screen:** live picture with zoom-in for focusing, framing guide, camera settings (exposure, white balance, focus), capture mode (syncmouse or camera-triggered), **Test Frame** button.
3. **Capture screen:** big **ARMED / STOPPED** status, live picture, last saved frame, counts (frames saved, failed), frames per second, running movie length at the chosen speed, disk space left.
   - Keyboard controls: **Space** = arm/stop, **Esc** = stop.
   - While armed, mouse clicks on the capture screen are ignored, so the syncmouse cannot press the capture screen's buttons.
   - **If the capture window loses focus while armed** (another program or window comes to the front), the software immediately stops accepting triggers and enters the fault state. The syncmouse's clicks may then land in whatever window is in front — Windows offers no way to block one mouse system-wide — so the operator must stop the WorkPrinter or unplug the syncmouse. The fault screen stays up, ignoring mouse clicks, until the operator presses a key to confirm the WorkPrinter is stopped.
   - On any fault the screen turns red and says: **"STOP THE WORKPRINTER — the software has stopped capturing."** The software cannot stop the motor.
   - **Resume** starts a new segment, after the operator confirms the film position.
4. **Review screen:** step through frames, jump to a frame number, full-size view. Set rotation/flip, crop, and first/last frame for the movie. Originals are never changed.
5. **Create Movie:** choose speed (16, 18, 24 fps or custom) and format; progress bar, cancel, then **Open Movie / Open Folder**.

## 5. Saved files

Each reel is a folder under a capture location the operator chooses (default `Documents\WorkPrinter Reels`), never inside the program folder:

```text
Grandpa 1962 Reel 3/
  reel.json          reel name, notes, machine profile, camera + settings used, playback speed, crop/rotation
  journal.jsonl      one line per event: frame saved, frame failed, trigger rejected, fault, segment start/stop
  frames/
    000001.png
    000002.png
  exports/
    Grandpa 1962 Reel 3 - 18fps.mp4
```

- **Pictures:** PNG, lossless, at full camera resolution. 8-bit per color for 8-bit cameras; 16-bit PNG when a camera delivers more than 8 bits.
- **Safe writing:** each picture is written to a temporary file, then renamed into place, then logged in the journal. Existing frames are never overwritten.
- **Accounting rule:** frames requested = frames saved + frames pending + frames failed. It must balance at the end of every segment.
- **Recovery:** when a reel is reopened, the software checks frames against the journal, keeps every complete frame, and flags any half-written one.
- **Disk space:** warns when space runs low, stops with a clear fault if a write fails.

## 6. Movie creation

Uses **FFmpeg** (bundled with the program — no separate install).

| Preset | Use |
|---|---|
| **MP4 (H.264)** | Everyday viewing, sharing, TVs, phones. Default. |
| **Archival (FFV1 in MKV)** | Lossless master copy for long-term keeping. |
| **Editing (ProRes 422 HQ in MOV)** | For editing in Premiere, DaVinci Resolve, Final Cut. |

All three presets are in version 1. They use the same bundled FFmpeg and the same frame checks; only the encoder settings differ. Each is covered by the export tests in section 8. This deliberately goes beyond the owner's original requirements document (which deferred archival formats), to avoid CineCap's single-format limit.

- One film frame = one video frame. Speed choices: 16, 18, 24 fps or custom. Movie length = frames ÷ speed (1,800 frames at 18 fps = 100 seconds).
- No frame blending, no conversion to 30 fps, no added frames.
- Crop, rotation and frame range from the Review screen are applied; originals untouched.
- Before encoding, the software checks every frame in the range exists and opens. Gaps block the export and are listed.
- After encoding, the software checks the movie's frame count and length match.
- Export again at any speed or format without rescanning.
- Silent. No sound.

## 7. Software structure

Written in **C# on .NET 10**, Windows desktop UI with **WPF**. Built on the Linux dev server; runs on Windows 11 x64.

| Part | What it does | Runs/tested where |
|---|---|---|
| **Core** | Reels, journal, frame saving, accounting, recovery, trigger filtering, frame matching (syncmouse mode), stall detection, export checks, FFmpeg control | Linux automated tests + Windows |
| **Simulator** | Pretend camera (numbered test frames, with "moving film" blur between frames) and pretend triggers (steady, bouncy, missing, bursts) | Linux tests + a Demo Mode in the app |
| **Camera** | USB camera access (list cameras, modes, stream frames, trigger mode, lock exposure/white balance/focus) | Windows (tested on owner's PC) |
| **Syncmouse input** | Tells mice apart, listens only to the chosen one | Windows (tested on owner's PC) |
| **App** | The screens | Windows (tested on owner's PC) |

- Core never depends on Camera, Syncmouse input or App; they plug into Core through small interfaces. The Simulator plugs into the same interfaces, which is how Core is tested without hardware.
- Camera access is replaceable: an industrial (GenICam) camera adapter can be added later without touching Core.
- Capture, saving and screen updates run separately, so a slow screen never costs a frame. Buffers have fixed limits.
- PC is kept awake during capture and export.

## 8. Testing

1. **Automated tests (Linux, every change):** 1,000+ simulated frames saved in order with none lost or doubled; bounce and wrong-mouse filtering; missing-picture faults; camera-triggered gap flagging; stall warnings; focus-loss fault; crash recovery; disk-full faults; movie frame count and length (1,800 frames at 18 fps = 100 s) for each of the three export presets. Run with `testrepo`.
2. **Windows build check (Linux, every change):** the Windows program must build.
3. **Owner's PC, no camera:** install, Demo Mode, capture a simulated reel, create a movie, play it.
4. **Owner's PC, camera only:** live picture, focus, settings lock, Test Frame, movie.
5. **Camera + trigger by hand:** each tap of the trigger wire = exactly one saved frame.
6. **WorkPrinter 1, test reel:** at least 500 consecutive frames checked by eye — sharp, in order, no gaps or repeats. Watch the movie.
7. **WorkPrinter 2:** same test with its own profile.
8. **Full reel:** start to finish with no slowdown or growing memory.

The software is not called hardware-ready until steps 6–8 pass.

## 9. Delivery

- A zip containing a self-contained Windows program (no .NET install needed) with FFmpeg included and its license notice. Unzip and run.
- Source code in a git repository, with build instructions and pinned versions of .NET, libraries and FFmpeg.
- A short operating guide in `README.md`, written for any WorkPrinter owner: what to buy, how to connect the syncmouse and camera, and a list of cameras tested so far.
- Published as a GitHub release on the public repository.

## 10. Not in version 1

Kept out to get a working scanner first. The saved full-quality frames mean all of these can be applied later without rescanning:

- Multiple exposures per frame (HDR)
- Industrial (GenICam) camera support — Camera access sits behind an interface, so an adapter can be added later; no GenICam code, tests or packaging in version 1
- Automatic frame alignment using sprocket holes, stabilization
- Color correction, dust and scratch removal
- Sound
- Running both machines at the same time
- Motor or lamp control

## 11. Risks

| Risk | What we do |
|---|---|
| The chosen camera's trigger mode doesn't work as advertised on Windows | Syncmouse mode is the standard anyway; test trigger mode on the first camera before buying the second. |
| A camera can't lock exposure/white balance | Warn; pick a camera that can. |
| The syncmouse hardware no longer works | Use camera-triggered mode, or wire a replacement mouse to the RCA jack. |
| Other owners' WorkPrinter models behave differently | The software only relies on "one click per frame", which is common to mouse-triggered WorkPrinters; issues reported on GitHub get fixed. |
| Windows-only parts can't be run on the dev server | Keep them thin; test on owner's PC at steps 3–5. |
