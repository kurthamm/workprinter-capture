# Full project history and decision log

## Why
The owner purchased **two MovieStuff WorkPrinter film-transfer machines** years ago and wishes to reuse them on a modern Windows PC. The model is believed to be **WorkPrinter XP**, but neither machine's nameplate has been inspected. The old capture software ran on older Windows and used a **modified mouse that clicked once per physical film frame**. Goal is a maintainable replacement rather than purchasing new scanners.

## Historical names identified
- **MovieStuff / WorkPrinter**, including XP and XP/HD-era documentation.
- **CineCap** and earlier **DodCap** (also associated with AlternaWare).
- In an owner's **April 6, 2023 email**: “What was that software that made the modified mouse click to take the frame-by-frame pictures?”
- On **April 11, 2023**, Roger from MovieStuff responded that it was called **CineCap**, was no longer available for purchase, and in his recollection worked only on 32-bit Windows XP.
- A **July 21, 2003** historical email from Jeff mentioned a **Dodcap Regular8 pulldown option listed as 15 fps instead of 16 fps**. Preserve this as historical evidence, *not* a correct recommended frame-rate interpretation for every reel.
- The original manufacturer is reported by forum participants as having closed in 2024. Historical site pages may be intermittently unavailable.

## Explained original mechanics
Film transport belongs to the WorkPrinter. The machine's sync switch actuated an adapted mouse via cable. The mouse click triggered software capture. A separate live video camera connection supplied the digital frames. The camera was not physically stepping the film and was not necessarily taking a separate still photograph on each click. The original capture software built a playable video (reported AVI) by assembling frames at the selected output/movie rate. Transfer rate and playback rate are independent.

## Decisions made in this conversation
1. Recreate the **original mouse-triggered stop-motion workflow**, not the later CineCap Velocity audio-pulse workflow.
2. **Use both existing WorkPrinters** with distinct saved hardware profiles. No requirement for concurrent use in v1.
3. **Silent film only**: no audio recording, WAV, AAC, audio synchronization, or noise removal subsystem.
4. Modern **Windows-native application**, proposed C#/.NET 10/WPF with standard packaging.
5. Use **Pico 2 H** as the preferred dedicated sync adapter rather than depending on GUI mouse clicks. Its C/C++ firmware detects valid physical sync events and sends USB messages to Windows.
6. **Keep original modified mouse as fallback and diagnostic**, supported by Windows Raw Input where feasible.
7. Video from a **camera connected to PC**; proposed HDMI capture path only if supported by actual camera and adapter. Do not assume existing gear is HDMI or USB.
8. First develop against **simulated triggers and video** before requiring the physical system to be assembled.
9. Highest *genuine* capture quality practical, source frames preserved, **FFV1 v3 in Matroska** archival movie and **H.264 MP4** shareable copy.
10. Never silently drop, duplicate, interpolate or overwrite captured original frames.
11. Exclude speculative motor control, cloud dependency, subscriptions and AI restoration from first usable release.
12. Repository named `workprinter-capture`; owner wants it eventually under **Aetheria Systems**. **Repository ownership transfer is not done by documenting this choice.**

## Previously discussed equipment and purchases (status uncertain)
- Two owned WorkPrinters.
- Computer: a used Dell Core i7 from Goodwill was later identified by owner as being for the 8mm conversion project.
- Potential used Panasonic HC-V770 or HC-V800 HDMI camcorder or newer HC-V900; verify whether existing camera suitable before buying.
- Elgato Cam Link 4K USB HDMI capture.
- HDMI cable of correct camera connector type; stable tripod and AC camera power.
- Raspberry Pi Pico 2 H, screw-terminal Pico breakout, small ABS enclosure, USB data cable, RCA male-to-male and female-to-screw-terminal adapter.
- A previously suggested LeMotech ABS enclosure **158 × 90 × 60 mm** (approx. 6.2 × 3.5 × 2.4 inches) as a candidate, *not verified fit*.
- DVD writer, DVD-R media and USB drives mentioned for delivery only.
- Further graphics card, RAM and drives were deliberately deferred.
- **Do not treat planned shopping items as confirmed purchased**, or make claims about present camera hardware.

## Design-document status
The earlier draft requirements and rebuild spec are research-based plans, not executable source and not official CineCap specifications. This repository is intended to preserve those plans and elaborate them into traceable implementation artifacts.
