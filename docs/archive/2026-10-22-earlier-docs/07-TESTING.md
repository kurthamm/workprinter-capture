# Test strategy and measurable acceptance

All checks below are planned, **not executed**. Every release records which tests actually passed.

## Phase A: pure software simulation (before assembling machines)
1. Synthetic camera frames each marked with known serial number; test 1,000 simulated capture events -> exactly 1,000 ordered images without gaps or unexplained duplicates.
2. Simulate triggering at slow and fast intervals and contact bounce, press/release edges and incorrect mouse clicks. Distinguish accepted, ignored and unresolved.
3. Inject known variable sample latency and clock drift; confirm timing matcher selects designated still frame or explicitly flags no frame.
4. Simulate interlaced mixed-field movement samples; ensure not marked valid.
5. Test storage faults: full disk, interrupted encode, crash between image temp write and journal, corrupted PNG, camera disconnect, USB reconnect, queue overflow.
6. Restart and reconcile saved images/events; no overwrite or fabricated success.
7. Test frame-rate math: 1,800 frames at 18 fps -> 100 seconds native-rate video, 1,800 frames (allow container timestamp rounding).
8. Assert quiet/silent output contains **no audio track**.

## Phase B: stand-alone camera and Pico
- Enumerate actual camera and real negotiated formats, show live preview, manually capture hundreds of frames.
- Verify lens focus and locked exposure, camera output overlays absence, any interlacing.
- With Pico connected to a *verified safe* test switch/signal generator, validate sequence numbers, missed USB events, contact debounce and device-specific identity.
- Test normal Windows mouse alongside Pico without involuntary clicks.
- Confirm sustained image writes exceed physical capture rate with bounded memory.

## Phase C: WorkPrinter physical short reel
- Inspect projector first, test with noncritical/expendable leader or numbered film reference.
- Confirm exact sync contact timing relative to frame stability.
- Calibrate capture window independently for each WorkPrinter and camera mode.
- Inspect at least **500 consecutive physical frames from each machine**, checking for dropped/repeated/streaked/mixed-field/out-of-order images, not merely matching software counters.
- Reconfirm after changing video mode, lens, frame rate or connection.

## Phase D: whole reel and operations
- Capture longer than intended normal reel duration; confirm no backlog/memory growth.
- Interrupt camera, Pico, UI focus, export and storage and verify notifications/recovery behaviors.
- Confirm operator understands physical motor remains running if app stops.
- Repeat with both saved WorkPrinter profiles (not simultaneous capture).
- Export archive FFV1/MKV and viewing H.264/MP4, inspect frame order, duration, correct aspect and color, and confirm no audio stream.
- Restore backup, validate checksum, reopen and re-export without original capture modifications.

## Release acceptance
- Count invariant: accepted triggers = committed frames + pending + unresolved/failed.
- Device identification prevents silent fallback to another camera.
- Nothing recorded as complete if missing frames are unresolved.
- No unexpected frame omission/duplication proven by physical reference reel.
- Good images are stationary, uncombed, correctly framed and of negotiated genuine capture quality.
- Both profiles verified independently.
- Fully documented installer, supported OS, camera hardware list, firmware binary/source and reproducible build procedure.

## Manual checklists to prepare
Machine identity photo checklist; preflight AC power and lens focus; safe electronics measurements; capture start/stop procedure; end-of-reel procedure; archive & backup verification; incident response if film transport continues after app fault.
