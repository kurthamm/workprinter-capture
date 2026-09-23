# Decisions

Strategic decisions for the Movie Stuff project, with the reasoning and research behind them.
Recorded 2026-09-23 (first planning session). Nothing has been built yet.

---

## 1. Project goal

**Decision:** Build new capture software so the owner's two **MovieStuff WorkPrinter XP** machines can digitize 8mm film again, using a modern computer and a modern camera.

**Why:** The original software (CineCap) and the camcorder-era setup are obsolete and no longer obtainable. The WorkPrinter hardware itself still exists and will be reused as-is.

**Explicitly not wanted:** A copy of the old XP-era software with its old limits. The owner said: *"I don't want to build a stupid application and make it limited like the one from XP days."* The new software must be built around the WorkPrinter XP and modern cameras, and deliver high quality.

### 1.1 Audience: every WorkPrinter owner

**Decision (2026-09-23):** This is **the replacement for CineCap** for anyone with a MovieStuff WorkPrinter, not just the owner's two machines. The owner said: *"We need to be the replacement software for that one we used to use and helping people with the WorkPrinter."*

**Consequences:**
- The repository is public on GitHub: https://github.com/kurthamm/workprinter-capture
- **Syncmouse mode is the standard mode**, because every WorkPrinter owner already has a syncmouse. Camera-triggered mode is an optional upgrade.
- Any standard USB webcam must work (with a quality warning for compressed modes), because other owners will use whatever camera they have.
- `README.md` becomes a setup guide for any owner, with a list of tested cameras.
- Independent project; not affiliated with MovieStuff or AlternaWare. Repository named `workprinter-capture` rather than `moviestuff` for that reason.
- License: open question (MIT recommended so others can use and improve it).

---

## 2. What the system consists of

**Decision:** The complete setup is four parts:

1. **WorkPrinter XP** — already owned (two units). Stays as it is.
2. **Computer** — an ordinary Windows 11 PC or laptop with USB.
3. **Camera** — a modern USB camera, one per machine (see section 5).
4. **Software** — what this project builds. Pick the machine, press Capture, run the reel; every frame is saved; press Create Movie to get a video file.

---

## 3. Research: the original software (CineCap)

What we found about the software being replaced:

- **Maker:** AlternaWare. Windows XP program written specifically for WorkPrinter units.
- **Availability:** Only supplied to customers who bought directly from MovieStuff.
- **Versions:** CineCap, CineCap Standard 1.40, CineCap Velocity, and Velocity HD (for the WorkPrinter XP HD).
- **How it captured:** It relied on a mouse click landing on its on-screen Capture button. The operator had to click the first frame by hand to "prime" it.
- **Capture speed:** Film ran at about 3 or 6 frames per second during capture.
- **Output:** AVI files only.
- **Known weakness:** Its built-in speed-change feature (converting film rate to video rate) was designed for standard definition and degraded HD captures. Users did speed changes in VirtualDub or Premiere instead.
- **Later attempt to revive it:** On the 8mm forum in about the last year, a renewed CineCap for HD/4K was proposed at about $75, conditional on 12 buyers. No evidence it was ever released.
- **Documentation status:** MovieStuff's setup pages now return 404. The AlternaWare download site no longer resolves. RJ Nunnally's syncmouse write-up could not be reached. No original manual was found; nothing is known about CineCap's internals beyond the points above.

**Decision:** We do **not** recreate CineCap's file formats, project files, or behavior. We replace what it did and fix its weaknesses.

---

## 4. Research: how the WorkPrinter XP works

- The WorkPrinter is a **modified GAF projector**.
- A **lobed disc** on the shaft closes a **mechanical switch once per film frame**, at the moment the frame is fully displayed and still.
- That switch is wired to an **RCA jack** on the front of the unit.
- The **"syncmouse"** is an ordinary mouse with its left button wired to that RCA jack, so every switch closure is a left click.
- The original camera was a **camcorder** looking at the film through the XP's large **condenser lens**. One user described a Canon camcorder with a Raynox DCR-250 macro lens. Another replaced the XP lens with a 16mm Keystone K-160 projector lens.
- The XP's lamp already gives diffused light (built-in white reflector acts as a diffuser); the gate is already enlarged by MovieStuff.
- The camcorder era most likely meant **DV over FireWire** at 720×480 interlaced (NTSC) — not verified for the owner's units.

**What this means for the new design:**
- The mechanical switch is the key signal. It tells us exactly when each frame is still.
- Because it is a mechanical switch, **contact bounce** (one closure registering as several) must be handled.
- At 3–6 frames per second, speed and disk writing are easy. Timing (grabbing the right image) is what matters.

---

## 5. Camera

### 5.1 How the camera gets triggered

**Decision (revised 2026-09-23 after the audience decision and code review):**

- **Standard: syncmouse mode.** Continuous camera video; each syncmouse click picks the matching picture. Works with any camera and every WorkPrinter owner already has the syncmouse. Every click is accounted for as one saved frame or one recorded failure.
- **Optional upgrade: camera-triggered mode.** Wire the XP's frame switch (the RCA jack) into the camera's trigger input, so the camera takes exactly one picture per frame while the film is still. No timing calibration and no blurred in-between images.

**Why camera-triggered is not the standard:** a standard USB camera gives the software no trigger count, so a trigger the camera misses can't be proven missing. The software flags suspicious gaps in frame timing as "possible missed frame", but only syncmouse mode can guarantee every frame is accounted for. It is also an extra wiring job other owners may not want.

### 5.2 How much resolution 8mm film actually has

- A Super 8 frame is about 5.8 × 4.0 mm; Regular 8 is smaller (about 4.5 × 3.3 mm).
- Home-movie lenses and film stock recorded roughly the detail of **1,000–1,500 pixels across the frame**.
- Beyond about **2,000 pixels across**, a camera records film grain more sharply, not more picture.
- **Sweet spot: a 2–5 megapixel camera** (1,900–2,500 pixels wide). That covers the frame, the edges and the sprocket holes with room to spare. 12 MP or 4K adds nothing real on 8mm.

### 5.3 What matters more than megapixels

1. **Lens quality** — a cheap lens is soft at any resolution. This is where money should go.
2. **Uncompressed frames** — many cheap USB cameras compress every frame (MJPEG), adding blocky artifacts. The camera must deliver uncompressed images. Easy at 3–6 frames per second.
3. **Global shutter + trigger input** — the whole image is exposed at once, at the right moment. No rolling-shutter smear.
4. **Bit depth** — 10–12-bit output (instead of 8-bit) lets faded color and dark scenes be recovered without banding. This is the main thing a more expensive camera buys.

### 5.4 Cameras considered

| Camera | Approx. price | Notes |
|---|---|---|
| **ELP AR0234 global shutter USB** | Under $100 (not confirmed) | 1920×1200 color, global shutter, external trigger, standard USB webcam (UVC), no drivers. "Close-up varifocal" version focuses at short range. 8-bit. |
| **Arducam OV9782 global shutter USB** | About $100 (Newegg listing) | 1280×800 color, global shutter, external trigger. Cheaper, lower resolution. Only 10 fps uncompressed at full resolution, which is still enough. |
| **Basler ace 2 a2A2448-75ucBAS** | About $600+ | 5 MP, Sony IMX547, global shutter, 12-bit, opto-isolated trigger, USB3. First recommendation; the owner rejected it as more than needed. |
| Mirrorless / DSLR | — | Rejected. Tethered stills are slow and wear the mechanical shutter; HDMI streaming brings back the timing problem. |
| Webcam / Raspberry Pi HQ camera | — | Rejected as primary. Rolling shutter, no proper trigger input. |
| Existing camcorders | — | Rejected. DV-era video quality. |

**Decision (current):**
- Budget tier, about $100 (ELP AR0234): enough resolution, 8-bit color. Fine for normal film, less room to rescue faded or dark reels.
- Mid tier, about $300–600 (industrial 3–5 MP camera): same useful resolution, plus 12-bit color and a proper lens mount. The "no regrets" choice.
- Above $600: not worth it for 8mm.
- **Plan:** buy one ELP camera first, test a reel on one XP. If colors and shadows look good, buy a second. If faded reels look poor, upgrade to a 12-bit industrial camera.
- The owner stated: *"I don't want a low quality setup. If I need to buy a $600 camera, I will."* Quality comes first; spending is fine where it buys visible quality.

**Software decision that follows:** The software must not be tied to one camera brand. Version 1 supports standard USB webcams (UVC) only. Industrial cameras through the GenICam standard (Basler, Hikrobot, Daheng, FLIR, Allied Vision) are **not in version 1**; camera access sits behind an interface so an adapter can be added later. If the owner upgrades to a 12-bit industrial camera, that adapter becomes the next piece of work.

### 5.5 Lens

- For an industrial camera: a used 50 mm enlarger lens (Schneider Componon-S or El-Nikkor), reversed on extension tubes with a C-mount adapter, set near 1:1. Common, sharp and inexpensive for 8mm scanning.
- For the ELP: the close-up varifocal version, or an inexpensive M12/CS-mount macro lens.
- Either way, the new camera and lens replace the XP's original condenser-lens-plus-camcorder arrangement.

---

## 6. The owner's own research document

The owner supplied `WorkPrinter_Windows_Requirements_v2.md` (Revision 2.0, 2026-09-23): 61 numbered requirements and acceptance tests for a Windows replacement.

**Kept from that document:**
- Windows 11 x64 desktop application, fully local (no internet, account or subscription).
- Separate saved profiles for WorkPrinter 1 and WorkPrinter 2; one machine at a time.
- Continuous live preview, focus zoom, manual test frame.
- One saved numbered image per frame, saved as it goes, with a capture log (journal).
- Accounting rule: accepted triggers = saved frames + pending + failed. No silent reuse of an old image.
- Recovery after interruption; never overwrite existing frames.
- Review, rotate/flip, crop and frame range without changing the originals.
- Create Movie: MP4/H.264 via FFmpeg at 16, 18, 24 fps or custom; one film frame per video frame; export again without rescanning.
- Clear warnings that stopping the software does not stop the projector motor.
- Simulated camera and trigger for testing before the hardware is set up.
- Deliver source code, build instructions and dependency versions so the software can't become unusable the way CineCap did.
- Proposed stack: C# / WPF / .NET 10, Media Foundation for camera input, Windows Raw Input for the syncmouse, FFmpeg for movies.

**Changed from that document:**
- Syncmouse mode stays the standard (as in the document); **camera-triggered mode is added** as an optional upgrade.
- **Archival export is in version 1:** FFV1 (lossless, MKV) and ProRes 422 HQ (MOV) presets alongside MP4/H.264. The document deferred these; the owner wants a modern, non-limited application and FFmpeg makes them cheap.
- **16-bit PNG** is saved when a camera delivers more than 8 bits.
- **Compressed camera modes (MJPEG)** are accepted with a visible quality warning, because other owners' webcams may only offer that at full resolution.
- Still not in version 1: multiple exposures per frame (HDR), industrial (GenICam) cameras, automatic frame alignment using sprocket holes.

---

## 7. Confidence and risks

**Confidence in building the software: high.** CineCap's job — wait for the frame signal, grab a picture, save it, repeat, make a movie — is simple by today's standards. Every step is covered by existing tools (FFmpeg for movies; modern camera and Windows APIs for capture). The work is careful integration, not invention.

**Can't be guaranteed until tested with the real equipment:**
- The chosen camera's trigger input actually working as advertised (fallback: syncmouse).
- The wiring from the XP switch to the camera (simple, but must be done once and checked).
- Windows testing: development happens on a Linux server. Most of the software can be built and tested there; the final check must happen on the owner's Windows PC with the camera and XP connected.

**Development approach because of the Linux server:** split the code into a platform-neutral core (trigger handling, frame selection, capture log, recovery, movie export — fully testable on Linux) and Windows-only parts (camera input, Raw Input, the user interface — compiled on Linux, run and tested on Windows).

---

## 8. Open questions

1. **XP optics:** Does the owner's XP still have its projection lens and the condenser lens the camcorder pointed at? Decides how the new camera mounts.
2. **Camera purchase:** Confirm starting with one ELP AR0234 for testing.
3. **Windows PC:** Which PC will run it, and how the owner will test builds on it.
4. **License:** MIT recommended, so other WorkPrinter owners can use and improve it.

---

## 9. Next steps

1. Owner reviews the version 1 spec: `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md`.
2. Write the step-by-step implementation plan.
3. Build the software against a simulated camera and trigger.
4. Test on the owner's Windows PC with a webcam.
5. Connect the real camera and XP; test one reel on each machine.

---

## 10. Sources

- [Worthpoint: MovieStuff Workprinter-XP listing](https://www.worthpoint.com/worthopedia/moviestuff-workprinter-xp-8mm-film-704200282)
- [RJ Nunnally: Workprinter XP Syncmouse](https://www.rjnunnally.com/moviestuff-workprinter-xp-syncmouse/)
- [8mm Forum: Workprinter XP Modifications](https://ft-forum.com/8mm/vbb/forum/film-to-digital-conversion/438-workprinter-xp-modifications)
- [8mm Forum: New software for WorkPrinter owners](https://ft-forum.com/8mm/vbb/forum/film-to-digital-conversion/98416-new-software-for-workprinter-and-diy-scanner-owners)
- [AlternaWare download page (offline)](https://jeffdod.tripod.com/alternaware/download.html)
- [CineCap Velocity (Software Informer)](https://cinecap-velocity.software.informer.com/)
- [CineCap Standard (Software Informer)](https://cinecap-standard.software.informer.com/)
- [VideoHelp: 8mm frame-by-frame editing](https://forum.videohelp.com/threads/294921-POSSIBLE-Captured-8mm-Movie-Frame-by-Frame-Editing)
- [MovieStuff XP RGB setup (now 404)](https://www.moviestuff.tv/set_up_xp_rgb.html)
- [Basler a2A2448-75ucBAS](https://www.baslerweb.com/en/shop/a2a2448-75ucbas/)
- [Edmund Optics: a2A2448-75ucBAS](https://www.edmundoptics.com/p/basler-ace2-a2a2448-75ucbas-color-usb3-basic-camera/56309/)
- [ELP AR0234 global shutter USB camera](https://www.elpcctv.com/elp-2mp-ar0234-sensor-1200p-1080p-90fps-global-shutter-usb-camera-p-388.html)
- [ELP AR0234 close-up varifocal (Amazon)](https://amazon.com/ELP-Computer-Lightburn-Variable-Close-up/dp/B0CXDS8F6Q)
- [Arducam OV9782 global shutter USB](https://www.arducam.com/100fps-global-shutter-color-usb-camera-board-1mp-ov9782-uvc-webcam-module-with-low-distortion-m12-lens-without-microphones-for-computer-laptop-android-device-and-raspberry-pi-arducam.html)
- [Arducam OV9782 external trigger notes](https://docs.arducam.com/UVC-Camera/Appilcation-Note/External-Trigger-Mode/OV9782-Global-Shutter/)
- [Newegg: Arducam OV9782 ($99.99)](https://www.newegg.com/p/3C6-038N-01VG2)
- [Kinograph forum: DIY 8mm scanner build](https://forums.kinograph.cc/t/8mm-film-scanner-my-build/2574)
- [Kinograph forum: Pi HQ camera build](https://forums.kinograph.cc/t/my-8mm-super8-scanner-build-in-progress-led-help/2545)
