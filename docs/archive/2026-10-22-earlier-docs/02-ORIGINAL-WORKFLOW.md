# Original workflow and proposed reproduction

## Physical signal flow
```text
                       [MovieStuff WorkPrinter XP?]
                       film advance + illumination
                                 |
             projected optical image       frame-sync switch
                        |                         |
                 video camera            modified mouse (historical)
                        |                         |
                video input PC             click event to PC
                        +-----------+-------------+
                                    |
                           CineCap / DodCap
                            captures 1 frame
                                    |
                        ordered images -> AVI
```

## Essential clarification
**Click does not advance film.** WorkPrinter mechanically transports it. A contact creates a sync signal. Original modified mouse represented that signal as a click of a software Capture button. The software extracted an image from the *continuous* camera stream. It captured a sequence and produced a movie by assigning a playback rate. 1,800 images / 18 fps = 100 seconds of film, independent of how long transfer took.

## Proposed modern path
```text
WorkPrinter optics -> camera -> HDMI/USB adapter -> video samples
WorkPrinter RCA sync (type TBD) -> safe conditioned input -> Pico 2 H
Pico -> USB CDC serial events -> Windows capture engine
Windows -> calibrated frame selection -> lossless images + event journal
        -> FFmpeg FFV1/MKV archival master and H.264/MP4 viewing copy
```
Original modified mouse remains a fallback: Raw Input can distinguish source HID mouse devices but **cannot promise system-wide click suppression**. The Pico USB input avoids accidental UI clicks if its electrical interface is safely designed.

## Unverified details
Exact XP sync socket, polarity, pinout, contact characteristics, timer position, original camera type, film optics and projector speed must be verified from each machine; family-level documentation is not proof of a particular model's circuit. Film motion timing must be calibrated, not guessed from mouse click arrival time.

## Film speed
Regular 8 commonly uses 16 fps, Super 8 silent frequently 18 fps, and some reels may use other rates, especially 24 fps. Provide **editable presets 16 / 18 / 24 and custom rational speed**. A historical software menu's “15 fps” entry is not a universal physical-film standard.

## Frame acquisition and interlacing
Video runs independently from trigger signal. Keep a bounded rolling buffer with timestamps, locate the **stationary interval** after calibration, and select an appropriate image. Interlaced capture may combine fields from different film positions; avoid mixed-field frames or silently halving resolution.
