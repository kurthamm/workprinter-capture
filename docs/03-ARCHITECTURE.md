# Software architecture and detailed design

## Technology decisions (proposed)
- **C# / .NET 10 LTS / WPF XAML with MVVM**. Separate application UI from capture services.
- Native **Windows Media Foundation** for supported capture devices; interface-based capture backend abstraction allows a verified legacy adapter in future.
- **Win32 Raw Input** optional fallback for modified mouse; **USB CDC serial** primary connection to Pico 2 H.
- **C/C++ Pico SDK** firmware; edge detection, configurable debounce, monotonic sequence numbering.
- **FFmpeg** command-line subprocess for media packaging and output, no hand-written codec.
- Session metadata and project profiles stored in versioned **JSON**; append-only **JSONL journal** for events; source images initially lossless **PNG** when correctly matched to decoded pixel format.
- Build and distribution should not require Python or an IDE on the end-user PC.

## Modules and explicit boundaries
1. **App/UI**: Device selectors, previews, profiles, reel management, capture controls, progress, warnings, frame inspector.
2. **DeviceDiscovery**: enumerates camera identities/modes and connected trigger transports. No silently choosing different camera after reconnect.
3. **VideoSource** (`IVideoSource`): starts/stops continuous acquisition, negotiates resolution/pixel layout, delivers timestamped immutable/reference-counted sample payloads and format metadata.
4. **TriggerSource** (`ITriggerSource`): Pico serial or Raw Input mouse, emits source ID, sequence number, monotonic host arrival stamp, signal edge and diagnostic status.
5. **SyncEngine**: stores bounded video ring buffer; aligns independent timestamp domains; matches accepted trigger to candidate frame inside calibrated stable-film window; flags misses.
6. **CaptureCoordinator**: single writer session state machine; applies arm/disarm/fault lifecycle; enforces one trigger -> one capture request -> one resolution.
7. **FrameWriter**: bounded asynchronous queue; writes file to temporary path then finalizes atomically where possible, records checksum, journals durable outcome.
8. **SessionStore**: versioned configuration, profiles, immutable capture sessions and recovery reconciliation.
9. **Review/Transforms**: preview orientation, export-only crop/grade, frame stepping, reel trims. Never destructively modify the original sequence.
10. **ExportService**: validates sequence; invokes known, pinned FFmpeg binary; writes output temp then final file and checks frame count/duration.
11. **Diagnostics**: structured logs, drop counters, latency histograms, camera mode, queue length, storage capacity, faults.
12. **SimulationBackend**: synthetic numbered frames and programmable trigger cadence without physical devices.

## Capture state machine
```text
Disconnected -> PreviewReady -> Armed/Capturing -> Stopped -> Exporting
                      \           |
                       \          v
                        -----> Faulted -> Recovery/Resegment -> PreviewReady
```
Hardware safety boundary: software stop **cannot stop projector motor**. Pausing without transport stopping risks missing physical frames. Any resume requires explicit film-position decision and new segment metadata.

## Trigger protocol proposal
Use newline-delimited ASCII or length-framed binary, **versioned**; initial ASCII example:
```text
WP1 EVT seq=123456 edge=fall tick_us=827161902
WP1 STATUS firmware=0.1 input=GP2 mode=contact
```
Sequence counter wraps according to documented protocol. Include boot/session identifier, firmware/protocol version, transport errors, reconnect handling. Do not assume USB arrival time equals contact closure time. Maintain Pico monotonic ticks and host arrival time; measure drift and latency. Unexpected sequence gaps must raise alarms, not silently manufacture missing frames. Avoid parsing ambiguous free-form strings in production; choose and document a strict schema with unit tests.

## Timing algorithm
1. Acquire continuously in a negotiated video mode; retain sample sequence, PTS, monotonic arrival timestamp, interlace/color metadata.
2. Receive valid trigger edge; discard only *documented* switch chatter with configurable debounce and logged rejection.
3. Store pending capture request keyed by event sequence.
4. Using saved calibration, select sample within target stable-film interval around trigger. Candidate may precede or follow arrival because video and USB paths buffer differently.
5. Confirm sample available/usable; preserve exact selected image to frame queue; if not, record unresolved request (no fabricated repeat).
6. Journal event, selected sample ID, offset, saved path, source mode and outcome. Revalidate calibration after hardware or mode changes.

**Clock caveat:** Media Foundation sample PTS and host timer ticks may be unrelated clock epochs; estimate mapping, monitor drift/discontinuities, and record calibration confidence.

## Consistency and concurrency
- Bounded image buffer and writing queue with configured backpressure. Never block input callback on PNG compression or UI rendering.
- Atomic file finalize plus journal. On startup reconcile orphaned temporary files, persisted frames and event ledger.
- **Accepted triggers = committed frames + pending + unresolved/failed.**
- Counters prove software accounting, **not film movement correctness**.
- Lost focus/disconnected mouse cannot automatically stop physical film; surface conspicuous fault and operator guidance.
- Use immutable session snapshots when exporting, never overwrite masters.
- No blind reconnect to new device with same UI ordinal.

## Data layout
```text
Library/
  Reel_001/
    session.json
    events.jsonl
    frames/
      frame_000000001.png
      frame_000000002.png
    segments/
    exports/
      Reel_001-archive.mkv
      Reel_001-viewing.mp4
    logs/
```
`session.json` records project ID, machine profile, timestamp, camera mode, nominal film fps, frame mapping, timing calibration, checksum manifest, export choices. JSON schema version required for migration. Storage on NTFS assumed by default; validate alternative filesystems.

## Camera-specific abstractions
A camera is not necessarily a USB webcam: HDMI capture dongle, DV/FireWire, PCI capture card and historical legacy drivers have different host support. No claim of support until a real driver/acquisition test passes. Do not infer 10-bit capture from an HDMI camera marketing claim; query actual pixel format and inspect output.

## Security and maintainability
No cloud, outbound telemetry or credentials required. Least privilege, no admin for normal capture if device drivers allow. Structured logging excludes unrelated personal data. Pin dependencies and publish reproducible build recipes and checksums; sign releases if certificates available. Automated unit/integration tests, CI builds, code review, strict nullable types and analyzers.
