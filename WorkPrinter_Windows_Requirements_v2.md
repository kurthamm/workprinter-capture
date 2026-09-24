# WorkPrinter Capture for Windows
## Version 1 requirements and acceptance checklist

**Owner:** Kurt Hamm  
**Revision:** 2.0, September 23, 2026  
**Status:** Ready to begin implementation. This is a proposed independent replacement specification, not a recovered CineCap specification. No replacement executable or hardware test results are delivered with this document.

## 1. Objective and agreed context

Return the owner's two existing mouse-triggered WorkPrinters to useful service. The owner believes the machines are WorkPrinter XP models; exact model labels, camera models, connectors, drivers, and current operating condition remain unverified.

The intended workflow is: continuously receive the camera's live video; accept the WorkPrinter's synchronization event through its modified mouse; select one camera image corresponding to a stationary film frame; save successive images; create a complete movie at a user-selected playback speed. The application does not advance the film, operate the projector motor, or issue still-photograph shutter commands to the camera.

This revision builds on `WorkPrinter_Windows_Rebuild_Spec.md` in this conversation. That earlier document is a design draft, not independent proof that any hardware works. Previously identified manufacturer pages were not successfully reloaded during this revision, so no additional model-specific behavior is inferred from them.

**Ready now:** software implementation, simulated input tests, frame storage, review, and movie export.  
**Requires the equipment later:** actual camera/driver compatibility, modified-mouse identification, synchronization calibration, and physical-film acceptance tests.

## 2. Proposed first-release decisions

| Decision | Baseline |
|---|---|
| Operating system | Windows 11 x64. Confirm the particular PC before final deployment. |
| Application | A local desktop application; no cloud service, subscription, account, or Internet connection for capture/export. |
| Equipment | Reuse the existing machines, cameras, and synchronization mice wherever their interfaces work. Do not prescribe replacements before testing. |
| Concurrent operation | One active WorkPrinter per application session. Save independent profiles for both machines. Simultaneous capture is outside version 1. |
| Capture storage | Preserve numbered, losslessly encoded images of the decoded capture pixels, with session metadata and a capture journal. PNG is the initial format for the supported RGB workflow. |
| Finished movie | MP4 with H.264 as the first delivery preset; validate the selected encoder and actual playback. Keep the capture images separately. |
| Playback speed | Editable presets of 16, 18, and 24 fps plus a custom positive rational rate. These are user choices, not automatically inferred reel speeds. |
| Sound | Silent output. Do not record camera microphone or projector noise. Film soundtrack transfer is a separate future feature. |
| Operator controls | Simple foreground capture screen; keyboard controls while hardware-trigger mode is active. |

These are proposed build defaults. A different camera input backend, actual input format, and throughput envelope may be selected after hardware identification without changing the core workflow.

## 3. User workflow

Select a machine profile and create a reel. Select or confirm the camera and trigger device. Check live preview, focus, framing, and timing. Arm the software, then operate the WorkPrinter using its existing physical controls. Observe capture status. Stop the physical transport and sync, then finish capture. Review the saved frames, choose playback speed, and press **Create Movie**. Open the resulting video.

The app must not require the operator to assemble images manually in a video editor or run FFmpeg commands. An optional automatic-export-after-finish setting may invoke the same validated export workflow.

## 4. Required software behavior

All requirements below apply to version 1 unless labeled **Conditional**. Conditional means necessary when that equipment or format is actually used, not an obligation to support every legacy device.

### A. Platform, installation, and ownership

| ID | Requirement |
|---|---|
| A01 | Run as a normal Windows 11 x64 desktop application. Normal capture and export must not require administrator privileges. Separate hardware driver installation may have different requirements. |
| A02 | Capture, save, review, and export locally without an account, subscription, network connection, or activation server. Do not upload images or logs automatically. |
| A03 | Deliver a runnable release package with required application dependencies and a tested encoder configuration, plus source code, build instructions, automated tests, dependency versions, and relevant third-party notices. |
| A04 | Keep capture data outside installation files. Updating or removing the application must not delete reels. Document which runtime and encoder builds were packaged. |

Proposed implementation: C# and WPF on .NET 10. WPF is Microsoft's Windows desktop UI framework; .NET 10 is listed as an active LTS release in Microsoft's support policy. These facts support the platform choice, not compatibility with untested capture devices. [S1, S2]

### B. Machine profiles and reel projects

| ID | Requirement |
|---|---|
| B01 | Provide independent, renameable profiles initially named WorkPrinter 1 and WorkPrinter 2. Store camera selection/mode, trigger selection/edge, timing, and framing preferences separately. |
| B02 | Verify devices when a profile loads. Never silently replace an absent device with the first available camera or mouse. Re-identification is required when identities or connections are ambiguous. |
| B03 | Create a unique reel/session folder with a name, optional notes, film-type label, playback rate, and a snapshot of the configuration actually used. The film-type label must not imply the app physically changes the gate or knows the original shooting speed. |
| B04 | Reopen existing reels for inspection and export without connecting the WorkPrinter. Recognize incomplete sessions and preserve existing data. Version the session metadata format. |

### C. Camera input and preview

| ID | Requirement |
|---|---|
| C01 | List compatible video sources by useful names and diagnostic identities. Enumerate supported modes and display the actual negotiated resolution, camera frame rate, and image format. |
| C02 | Continuously show live video, with a focus inspection/zoom view and framing guide. Clearly distinguish live preview from the most recently saved frame. |
| C03 | Provide a manual single-frame test before hardware-trigger capture. Save the real source sample, not a screenshot of a resized preview window. |
| C04 | Record pixel aspect ratio, color interpretation, pixel format, bit depth, and interlace information when available. Require a visible override or report unknown metadata rather than silently guessing a critical setting. |
| C05 | Expose focus, exposure, shutter, and white-balance controls only when the device supports them. Otherwise direct the operator to the camera's physical controls. Do not promise remote control of every camera. |
| C06 | Report camera-busy, access-denied, unsupported-format, disconnect, and stopped-stream conditions clearly. Do not count new captures from a stale displayed image. |
| C07 | **Conditional:** Support the owner's actual camera/capture chain through a verified Windows driver and input adapter. A USB/UVC path can be used for development, but FireWire/DV, analog capture hardware, or a proprietary card requires its own compatibility proof. Never assume that an old 32-bit driver works in an x64 application. |

Media Foundation provides video-device enumeration and a Source Reader for media samples. Use it as the initial compatible-device backend, not as a promise of universal legacy hardware support. Keep the input adapter replaceable within the application. [S3]

### D. Modified-mouse triggers

| ID | Requirement |
|---|---|
| D01 | Include an Identify Trigger mode that shows which input device produced an event. Save and verify the selected device before arming. |
| D02 | In hardware mode, accept input only from the selected trigger source. Ordinary-mouse activity or the other WorkPrinter must not generate capture requests. |
| D03 | Accept exactly one configured button edge per trigger cycle. A button press and release must not create two frames. Ignore pointer movement and double-click UI interpretation. |
| D04 | Ignore capture triggers until armed. Clear stale pending input when starting a new segment and record events rejected while disarmed or filtered. |
| D05 | Provide a configurable contact-bounce filter. Calibrate it against observed intervals, log suppressed events, and do not select a fixed interval that silently removes valid fast triggers. |
| D06 | Assign each accepted trigger a unique ID and monotonic host-observation timestamp. Distinguish the observation time from the physical switch closure, which is not directly measured. |

Windows Raw Input can distinguish separate mice. Registration and device identity must be handled explicitly; do not store an ephemeral device handle as the only persistent identifier. [S4]

### E. Frame selection and synchronization

| ID | Requirement |
|---|---|
| E01 | Acquire video continuously into a bounded recent-frame buffer, independent of preview rendering and storage. Retain or copy buffers safely so driver reuse cannot overwrite queued images. |
| E02 | Provide adjustable trigger-to-video timing and a calibration view showing candidate images around several trigger events. Save the chosen stable interval per camera/machine configuration. |
| E03 | Associate each accepted trigger with at most one distinct source sample from the calibrated stationary-film interval. Selection may require an earlier buffered sample or waiting for a later arriving sample. Do not assume newest always means correct. |
| E04 | Align camera timestamps and host trigger timestamps explicitly. Track discontinuities or drift; invalidate timing after device, video-mode, or relevant pipeline changes. |
| E05 | If no valid sample arrives in time, record a failed/unresolved request and fault the session. Never silently reuse the previous saved frame or declare success using a stale sample. |
| E06 | **Conditional:** For interlaced input, validate field order and ensure both fields represent the same stationary film image before treating them as one intact frame. Any deinterlacing or other conversion must be explicit and tested. Do not silently discard half the vertical information. |
| E07 | Do not automatically remove visually similar images. Genuine adjacent film frames may be similar; image similarity cannot establish a skipped film advance. Physical correspondence requires a known test strip or human sequence inspection. |

Media Foundation sample callbacks expose timestamps, sample data, errors, and stream-gap indications. Their timestamp units alone do not establish a shared clock with mouse events. Microsoft documents interlace metadata and field handling separately. [S5, S6]

### F. Capture controls and operator interaction

| ID | Requirement |
|---|---|
| F01 | Provide visible states: Preview, Armed/Capturing, Finishing, Stopped, Fault, and Exporting. Arm only after a valid destination, working video source, selected trigger, and applicable timing setup are present. |
| F02 | Provide keyboard actions to arm and stop capture. Keep an accessible stop action available during capture, finish, and fault handling. Do not make software Stop appear to be a motor stop. |
| F03 | While hardware-trigger capture is active, prevent its ordinary mouse clicks from activating app controls or dialogs. Use a protected foreground screen and keyboard operation for version 1. Do not depend on the pointer remaining over a Capture button. |
| F04 | On focus loss, device loss, or capture fault, stop accepting new capture requests and show a conspicuous instruction to stop the physical transport/sync. Maintain appropriate click protection in the foreground fault/finish screen until the operator can disable sync. Do not promise system-wide click isolation. |
| F05 | Finish or fail all already accepted requests explicitly when stopping. A request that cannot be resolved must not disappear from accounting. |
| F06 | Resume only through an explicit new capture segment and operator confirmation of film position. If film kept moving while software was stopped, do not imply seamless continuation. Never advance or rewind the film in software. |

Raw Input source identification is not a system-wide per-device click blocker. Microsoft describes NOLEGACY suppression in the registered application and separate foreground behavior flags. Test the exact guard behavior on Windows; advise the operator to stop or disable physical sync before switching applications. [S7]

### G. Capture storage and recovery

| ID | Requirement |
|---|---|
| G01 | Preserve one numbered image file per successfully committed capture. Use PNG for the initial supported decoded RGB path; use an appropriate lossless encoding if another supported pixel format requires it. Document any decode/color conversion. This is not a claim to preserve sensor-raw data or undo upstream camera compression. |
| G02 | Keep reel metadata, capture images, capture-event journal, and exported movies separate within the reel folder. Use stable numeric sequencing and unique segment identifiers. |
| G03 | Write a temporary image, finalize it without overwriting an existing capture, then record a successful commit. Reconcile partial images and journal/file mismatches after restart. |
| G04 | Log trigger ID, segment, source sample ID, relevant timestamps, selected timing, file name, and result. Keep rejected inputs separate from accepted-trigger accounting. |
| G05 | Detect inadequate disk space or write errors, warn before the configured reserve is exhausted, and fault visibly when storage cannot keep up. Preserve committed files; do not promise to stop the physical machine. |
| G06 | Use bounded queues. After interruption, retain verified committed frames and identify incomplete final writes. Do not claim immunity from power loss or arbitrary filesystem damage. |

Required accounting invariant:

**Accepted triggers = committed frames + pending requests + failed/unresolved requests.**

Matching counters prove software accounting, not one-to-one correspondence with the physical film. At successful completion, pending and unresolved counts must be zero for the range being exported as complete.

Suggested structure:

```text
Reel_Name/
  session.json
  events.jsonl
  frames/
    frame_000000001.png
    frame_000000002.png
  exports/
    Reel_Name_18fps.mp4
```

### H. Review and image interpretation

| ID | Requirement |
|---|---|
| H01 | Open saved frames, step forward/backward, jump to a frame number, and inspect at capture resolution. Show associated capture errors or timing information when requested. |
| H02 | Support nondestructive rotation/flip and an export crop rectangle. Preserve uncropped capture images and save transformations as settings. |
| H03 | Preserve the intended display aspect ratio, including non-square source pixels where applicable. Do not stretch every image to widescreen. |
| H04 | Allow an explicit start/end frame range for export. Do not delete excluded frames. Version 1 need not include a multitrack timeline, editing, grading, or automatic restoration. |

### I. Movie creation

| ID | Requirement |
|---|---|
| I01 | Provide a Create Movie action that assembles the selected valid capture range in order into a complete MP4/H.264 file. The application manages the encoder; the user does not manually import images or type commands. |
| I02 | Offer 16, 18, 24 fps and a custom positive rational playback rate. Keep film playback rate, camera video rate, and mechanical scan rate separate. Do not infer playback rate solely from film type. |
| I03 | In native-rate export, represent each selected captured film image as one output video frame. Do not use capture elapsed time or image-file modification times for movie timing. |
| I04 | Validate sequence continuity, image readability, dimensions, and unresolved events before encoding. Block a supposedly complete export containing unresolved gaps; allow the user to choose an intact range instead. |
| I05 | Apply only explicitly selected crop, orientation, aspect-ratio, or delivery settings. Do not silently interpolate motion, blend neighboring film frames, change speed, or introduce frame dropping. |
| I06 | Show export progress, allow cancellation without altering captured images, protect existing exports, report encoder errors, and finalize the output only after success. Retain a settings summary and validate output duration/frame count. |
| I07 | Allow export again at another speed or quality without rescanning. Provide an Open Movie/Open Folder action. Validate playback in the user's actual target player. |

For an intact native-rate export:

**Movie duration in seconds = included film-frame count / selected playback fps.**

Example: 1,800 frames / 18 fps = 100 seconds. Scan duration is irrelevant to that calculation.

FFmpeg's image-sequence input supports explicitly supplied frame rate and sequentially numbered files. The application must set the rate rather than rely on the encoder's default. Pin and test the actual encoder build and command configuration. [S8]

### J. Reliability, status, and diagnostic information

| ID | Requirement |
|---|---|
| J01 | Keep the main screen simple: live view, last saved frame, accepted-trigger count, saved-frame count, pending/failed count, measured scan rate, resulting movie duration, and remaining storage. Put detailed timestamps and queue statistics in a diagnostic view. |
| J02 | Keep video acquisition, frame selection, and writing independent of UI rendering. A slow or dropped preview refresh must not drop a required saved film frame. |
| J03 | Sustain the measured maximum operating trigger rate on the chosen PC, input mode, and storage. Determine the supported envelope by measurement; do not invent a universal CPU, RAM, or capture-rate requirement. Verify bounded memory and queue growth over sustained runs. |
| J04 | Recognize no-video, stale-sample, input-disconnect, queue-overflow, storage-failure, and encoder-failure conditions. A trigger timeout may warn that capture stopped; it must not be treated as proof that the reel ended normally. |
| J05 | Request prevention of automatic idle sleep during capture/export and release that request afterward. Do not disable security updates, bypass screen locks, or promise protection against shutdown or power loss. |
| J06 | Export a human-readable diagnostic summary containing application/dependency versions, device/mode details, timing settings, counts, and errors. Keep it local unless the operator chooses to share it. |

### K. Testing without assembled WorkPrinters

| ID | Requirement |
|---|---|
| K01 | Include a generated or prerecorded video source with known frame identities and simulated film transitions. Clearly label test footage so it cannot be confused with real film. |
| K02 | Support manual button/keyboard testing and internal simulated trigger events. An ordinary selected mouse may exercise the device-input path; simulated events alone do not validate the real modified mouse. |
| K03 | Test trigger press/release filtering, wrong-device rejection, bounce handling, timing offsets, missing samples, source resets, disk errors, and export settings without projector hardware. |
| K04 | Keep automated test results separate from hardware acceptance. A webcam or simulated-source pass is not evidence that the owner's original camera/driver works. |

## 5. Acceptance tests

The counts below are proposed minimum test sizes, not claims of completed tests or proof against every future fault.

| Test | Pass criterion |
|---|---|
| Deterministic capture | At least 1,000 simulated film-frame triggers produce the expected 1,000 identified images in order with zero unexplained duplicates or omissions. |
| Trigger edges | Repeated down/up cycles produce one accepted request per intended cycle; wrong-device events produce none. |
| Timing | Synthetic transition frames are not selected; offset changes choose the expected samples. Missing candidates fault explicitly rather than duplicating a previous sample. |
| Image fidelity | Saved dimensions and orientation match the configured acquisition pipeline; recorded pixel/aspect/color handling is verified with reference images. |
| Recovery | Induced interruption preserves verified earlier captures, flags incomplete files, reconciles the journal, and never overwrites existing images. |
| Fault handling | Camera/input removal, stalled samples, write failure, full disk simulation, focus loss, and encoder failure produce visible actionable status with no false success. |
| Movie export | An intact 1,800-frame reference export at 18 fps has 1,800 video frames and a 100-second media duration, subject only to stated container time-base rounding; actual playback is checked. |
| WorkPrinter 1 | A reference or expendable test reel yields at least 500 consecutive visually verified physical film frames, in order, with no unexplained capture-introduced blur, mixed fields, duplicates, or missing frames. Source-film blur must be distinguished from capture errors. |
| WorkPrinter 2 | The same physical test passes independently with its own profile and calibration. |
| Sustained operation | Capture runs for at least one intended full-reel duration at the validated operating rate with no growing backlog or unbounded memory. Test a higher simulated load for margin, recording the measured limits. |
| Usability | The operator can reopen the reel and create/play the movie without a terminal, external video editor, or manual image assembly. |

Only a visible-numbered or otherwise independently inspectable physical test establishes correspondence between triggers and film advances. Counters and software logs alone do not.

## 6. Hardware checks needed later

| Unknown | What is needed | What it decides |
|---|---|---|
| Exact machines | Model labels and identification of installed synchronization arrangement | Which model-specific operating instructions apply. |
| Camera source | Camera model and the live-video output actually used | The input signal format and any camera operating settings. |
| PC connection | USB, FireWire/DV, capture-box/card information and installed drivers | Whether the initial Media Foundation path works or another backend is required. |
| Trigger connection | Computer-end mouse plug and recognition by Windows | Whether the current sync input can be used directly. |
| Operating video | Actual negotiated resolution/rate, progressive/interlaced form, latency, and timestamp behavior | The supported acquisition mode and calibration. |
| Throughput | Actual trigger rate and sustained disk-write performance | Buffer settings, storage requirements, and validated operating envelope. |
| Reel playback | Desired playback rate for each reel | Movie timing; this does not prevent building the rate selector now. |

None of these requires assembling both machines before implementing the app. They do prevent claiming final compatibility before equipment testing.

## 7. Not part of version 1

AI restoration, scratch removal, stabilization, automatic color grading, HDR/multi-exposure capture, optical-flow interpolation, automatic film-speed detection, sound-stripe transfer, multitrack editing, cloud backup/accounts, simultaneous two-machine capture, automatic rewind/motor/lamp control, custom hardware drivers, and CineCap binary/project-file compatibility are outside the baseline.

AVI/MOV or an additional archival-video export preset may be added later. The initial master is the preserved image sequence with metadata. No new camera, capture card, mouse, or projector is a prerequisite purchase until the existing chain is inspected.

## 8. Build order

**First:** One working vertical slice using test video or a compatible webcam and an ordinary selected mouse: preview, one-image capture, numbered storage, and one-button movie export.

**Second:** Add the hardware-use essentials: selected-device trigger processing, timing calibration, machine profiles, protected capture controls, journals, recovery, and failure tests.

**Third:** Connect and validate each original camera/WorkPrinter combination independently; adapt the video backend only when actual equipment requires it.

**Finally:** Full-reel tests, playback verification, a runnable Windows release, and source/build documentation. Do not label the app hardware-validated until those tests have actually passed.

## 9. Primary technical references

References below support Windows and encoder capabilities, not proof of the owner's particular hardware. Checked September 23, 2026. The functional requirements above are proposed design decisions.

- **S1. Microsoft, WPF overview:** https://learn.microsoft.com/en-us/dotnet/desktop/wpf/overview/
- **S2. Microsoft, .NET support policy:** https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core
- **S3. Microsoft, Audio/Video Capture in Media Foundation:** https://learn.microsoft.com/en-us/windows/win32/medfound/audio-video-capture-in-media-foundation
- **S4. Microsoft, Raw Input Overview:** https://learn.microsoft.com/en-us/windows/win32/inputdev/about-raw-input
- **S5. Microsoft, IMFSourceReaderCallback::OnReadSample:** https://learn.microsoft.com/en-us/windows/win32/api/mfreadwrite/nf-mfreadwrite-imfsourcereadercallback-onreadsample
- **S6. Microsoft, Video Interlacing:** https://learn.microsoft.com/en-us/windows/win32/medfound/video-interlacing
- **S7. Microsoft, RAWINPUTDEVICE:** https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-rawinputdevice
- **S8. FFmpeg, Formats Documentation, image2:** https://ffmpeg.org/ffmpeg-formats.html#image2
