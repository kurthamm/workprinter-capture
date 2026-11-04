# Functional and nonfunctional requirements

Requirements are proposed and **not yet implemented**. Identifiers are intended for traceability.

## Device and project setup
- **FR-001** Enumerate supported video devices with stable identities, negotiated pixel mode, actual resolution and framerate.
- **FR-002** Enumerate Pico serial ports and optional Raw Input mice; identify selected trigger source explicitly.
- **FR-003** Maintain two separate WorkPrinter machine profiles with per-device camera, trigger, calibration and export settings.
- **FR-004** Never silently switch camera or trigger to another device after disconnection.
- **FR-005** Open/new/reopen reel projects with unique non-overwriting identifiers, names and optional notes.
- **FR-006** Show live video preview, actual negotiated resolution/mode and current device status.
- **FR-007** Manual capture independently of hardware trigger for setup.
- **FR-008** Focus zoom and framing guides without destructive alteration.
- **FR-009** Expose focus, exposure and white balance settings only when supported by capture hardware.

## Capture
- **FR-010** Camera acquisition runs continuously, independently from GUI rendering.
- **FR-011** Arm capture explicitly; disarmed triggers never create reel images.
- **FR-012** Pico edge event produces no more than one capture request; duplicate/repeated edge handling configurable and logged.
- **FR-013** Optionally identify mouse source with Raw Input; one configured button edge per physical cycle.
- **FR-014** Source selection and mouse safety must prevent ordinary UI actions from triggering film capture.
- **FR-015** Retain short, bounded, timestamped camera sample history.
- **FR-016** Apply device-specific, operator-calibrated stationary-film interval to pick correct sample.
- **FR-017** Support earlier-buffered and later-arriving samples; document and reconcile device clock domains.
- **FR-018** Detect incomplete/mixed-field images when source interlaced; do not treat them as valid film frames.
- **FR-019** Mark missing/unusable frames unresolved and notify operator; never quietly reuse last frame.
- **FR-020** Persist one numbered source image per successful accepted trigger without modifying original image content.
- **FR-021** Journal every trigger's disposition and map to camera sample and saved file.
- **FR-022** Show total accepted triggers, persisted images, pending requests, unresolved events, queue pressure and effective film duration.
- **FR-023** Controlled stop/disarm; hardware transport operation cannot be implied by software state.
- **FR-024** Fault visibly on camera disconnect, trigger disconnect, disk failure, exhausted space, timing loss and sustained overload.
- **FR-025** Resumption requires an explicit film-position decision and an additional segment rather than claiming lossless continuity.
- **FR-026** Record source camera format, color metadata, frame timing and settings for each session.
- **FR-027** Reject events outside supported performance bounds with truthful diagnostics, not fabricated success.

## Image review and editing
- **FR-028** Frame-by-frame review at captured resolution, stepping and random seeking.
- **FR-029** Nondestructive crop, rotate, flip, color/exposure settings for export.
- **FR-030** Select export in/out frame range without deleting preserved captures.
- **FR-031** Preserve pixel aspect ratio and document color/interlace transformations.
- **FR-032** Never silently interpolate, denoise, sharpen, scale, blend or delete similar frames.

## Persistence and recovery
- **FR-033** Numbered lossless original frames in a project folder, not just a transient video container.
- **FR-034** Asynchronous bounded writer with temporary files and durable journal.
- **FR-035** Restart recovery reconciles complete frames, orphan temp files and pending events.
- **FR-036** No overwrite of originals during capture, restart, re-export or interrupted export.
- **FR-037** Validate missing numbers, corrupt images and unresolved capture events before movie production.

## Export
- **FR-038** Editable playback speed presets: 16, 18, 24 fps and custom rational rate.
- **FR-039** Playback speed is independent from acquisition cadence and camera live-video rate.
- **FR-040** Create silent **FFV1 v3/Matroska** preservation video, with recorded frame count and conversion details.
- **FR-041** Create silent H.264/MP4 viewing copy with user-selectable quality and compatible pixel aspect/color settings.
- **FR-042** FFmpeg integration reports progress, stderr diagnostics, cancellation, outputs and frame count validation.
- **FR-043** User can re-export from untouched master frames at another speed without rescanning.
- **FR-044** No soundtrack, audio capture or silent filler track required.
- **FR-045** Preserve project-level export settings and provenance.

## Software quality and distribution
- **NFR-001** Windows 11 x64, .NET 10 LTS, WPF/MVVM, C# with nullable analysis and compiler warnings.
- **NFR-002** Deterministic state machine and testable abstractions around camera, trigger, storage and export.
- **NFR-003** UI remains responsive during capture, compression and encoding.
- **NFR-004** Bounded queues and sustained output at measured WorkPrinter trigger rate.
- **NFR-005** Alert promptly for data loss, failed writes, device/time discontinuity and limited disk space.
- **NFR-006** Offline, local-first; no subscription or activation.
- **NFR-007** Versioned settings, capture journal and Pico USB protocol.
- **NFR-008** No elevation required for normal operation where device backend permits.
- **NFR-009** Unit tests, integration tests, simulator, automated builds and documented operating instructions.
- **NFR-010** Build from source with pinned dependencies; package a normal Windows installer and record FFmpeg distribution/licensing obligations.
- **NFR-011** Avoid claiming archival capture quality greater than source camera optics, digitizer bitrate and color depth.
- **NFR-012** Operate safely with a powered/unknown external sync signal only through verified appropriate isolation/protection.

## Out of scope for first release
Audio, live motor driving, simultaneous two-WorkPrinter operation, AI restoration, stabilization, scratch removal, cloud storage, silent frame interpolation, automated film-splice repair, licensing service and original CineCap binary compatibility.

## Acceptance criteria
See [testing plan](07-TESTING.md) for measurable tests. These requirements are the complete proposed baseline; they remain open to revision after real hardware identification.
