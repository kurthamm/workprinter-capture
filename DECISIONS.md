# Decisions

Strategic decisions for the Movie Stuff project, with the reasoning and research behind them.
Recorded 2026-09-23 (first planning session). Nothing has been built yet.

> **Current design (read this first):** WorkPrinter XP + **one mini PC** for both machines + a **USB camera** and a small **USB control board (Raspberry Pi Pico 2)** on each machine, operated from a web browser. See section 10 and the spec `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md`. Earlier sections record how the thinking got there; where they mention Windows, a Raspberry Pi 5 per machine, or the syncmouse as the standard, section 10 supersedes them.

---

## 1. Project goal

**Decision:** Build new capture software so the owner's two **MovieStuff WorkPrinter XP** machines can digitize 8mm film again, using a modern computer and a modern camera.

**Why:** The original software (CineCap) and the camcorder-era setup are obsolete and no longer obtainable. The WorkPrinter hardware itself still exists and will be reused as-is.

**Explicitly not wanted:** A copy of the old XP-era software with its old limits. The owner said: *"I don't want to build a stupid application and make it limited like the one from XP days."* The new software must be built around the WorkPrinter XP and modern cameras, and deliver high quality.

### 1.1 Audience: every WorkPrinter owner

**Decision (2026-09-23):** This is **the replacement for CineCap** for anyone with a MovieStuff WorkPrinter, not just the owner's two machines. The owner said: *"We need to be the replacement software for that one we used to use and helping people with the WorkPrinter."*

**Consequences:**
- The repository is public on GitHub: https://github.com/kurthamm/workprinter-capture
- ~~Syncmouse mode is the standard mode~~ — superseded by section 10: a control board reads the WorkPrinter's sync socket directly; an existing syncmouse plugged into the mini PC remains a supported no-wiring alternative.
- Any standard USB webcam must work (with a quality warning for compressed modes), because other owners will use whatever camera they have.
- `README.md` becomes a setup guide for any owner, with a list of tested cameras.
- Independent project; not affiliated with MovieStuff or AlternaWare. Repository named `workprinter-capture` rather than `moviestuff` for that reason.
- License: open question (MIT recommended so others can use and improve it).

---

## 2. What the system consists of

**Original decision (superseded by section 10):** WorkPrinter XP + Windows 11 PC + USB camera + software.

**Current decision:** WorkPrinter XP (unchanged except removable relay wiring) + **USB control board (Pico 2) and USB camera per WorkPrinter** + **one mini PC** for both + the software, operated from a web browser. Details in section 10.

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
- **Documentation status:** MovieStuff's live setup pages return 404 and the AlternaWare site no longer resolves, but **the original MovieStuff pages are preserved on the Wayback Machine** (see section 3.1). No CineCap manual from AlternaWare itself was found.

**Decision:** We do **not** recreate CineCap's file formats, project files, or behavior. We replace what it did and fix its weaknesses.

### 3.1 Wayback Machine findings (original MovieStuff instructions)

Found 2026-09-23 via the Wayback Machine index of moviestuff.tv. Key pages: `set_up_xp_rgb.html` (WorkPrinter-XP RGB setup), `set_up_xphd_mouse.html` (XP HD with syncmouse), `set_up_xphd_velocity.html`, `explain.html` ("How the damned thing works"), `cinecap_read.html`, `velocity_box.html`, `set_up_velocity_box.html`, `velocity_instructions.html`, `velocity_hd_instructions.html`, `read_wpxp.html`. Content is © Roger Evans; summarized here, not copied into the repository.

**Original products and prices**
- WorkPrinter-XP: $1,595, built to order from rebuilt projectors; "each may change slightly from unit to unit but all should work the same."
- CineCap: $70, sold by AlternaWare only to WorkPrinter customers via a private link. Mac equivalent: **CaptureMate**.
- Later: **Velocity / Velocity-HD** software (also branded "CineCap Velocity") and the **Velocity Box** ($199).

**The WorkPrinter XP's controls — the "control" that made it all work together**
- **Control box** with the **RCA sync jack** on the back (the syncmouse cable plugs in here).
- **Sync switch** (on/off; a three-position selector on the XP HD, middle = off). It turns the frame signal to the computer on and off, separately from the motor.
- **Motor switch** and a **control knob**: off/stop, project/play/forward, rewind.
- **Framer knob** (vertical framing; only works while film advances) and **focus lever** (used only to correct barrel/pincushion distortion — focusing is done with the camera).
- **Light:** on the XP RGB, an LED light with **R, G, B and M (master) sliders** on the control panel to set color and exposure, plus a **remote** for exposure. On the XP HD, an LED with a **preset intensity knob**. Older units had an AC bulb (flicker and banding with fast shutter speeds); MovieStuff offered an upgrade to a steady LED and a DC motor.
- **Timing disk** inside the back, between the motor and the LED assembly: a black cam, held by an Allen set screw, that closes the **microswitch** once per frame.

**Why the timing disk existed**
- DV camcorders took about **1/3 second** to deliver each picture to the computer, but the mouse click arrived instantly.
- The timing disk was rotated to **delay the click mechanically** so it reached the computer together with the right picture. Every camera and computer combination needed its own setting, found by trial and error (move in half-inch steps, capture, look for "vertical pulldown blur", repeat).
- For the Velocity Box (units shipped after January 2009), the disk was preset so the switch clicks **exactly when the claw reaches the bottom of the pulldown** — the moment the frame lands in the gate. Marks: a black line on the large white pulley and a white line on the timing disk.
- **Implication:** the owner's XPs may have their timing disks set for an old camcorder's delay, not for the moment the frame is still. Any new setup must either reset the disk to the claw-bottom position or compensate in software.

**How CineCap was operated**
- Syncmouse must be the only mouse. Click the first frame manually, leave the pointer over the Capture button, start the motor, then turn on the sync switch. Stop: sync switch off first, then motor.
- Required a PC with three internal drives (system + two in RAID-0), parallel ATA preferred; otherwise sync was lost. Maximum about **8 frames per second**.
- Camera: 36–42 inches from the condenser lens, 14× zoom or better, manual shutter at least 1/60 (1/500 for CMOS cameras), no auto shutter or steady-shot, **white balance locked**. The image is mirror-reversed, so **horizontal flip** was required.
- Pulldown blur is always visible during capture; playback must be clean.

**How Velocity worked (the later, better design)**
- Streaming instead of stop-motion: the camera video is recorded continuously while the **Velocity Box converts each switch closure into an audio sync pulse** recorded alongside the video (via a Canopus ADVC converter for SD, or a BlackMagic Intensity Pro card for HD).
- Afterwards, the software **finds the pulses and harvests the matching frames**. If there is blur, the **sync offset is changed in software and the file reprocessed — no recapture needed.**
- Features: Settings tab (folders, unit type "V-Box + WorkPrinter", flip, codec, NTSC/PAL, blended or progressive frames, pulse threshold, dead-pixel mask, watermark); Capture tab (customer name with automatic `_0001` numbering, film type for a footage counter, **Keep / Throw** after each capture); Speed Change tab (speed preview, several output speeds per capture, a true 1:1 "24P" option); **numbered image sequences** in JPG/PNG/BMP/TIF (65,000 frames per folder); Play tab showing total length in feet or meters; optional PC shutdown after processing.
- Limits: 32-bit Windows XP/Vista/7 only, English (US) regional settings required, a dedicated 7200 RPM drive, DV AVI output.

**WorkPrinter XP models and generations** (from `wp_xp_rgb.html`, `wp_hd.html`, `workprinter_guide.html`, `read_upgrade_wp.html`, `faq_print2.html`, `remote.html`)
- **Older XP:** original tungsten bulb, **lamp and motor push buttons on the center chassis**, runs on 110 VAC (transformer needed abroad).
- **Newer XP:** LED light source, high-torque DC motor, **vertical toggle switches for lamp, motor and synch on the rear plastic cover**, runs on 100–256 VAC. MovieStuff offered to upgrade older units (refurb + DC motor + LED, $350).
- **XP RGB** ($2,395): RGB LED light with R/G/B/M sliders on a control box; sync RCA jack on the back of that control box.
- **XP HD** ($2,195; +$35 for syncmouse): LED with a panel preset knob; **Velocity circuit built in** (sync pulses on LEFT and RIGHT RCA audio outputs, no timing disk needed with Velocity); a switch halves the capture rate for slow systems.
- **Sync connection:** on the plain XP, a "synch socket" on the side of the projector near the back, next to a switch marked "synch"; on the RGB and HD, the RCA jack on the back of the control box. A provided cable connects it to the syncmouse. The sync plug is **RCA ("phono")**, confirmed.
- **Common to all XPs:** about 8 frames per second scanning, sprocketless drive, 400 ft capacity, enlarged gate showing 100% of the frame, jumbo 5-inch condenser lens, camera images the emulsion side, no shutter (true frame-by-frame), silent only.
- **LED colour:** the LED is daylight-balanced; MovieStuff suggested an 85B filter if a camera couldn't white-balance to it.
- **Remote (early WorkPrinter, 2003 page):** single-frame advance, auto run, independent lamp control, always stops with the current frame in the gate, and a "remote trigger" jack for timing devices. Not confirmed for the XP; the XP RGB page mentions a remote for exposure only.
- **Not found in any archived page:** whether the motor or light connect to the control box through phono plugs.

**What this means for the new design**
1. The **timing disk becomes a software setting** where possible: the new system measures the switch timing and applies an adjustable delay, instead of opening the machine with an Allen wrench. Where the camera is triggered directly, the disk should be reset to the claw-bottom position (the Velocity Box procedure).
2. **Keep Velocity's best idea:** record the trigger timing so the frame selection can be re-done in software without rescanning.
3. Keep the sync switch as the operator's on/off for frame signals, and keep the "sync off first, then motor" habit.
4. Carry over the useful Velocity features: Keep/Throw, automatic reel naming, footage counter by film type, several speeds per reel, image sequences, flip.
5. Record whether the owner's XPs have the RGB LED, a preset-knob LED, or the older AC bulb (affects flicker at fast shutter speeds).

---

## 4. Research: how the WorkPrinter XP works

- The WorkPrinter is a **modified GAF projector**.
- A **lobed disc** (the "timing disk") on the shaft closes a **mechanical microswitch once per film frame**. Where in the frame cycle it closes depends on how the timing disk was set (see section 3.1).
- That switch is wired to an **RCA jack** on the back of the WorkPrinter control box, through the sync switch.
- The **"syncmouse"** is an ordinary mouse with its left button wired to that RCA jack, so every switch closure is a left click.
- The original camera was a **camcorder** looking at the film through the XP's large **condenser lens**. One user described a Canon camcorder with a Raynox DCR-250 macro lens. Another replaced the XP lens with a 16mm Keystone K-160 projector lens.
- The XP's lamp already gives diffused light (built-in white reflector acts as a diffuser); the gate is already enlarged by MovieStuff.
- The camcorder era most likely meant **DV over FireWire** at 720×480 interlaced (NTSC) — not verified for the owner's units.

**What this means for the new design:**
- The mechanical switch is the key signal. It marks each frame; with the timing disk at the claw-bottom position (or a software delay), it marks when each frame is still.
- Because it is a mechanical switch, **contact bounce** (one closure registering as several) must be handled.
- At 3–6 frames per second, speed and disk writing are easy. Timing (grabbing the right image) is what matters.

---

## 5. Camera

### 5.1 How frames are signalled and captured

**Decision (final, 2026-09-23; history below).** Two separate choices, with fixed names used in the spec, the code and the tests:

**Sync input — where the frame click comes from:**
- **Direct sync (standard):** the WorkPrinter's RCA sync socket wired to the control board's input pin (section 10.5). The board timestamps every switch closure.
- **USB syncmouse (alternative, no wiring):** an existing syncmouse plugged into the mini PC; the software listens only to its left button. PS/2 syncmice need an active PS/2-to-USB converter.

**Capture mode — how the picture for each click is obtained:**
- **Continuous mode (standard):** the camera streams continuously; for each click the software picks the picture at click time + the per-machine software delay. Works with any USB camera.
- **Triggered mode (upgrade):** the camera's trigger input is wired to a **control board output pin**, never directly to the WorkPrinter switch. For each click the board sends one trigger pulse after the per-machine software delay, when the film is still, and matches each pulse to one picture or a recorded failure.

Either way every click is accounted for as one saved frame or one recorded failure.

**History:** earlier drafts made "syncmouse mode" the standard (Windows design) and proposed wiring the switch directly to the camera's trigger. Both were replaced: the control board reads the switch itself, and triggering goes through the board so the software delay applies (the timing disk may still be set for an old camcorder) and every trigger is counted.

### 5.2 How much resolution 8mm film actually has

- A Super 8 frame is about 5.8 × 4.0 mm; Regular 8 is smaller (about 4.5 × 3.3 mm).
- Home-movie lenses and film stock recorded roughly the detail of **1,000–1,500 pixels across the frame**.
- Beyond about **2,000 pixels across**, a camera records film grain more sharply, not more picture.
- **Sweet spot: a 2–5 megapixel camera** (1,900–2,500 pixels wide). That covers the frame, the edges and the sprocket holes with room to spare. 12 MP or 4K adds nothing real on 8mm.

### 5.3 What matters more than megapixels

1. **Lens quality** — a cheap lens is soft at any resolution. This is where money should go.
2. **Uncompressed frames preferred** — many cheap USB cameras compress every frame (MJPEG), adding blocky artifacts. Uncompressed modes are preferred; MJPEG is accepted with a visible quality warning and the mode used is recorded. Uncompressed is easy at 3–6 frames per second.
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
- **Platform:** Windows 11 / C# / WPF replaced by one Linux mini PC with a USB control board per machine, Python, web page (section 10). Windows-specific requirements (Raw Input, Media Foundation, click protection on a desktop window, "software can't stop the motor") no longer apply.
- **Sync:** read directly from the WorkPrinter by the control board; syncmouse becomes an alternative. **Triggered-camera mode** added, with the board sending the trigger.
- **Projector control added:** the control board switches lamp and motor through relays and stops the machine on any fault or at the end of the reel.
- **Archival export is in version 1:** FFV1 (lossless, MKV) and ProRes 422 HQ (MOV) presets alongside MP4/H.264. The document deferred these; the owner wants a modern, non-limited application and FFmpeg makes them cheap.
- **16-bit PNG** is saved when a camera delivers more than 8 bits.
- **Compressed camera modes (MJPEG)** are accepted with a visible quality warning, because other owners' webcams may only offer that at full resolution.
- Still not in version 1: multiple exposures per frame (HDR), industrial (GenICam) cameras, automatic frame alignment using sprocket holes.

---

## 7. Confidence and risks

**Confidence in building the software: high.** CineCap's job — wait for the frame signal, grab a picture, save it, repeat, make a movie — is simple by today's standards. Every step is covered by existing tools (FFmpeg for movies; modern camera and Windows APIs for capture). The work is careful integration, not invention.

**Can't be guaranteed until tested with the real equipment:**
- The chosen camera's trigger input actually working as advertised (fallback: continuous mode).
- The relay wiring for lamp and motor, which depends on the owner's XP model (needs photos/inspection).
- How precisely the DC motor can stop with a frame in the gate.

**Development approach:** the dev server runs Linux, like the mini PC. Everything is developed and tested here against a simulated camera and a simulated control board; only the physical connections need the owner's equipment. (The earlier Windows plan needed the owner's PC for most testing; this is a major reason the Linux design is easier to build and verify.)

---

## 8. Open questions

1. **Which XP model the owner has** (owner, 2026-09-23: *"I think both of my units have bulbs"*, so likely the older type; photos to confirm): push buttons in the middle (older), three toggle switches on the back (newer), a control box with R/G/B/M sliders (RGB), or a single light knob (HD). Photos of the switch panel and inside the back cover decide the relay wiring.
2. **XP optics:** whether the projection lens and condenser lens are still fitted. Decides how the new camera mounts.
3. **Timing disk position** on the owner's machines (set for an old camcorder, or at the claw-bottom mark).
4. **Camera purchase:** start with one ELP AR0234; confirm its trigger mode works.
5. **Mini PC choice:** specific model within the spec (8+ cores, 32 GB RAM, hardware video encoding, at least two USB 3 ports on separate controllers).
6. **License:** MIT recommended, so other WorkPrinter owners can use and improve it.

---

## 9. Next steps

1. Owner reviews the version 1 spec (revision 3, one mini PC + control boards): `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md`.
2. Write the step-by-step implementation plan.
3. Build the app core, simulators, web page and export on the dev server; write and unit-test the control board firmware.
4. Owner buys parts (section 10.4); bench-test the mini PC with both cameras and a control box.
5. Owner sends photos of the WorkPrinter; design and install relay wiring.
6. Film tests on both machines.

---

## 10. Platform: one mini PC + USB control boards (current design)

### 10.1 How we got here (2026-09-23)

1. Started with the owner's Windows requirements document and a Windows 11 PC design.
2. The owner asked whether a Raspberry Pi could do it. Key realization: **the Pi has input pins that can read the WorkPrinter's frame switch directly**, so the syncmouse, the "mouse click lands on a button" fragility and the timing guesswork all go away, and every frame can be counted for certain.
3. The owner asked: *"Do I need a Windows machine or just a Raspberry Pi?"* Decision: **no Windows machine.**
4. The owner wants the **best solution**, not a minimal one: *"Why would I start small. I want the best solution!"* and *"I want to upgrade the living shit out of this hardware."*
5. The owner wants **the Pi to control the projector.** A whole-machine power switch was proposed and rightly rejected by the owner as crude (it kills the light, stops the film mid-motion). Decision: the Pi controls the **lamp and motor through relays wired alongside the WorkPrinter's own switches**, and stops with a frame in the gate.
6. The owner's operating idea: *"I set everything up and I start the 8mm projector and it starts the mouse stuff and someone knows that everything is working."* Decision: a scan can start **either from the web page or just by starting the projector**; the system detects the first frame click and records automatically, shows live status, and alarms on problems. An "Arm" button was dropped as confusing.
7. Concern that the Pi is too weak: capture and control are easy for a Pi 5; **movie creation is slow** on it (no hardware video encoder; 30–45 minutes for a 400 ft reel) and future HDR would be heavy. The owner chose **"mini PC and full Pi"** — not a microcontroller (Pico) — *"Quit being cheap!"*
8. Correction recorded: the frame switch keeps clicking after the film runs out (it is driven by the motor), so **end of reel is detected by the camera seeing an empty gate**, not by the clicks stopping.
9. **Pi per machine dropped (revision 3).** The owner asked: *"Why do I need a mini PC and a Raspberry Pi?!"* Nothing required both. The Pi-per-machine split assumed each machine had to run on its own and be networked. With both WorkPrinters in the same room (*"of course they would be in the same room!"*), one mini PC can run both cameras directly. Decision: **one mini PC** for everything, plus a **Raspberry Pi Pico 2 control board per machine** on USB for the frame switch, relays and camera trigger.
   - This is **not a cost cut**, and it doesn't reverse item 7. There, the Pico was offered as a cheaper replacement for the whole Pi. Here it does only the jobs that need exact timing. A microcontroller timestamps switch closures and times stops and triggers to the microsecond, more precisely than any computer running a full operating system. It also keeps working (safety stop) if the mini PC hangs.
   - Gains: one computer instead of three, no networking between machines, no frame spool or copying, fewer parts to buy and maintain.
   - Costs, and how they're handled: the Pico's clock must be synced to the mini PC's (continuous sync, error shown, fault over the limit). Two cameras share one computer's USB (mini PC with separate USB 3 controllers; checked in Setup). One computer runs both machines (separate capture process per machine; the Pico's heartbeat safety stop).
   - Owner's syncmouse has the old round PS/2 plug. It isn't needed; the RCA cable goes straight from the WorkPrinter to the control box.

### 10.2 The design in one paragraph

One mini PC runs both WorkPrinters. Each WorkPrinter has a USB camera and a small USB control box (Raspberry Pi Pico 2 with relays), both plugged into the mini PC. The control box reads the frame switch from the WorkPrinter's RCA sync socket with microsecond timestamps, switches the lamp and motor, and fires the camera trigger in triggered mode. The mini PC captures one picture per frame (picked from a continuous stream by a software delay, or by triggering the camera), saves it to the reel drive, makes movies with FFmpeg and serves the web page used from any phone, tablet or laptop. If the mini PC stops responding, the control box stops the projector by itself.

### 10.3 Why this is better than CineCap's design

| CineCap era | New design |
|---|---|
| Projector clicks a modified mouse; mouse pointer must sit over a button | Control board reads the switch directly; nothing to aim |
| Timing disk adjusted inside the machine with an Allen wrench, by trial and error | Software delay chosen on a calibration screen, from side-by-side pictures |
| DV camcorder, 720×480 interlaced, AVI | Modern camera, full resolution, lossless frames, MP4/FFV1/ProRes |
| Three-drive RAID PC running Windows XP | One mini PC, ordinary SSDs, Linux |
| Software couldn't stop the projector | Motor stops on any fault and at the end of the reel |
| Nobody knows a frame was missed | Every click accounted for; alarm and phone alert |
| Proprietary, sold only via a private link | Free and open on GitHub |

### 10.4 Parts list

**Per WorkPrinter:**

| Part | Notes |
|---|---|
| Raspberry Pi Pico 2 H | Headers already fitted; no soldering |
| Pico screw-terminal breakout board + small case | The "control box" |
| USB cable for the Pico (Micro-USB to USB-A or USB-C) | Control box to mini PC, up to 5 m |
| RCA cable male–male (about 6 ft) | WorkPrinter sync socket to the adapter |
| RCA female to screw-terminal adapter | Search "RCA female to screw terminal" |
| Opto-isolated relay module, 2+ channels, 3.3 V logic compatible | Lamp and motor; exact choice after inspecting the machine (voltage/current) |
| USB 3 global-shutter camera (baseline ELP AR0234) + macro/close-up lens | Mount designed after inspecting the machine |
| USB 3 cable, or active USB 3 extension if over about 3 m | Camera to mini PC |

**One for both machines:**

| Part | Notes |
|---|---|
| Mini PC, 8+ cores (Ryzen 7 / Core Ultra class), 32 GB RAM, 1 TB NVMe, hardware video encoding, at least two USB 3 (10 Gbps) ports on separate controllers | Runs everything |
| 4 TB+ SSD for reels | About 120 GB per 400 ft reel of frames |
| Monitor, keyboard, mouse (optional) | Or use any phone, tablet or laptop |

### 10.5 Wiring summary

- **Sync:** WorkPrinter RCA sync socket → RCA cable → RCA-to-screw adapter → control board input pin and ground (pins fixed in the setup guide). Internal pull-up; switch closed = low.
- **Relays:** in series with the WorkPrinter's own lamp and motor switches (WorkPrinter switch on = enabled, relay = run/stop), so either can stop the machine and it can be undone. Designed after photos; mains-voltage wiring only by someone qualified.
- **Triggered camera (optional):** a control board output pin → camera trigger input (through an opto-isolator if the camera needs one); the board fires it after the software delay.
- **USB:** each camera and each control box plugs into the mini PC.

---

## 11. Sources

- [Wayback: WorkPrinter-XP RGB setup](https://web.archive.org/web/2020/http://www.moviestuff.tv/set_up_xp_rgb.html)
- [Wayback: WorkPrinter-XP HD setup (syncmouse)](https://web.archive.org/web/2020/http://www.moviestuff.tv/set_up_xphd_mouse.html)
- [Wayback: WorkPrinter-XP HD setup (Velocity)](https://web.archive.org/web/2020/http://www.moviestuff.tv/set_up_xphd_velocity.html)
- [Wayback: How the WorkPrinter works](https://web.archive.org/web/2020/http://www.moviestuff.tv/explain.html)
- [Wayback: What is CineCap?](https://web.archive.org/web/2020/http://www.moviestuff.tv/cinecap_read.html)
- [Wayback: Velocity Box](https://web.archive.org/web/2020/http://www.moviestuff.tv/velocity_box.html)
- [Wayback: Velocity Box setup (timing disk)](https://web.archive.org/web/2020/http://www.moviestuff.tv/set_up_velocity_box.html)
- [Wayback: Velocity software instructions](https://web.archive.org/web/2020/http://www.moviestuff.tv/velocity_instructions.html)
- [Wayback: Velocity-HD software instructions](https://web.archive.org/web/2020/http://www.moviestuff.tv/velocity_hd_instructions.html)
- [Wayback: WorkPrinter-XP order page](https://web.archive.org/web/2020/http://www.moviestuff.tv/read_wpxp.html)
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
