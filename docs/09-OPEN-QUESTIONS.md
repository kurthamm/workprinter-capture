# Open issues, risks and verification ledger

**These are facts not yet established; do not fill gaps with assumptions.**

1. **WorkPrinter model names**: owner believes both are XP; photograph actual labels, hardware controls, frame gate and sync ports.
2. **Sync connection**: original WorkPrinter-to-modified-mouse RCA arrangement; determine which device has socket, center/shell wiring, whether electrically passive, voltage, polarity, bounce, contact-to-stationary-frame relationship.
3. **Input conditioning**: choose opto-isolation/resistors/clamping ONLY after measuring output and knowing isolation requirements. Earlier direct GP2 pin 4 to center, GND pin 3 to shell proposal is conditional and not validated.
4. **Actual camera(s)**: make/model, video outputs, true clean HDMI vs DV/FireWire/analog; capture mode, cable and adapter. Modern USB camera may not match original optical needs.
5. **Video quality ceiling**: genuine resolution, 8/10-bit pipeline, full/limited range, field order, framerate, optics, exposure and power.
6. **Physical machine state**: transport, film tension, lamp, lens, shutter timing, film safety.
7. **Pico board/enclosure**: whether Pico 2 H and screw terminals have actually been purchased; breakout dimensions and USB plug clearance; LeMotech enclosure fit.
8. **Dell PC**: Windows version, memory, SSD/disk bandwidth, USB port configuration, CPU and camera driver support; no assumption modern hardware is sufficient until measured.
9. **Capture speed**: actual event cadence, gate dwell time and camera buffering; calibrate stable-frame sample window.
10. **Archival color fidelity**: document calibration method and test chart if needed.
11. **Output delivery**: whether MP4 needs a specific television/USB/DVD compatibility preset.
12. **License**: user has said public repo, but no chosen source license.
13. **GitHub destination**: repository now under personal `kurthamm`; move to Aetheria Systems requires proper org permission and deliberate ownership transfer; separate similarly named *empty* repo exists: `kurthamm/Workprinter-Capture.`. Do not mutate the other repo accidentally.
14. **Historic software**: no recovered source code or installer. Archive descriptions are partial; original CineCap Velocity sync-audio approach is not the design target.
15. **Archival backend**: verify FFV1 pixel format and color metadata for selected camera; output format alone cannot create higher fidelity.
16. **Failure safety**: physical transport needs operator stop, not software assumption.

## Risk register
| Risk | Impact | Control |
|---|---|---|
| Unknown sync RCA energized | Damaged Pico/PC, potentially unsafe | Electrical identification and isolation |
| Camera latency/interlacing | Blurry, mixed or duplicate frames | Buffered sample calibration with reference reel |
| Projector keeps advancing after app fault | Irrecoverable film-frame gaps | Fail conspicuously; physical stop procedure |
| Legacy camera unsupported on Windows 11 | No video capture | Verify connection/driver before purchases; pluggable backend |
| False trigger suppression | Lost film frames | Configurable logged debounce; physical test |
| Disk write failure | Lost images | Bounded pipeline, journal and disk preflight |
| Silent source pixel conversion | Lost genuine color detail | Negotiate formats and preserve capture metadata |
| Confusion between two GitHub repos | Docs/source added to wrong project | Use canonical owner/repo and validate all writes |
| Historical forum content mistaken for spec | Incorrect device engineering | Mark evidence level and validate with hardware |

## Decisions needing owner input eventually
Open-source license; exact archive delivery presets; whether to include old mouse fallback in first UI; enclosure and camera purchase if existing camera is unsuitable. These do not block software simulator work.
