# WorkPrinter Capture

Independent open-source-oriented reconstruction of the CineCap/DodCap-style capture workflow for **two existing MovieStuff WorkPrinter machines**, believed to be WorkPrinter XP. **Silent Regular 8mm and Super 8 only.**

**Status: requirements and design, not functioning software.** No projector, camera, modified mouse, Pico adapter, or archive output has been tested here.

## Documentation (start here)
1. [Project history and decisions](docs/01-HISTORY-AND-DECISIONS.md)
2. [Historical workflow and sources](docs/02-ORIGINAL-WORKFLOW.md)
3. [Complete architecture and component interfaces](docs/03-ARCHITECTURE.md)
4. [Requirements](docs/04-REQUIREMENTS.md)
5. [Hardware, Pico wiring and bill of materials](docs/05-HARDWARE.md)
6. [Media quality and archival policy](docs/06-VIDEO-AND-ARCHIVING.md)
7. [Testing and acceptance plan](docs/07-TESTING.md)
8. [Build milestones and engineering practices](docs/08-IMPLEMENTATION.md)
9. [Open questions, risks and verification ledger](docs/09-OPEN-QUESTIONS.md)
10. [Reference links](docs/10-REFERENCES.md)

## Planned implementation
- **Windows 11 x64 / C# / .NET 10 / WPF/MVVM** desktop program.
- Video: Media Foundation for verified camera/capture hardware; pluggable adapters where necessary.
- Trigger: **Raspberry Pi Pico 2 H, Pico SDK C/C++ firmware, USB serial**, with original modified mouse supported as fallback/diagnostic.
- Pipeline: continuous preview -> calibrated synchronization -> one saved image per valid physical film frame -> lossless image sequence -> FFV1/Matroska archival master and H.264/MP4 viewing copy through FFmpeg.
- Separate profiles for both WorkPrinters, initially **one active at a time**.
- **No audio path**: all reels in scope are silent.
- Preserve raw-as-received decoded images without destructive corrections; nondestructive crop/rotation/color settings only for exports.

## Safety
Never wire the unknown WorkPrinter RCA sync jack directly to the Pico GPIO until its actual electrical characteristics are verified. A Pico GPIO is 3.3 V logic and **not 5 V tolerant**. Details in hardware documentation.

## License
A public repository is not automatically open-source licensed. Choose and add a LICENSE file before describing redistribution rights.

## Provenance
This repository documents user-reported hardware and historical observations, and proposed engineering requirements. Where the original proprietary software specifications or machine pinout have not been obtained, the documentation explicitly says so.
