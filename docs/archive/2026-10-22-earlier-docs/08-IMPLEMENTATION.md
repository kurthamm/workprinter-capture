# Implementation roadmap, engineering standards and deliverables

## Development stack
- C# (.NET 10 LTS), Windows 11 x64, WPF/XAML, MVVM; nullable reference types on, analyzer enforcement, warnings treated as errors in CI.
- C/C++ (Raspberry Pi Pico SDK) embedded firmware, strict versioned serial protocol, defined time units and wraparound.
- Media Foundation camera backend with optional pluggable alternatives after testing real hardware.
- Async bounded channels for ingest/sync/storage, immutable data models for samples and events.
- FFmpeg subprocess pinned to known tested binary release and documented distribution terms.
- JSON settings and sessions, JSONL event journal, immutable frames; command-independent export from journaled frame order.

## Proposed repository tree once coding begins
```text
src/
  WorkPrinterCapture.App/          # WPF Windows GUI
  WorkPrinterCapture.Core/         # pure models, state, timing, policy
  WorkPrinterCapture.Capture/      # Media Foundation/camera adapters
  WorkPrinterCapture.Triggers/     # Pico CDC and legacy Raw Input
  WorkPrinterCapture.Storage/      # projects, frames, journals and recovery
  WorkPrinterCapture.Export/       # FFmpeg integration
firmware/pico2-sync/               # Pico SDK C/C++
tests/
  WorkPrinterCapture.Core.Tests/
  WorkPrinterCapture.IntegrationTests/
  WorkPrinterCapture.Simulation/
docs/                               # specifications and manuals
.github/workflows/                  # build and test
```
This is a roadmap; empty folders are not proof of implemented modules.

## Delivery increments
1. **Simulator + proof-of-concept**: WPF window, generated camera stream, manual trigger and image-sequence export.
2. **Hardware-independent reliability**: event journal, writer, state machine, recovery, timing tests.
3. **Real camera**: enumerate/preview/capture for an actually verified interface, documented live mode and format.
4. **Pico firmware + USB transport**: safe input testing, versioned sequence messages, control/diagnostics and validated event reliability.
5. **Sync calibration and review**: sample buffer and stable-frame selection, detailed fault handling, reel viewer.
6. **Film export**: FFV1 v3/MKV, H.264/MP4, native frame-rate selection and validation.
7. **One WorkPrinter full validation**, then **second WorkPrinter** with profile switching.
8. **Release**: Windows installer, operator guide, hardware compatibility matrix, wiring diagram after measured validation, regression tests and maintenance instructions.

## Quality gates
- Unit tests for source identity, trigger edge parsing, debounce, event ordering, timing, clock drift, movie duration and recovery.
- Integration tests with synthetic media/video device; fault injection for disk and device disconnect.
- CI compile, static analysis, tests, dependency vulnerability scan and code style checks.
- Pin versions, lock file/tool manifests, changelog, meaningful commits and tagged releases.
- Native Windows application must not run capture/storage/codec work on UI thread.
- Do not ship an untested waveform conditioner/wiring recipe as ready-to-connect hardware.
- Clearly mark all untested hardware and supported camera modes.

## Distribution and licenses
Select explicit open-source license (e.g. MIT or Apache-2.0) after owner decision; until then no license granted simply by being public. Track FFmpeg and bundled codec/library licensing requirements, produce attributable third-party notices. Provide installers that work offline where feasible and published SHA-256 hashes; signing where certificate is available. No key or user credentials committed.

## Definition of done
Installer actually operates on user's Windows PC with recognized camera and Pico, passes physical film reference tests for both WorkPrinters, exports correct silent archival/viewing files and preserves originals after failure.
