# Hardware list and purchase tracker

Agreed list for the owner's two WorkPrinter XP machines (spec revision 3, `docs/superpowers/specs/2026-09-23-workprinter-capture-design.md`).
Tick the box when the item is in hand. Prices are US street prices checked 2026-10-11 and are approximate.

Changes from the spec, 2026-10-11:
- **Panasonic HC-V800 is discontinued** (B&H: "no longer available"). Replaced by its successor, the **HC-V900** (same 1/2.5" BSI sensor, 24× Leica zoom, 1080p60 over micro-HDMI, released Nov 2024, $700).
- **Mini PC named: Minisforum UM890 Pro** (Ryzen 9 8945HS, 32 GB, 1 TB, two M.2 slots). Its two USB4 ports sit on a separate controller from its four USB 3.2 ports, so each Cam Link gets its own full-speed path. Fits the spec's requirement.

## Plan: one WorkPrinter first (2026-10-11)

Build and prove the system on one WorkPrinter, then copy the per-machine kit for the second.

1. **Phase 1, bench test on the Pi 5:** Pico 2 H, breakout board, box, RCA cable + adapter, micro-USB cable, one Cam Link 4K. About $150.
2. **Phase 2, first camera:** HC-V900 camcorder, tripod, micro-HDMI cable. About $800.
3. **Phase 3, the real computer:** Minisforum UM890 Pro, 4 TB reel SSD, adapter, Ethernet cable. About $1,100.
4. **Phase 4, second WorkPrinter:** a second per-machine kit. About $930.

## Per WorkPrinter (one set now, a second set in phase 4)

| Have? | Item | Spec / notes | Approx. price | Where |
|---|---|---|---|---|
| [ ] | Panasonic HC-V900 camcorder (HC-V900K) | Live video feed, 1080p60 HDMI. AC adapter included; confirm on arrival | $700 | B&H, Panasonic |
| [ ] | Tripod | Sturdy, pan/tilt head, ~36–42 in from the condenser box. Reuse an old one if solid | $60–100 | any |
| [ ] | Elgato Cam Link 4K | HDMI → USB 3; standard Linux video device | $100 | Elgato, B&H, Amazon |
| [ ] | Micro-HDMI to HDMI cable, 6 ft | Camcorder → Cam Link. One may be in the camcorder box | $10 | any |
| [ ] | USB-C (male) to USB-A (female) adapter, USB 3.1 Gen 2 rated | Only one is needed: lets the second Cam Link use a USB4 port. Buy two to have a spare | $10 | any |
| [ ] | Raspberry Pi Pico 2 H | Headers fitted, no soldering. The sync box | $6 | Adafruit, Pimoroni, PiShop |
| [ ] | Screw-terminal breakout board for Pico | e.g. Adafruit 5095 or 52Pi terminal board; Pico 2 is pin-compatible with Pico | $10–20 | Adafruit, Pi Hut, Amazon |
| [ ] | Small project box | Holds the Pico and breakout; one hole for RCA, one for USB | $8 | any |
| [ ] | Micro-USB data cable, 6 ft | Sync box → mini PC. Must be a data cable, not charge-only | $8 | any |
| [ ] | RCA cable, male–male, 6 ft | WorkPrinter sync socket → sync box | $6 | any |
| [ ] | RCA female to screw-terminal adapter | Inside the sync box | $6 | Amazon ("RCA female to screw terminal") |

## One for both machines

| Have? | Item | Spec / notes | Approx. price | Where |
|---|---|---|---|---|
| [ ] | Minisforum UM890 Pro, 32 GB RAM, 1 TB SSD | Ryzen 9 8945HS, 2× USB4 + 4× USB 3.2, two M.2 slots. Runs everything | $650–800 | Minisforum, Best Buy |
| [ ] | 4 TB NVMe SSD (M.2 2280) | Reel drive, goes in the second M.2 slot. e.g. WD Black SN850X 4 TB or Samsung 990 Pro 4 TB | $300–380 | any |
| [ ] | Ethernet cable to the home router | Wi-Fi works, but wired is more reliable for the web page | $10 | any |
| [ ] | Monitor, keyboard, mouse (optional) | Only if you want the web page on the mini PC itself | reuse | — |

## Already have

| Item | Use |
|---|---|
| Raspberry Pi 5, 8 GB | Bench test machine: runs the app with one Pico kit and one Cam Link before the mini PC is bought. Later a status screen or ntfy host. Not a replacement for the mini PC (no hardware encoder; two 1080p60 feeds + PNG saving is at its limit) |

## Not needed (fallback only)

| Item | Why it's listed |
|---|---|
| Active PS/2-to-USB converter for the old syncmouse | No-wiring fallback. Not needed with the sync box. Good active converters cost $130+; skip |

## Rough total

| | |
|---|---|
| Per machine | about $930 |
| Mini PC + reel drive + cable | about $1,100 |
| **One WorkPrinter working (phases 1–3)** | **about $2,050** |
| Second WorkPrinter (phase 4) | about $930 |

## Purchase log

| Date | Item | Qty | Notes |
|---|---|---|---|
| 2026-10-11 | Raspberry Pi 5, 8 GB | 1 | Already owned |
