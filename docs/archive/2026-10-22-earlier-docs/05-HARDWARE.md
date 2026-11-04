# Hardware, connections and electrical safety

## Inventory and status
| Item | Purpose | Status |
|---|---|---|
| Two MovieStuff WorkPrinter machines | Mechanical frame advance and illumination for Regular 8/Super 8 | Owner reports owned; **XP model unverified** |
| Dell Core i7 used computer from Goodwill | Windows capture workstation | Identified in prior discussion as purchased for project; specifications/OS unverified |
| Original modified mouse and cable | Legacy click-based capture trigger | Previously owned / availability and plug type need physical confirmation |
| Camera(s), optics, tripod and AC power | Continuous imaging of projection area | Exact gear unknown |
| Camera-to-PC adapter | Modern video acquisition | Depends on camera; HDMI/USB, FireWire or analog cannot be assumed |
| Raspberry Pi Pico 2 H | New USB frame-trigger interface | Selected in plan; possession unverified |
| Screw-terminal Pico breakout board | Convenient connection wiring | Planned; board dimensions/pin mapping not verified |
| Small ABS project enclosure | House Pico and terminations | LeMotech 158×90×60 mm *candidate* only; physical fit unverified |
| USB data cable | Pico USB power + CDC transport | Planned |
| RCA/phono male-to-male cable | WorkPrinter sync connection | Planned, verify exact jack and where installed |
| RCA female-to-terminal adapter | Connect sync conductors to interface | Planned |
| HDMI cable, Elgato Cam Link 4K | Candidate video acquisition chain | Planned, **not confirmed purchased** |
| Used Panasonic HC-V770 / HC-V800 or new HC-V900 | Candidate HDMI camcorder | Considered alternatives, **not required if existing camera adequate** |
| DVD writer/DVD-R/USB flash media | Optional finished-movie delivery | Not needed for capture |

Do not buy before inventorying existing hardware and measuring actual sync characteristics.

## Intended physical wiring (after electrical verification)
```text
Film WorkPrinter -> optical gate -> video camera -> compatible capture adapter -> Windows PC
                 -> synchronization RCA -> VERIFIED SAFE input conditioner -> Pico 2 H -> USB PC
```
The first drawing discussed *conditional contact-closure wiring*:
- RCA **center conductor** -> Pico **GP2** (physical pin **4**).
- RCA **outer shell/shield** -> Pico **GND** (physical pin **3**).
- Pico internal pull-up on GP2, falling edge on contact closure.
- Pico USB connection provides its own power and data.
This is **not an approved connection to unverified hardware**. It applies ONLY if sync is confirmed to be an isolated, voltage-free closure suitable for direct GPIO input. For a driven, externally powered, floating or higher-voltage signal, design an opto-isolated or otherwise rated input first.

### Critical unresolved safety checks
1. Determine **whether sync RCA is on the WorkPrinter or modified mouse**, and whether its connector carries a contact, active logic pulse, motor circuit or other source.
2. Examine hardware/manual or obtain circuit identification before electrical connection.
3. Use a properly rated meter/instrument and competent electronics safety practices to identify ground reference, voltage range, polarity, steady-state behavior and transient behavior; avoid shorting energized leads while probing.
4. Only after verifying passive contact behavior, test switch continuity/pulses and safe GPIO wiring. Never feed 5 V into Pico GPIO (3.3 V I/O).
5. If voltage/polarity uncertain, **do not connect GPIO**; use a properly engineered optocoupler module/input conditioner of known specifications. Do not arbitrarily attach the WorkPrinter ground to the PC through Pico.
6. Confirm Pico board variant, headers, screw-terminal breakout board silk screen and **physical pin versus GPIO index** before tightening wiring.

## Pico design
- Firmware written in C/C++ using official Pico SDK.
- GPIO input configured only after verified safe physical interface, with appropriate pull-up/down for circuit.
- Detect one configured transition per frame; configurable contact debounce and minimum gap, preserving diagnostic raw edges.
- Sequence-number every valid trigger; send over USB CDC serial to Windows, include boot identifier / version / uptime ticks.
- Host logs sequences, gaps, reconnects and timestamp offset; firmware must not claim knowledge of film position beyond contact timing.
- Choose USB serial rather than HID mouse to keep input isolated from Windows desktop controls.
- Firmware should boot in safe mode, report wiring/device status, offer simulation/test events and fail visibly rather than generating false triggers.

## Camera characteristics
Determine camera model, lens path and live-output standard. Continuous HDMI (without overlays) may be appropriate, but old camcorders may expose DV/FireWire or analog. Confirm whether live HDMI outputs at full quality, progressive or interlaced, clean screen, frame/field rate, bit depth, range/primaries and actual negotiated capture adapter format. Stable mount, AC power, consistent illumination/exposure, no autofocus drift and accurate field framing are critical. **Camera capture adapter output** may be less capable than camera sensor. No software can create missing detail.

## Model discovery protocol
Photograph nameplate, switches, cable connectors, camera model/ports and original modified mouse. Test each WorkPrinter separately for transport and illuminated gate operation before adding software. Verify sync event rate and association with stable film frames using expendable leader/reference strip.

## Electrical / operational warnings
Do not run film through unknown-condition transport with irreplaceable originals before checking rollers, gate, light source and take-up. Software Stop does **not** stop film motor; physical controls remain authoritative. A mis-triggering system can lose a whole reel unless calibration and early sample testing pass.
