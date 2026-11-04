# Video quality, silent-film fidelity and archival standards

## Goal
Digitize individual source film frames accurately; preserve the received image sequence and generate BOTH a preservation master and a widely playable copy. **No audio**: film in project scope is silent and application should not capture camcorder microphone/projector noise.

## Capture principles
- One *physical film frame* -> one correctly synchronized, stationary, in-focus captured image.
- Choose highest **genuine** resolution delivered end-to-end by camera, lens and capture adapter; target 1080p or higher when actually supported, **no artificial upscaling as master**.
- Preserve actual component bit depth and sample format; 10-bit preferred if actual equipment supports 10-bit throughout, but an 8-bit source is still 8-bit saved in a 16-bit container.
- Store negotiated resolution, frame/field format, color primaries, transfer characteristics, matrix coefficients, bit depth, pixel aspect and full/limited range where known.
- For color reproduction: prefer locked exposure, white balance and gain. Image corrections should be nondestructive export settings; avoid irreversible sharpening, denoising, scratch removal, fake HDR and frame interpolation.
- If analog/NTSC interlaced camera feed, ensure both fields of selected frame represent same stationary film position; avoid false combing or arbitrary loss of vertical detail.
- Keep original captured decoded images (PNG when appropriate for actual format) separate from produced video. Lossless file encoding cannot undo upstream MPEG compression or sensor limitations.

## Rate handling
- **Film capture event rate**, **live video camera sampling rate**, and **finished movie playback rate** are independent.
- Film playback presets **16, 18, 24 fps** plus custom exact rational.
- 1,800 frames at 18 fps = 100 seconds.
- Do not silently change movie duration, insert duplicates or interpolate for convenient nominal 30/60 fps.
- For broad playback compatibility, optionally create a separate 30/60 fps delivery encode using *explicit, documented* frame-repeat cadence while keeping native-rate archival version unchanged.
- Validate final output with frame count and duration checks.

## Storage and encoding
### Original captured sequence
Numbered lossless PNG or another appropriate lossless container for the verified decoded sample format, plus exact metadata/journal. Never destructively overwrite. Maintain checksums and backup plan.

### Archival master
- **FFV1 version 3 video codec** in **Matroska (.mkv)**, silent.
- Use a pinned FFmpeg build with tested command-line options, proper pixel format and color metadata; preserve orientation/aspect and exact film rate.
- Record per-frame/image source association, software revision, output checksum, encoder version, adjustments and failures.

### Viewing master
- **H.264/AVC in MP4** with reasonable high-quality encoder settings and widely supported pixel format, typically yuv420p for broad compatibility.
- Audio stream **absent**.
- Optional H.265 viewing format in later release, not required to make system useful.

## Color processing
Crop/rotate/flip, exposure, white balance, curves and film color correction should be **reversible** by retaining source frames and transform parameters. Any rescale to player-compatible format must be an export choice with recorded interpolation/filter and aspect metadata. Do not claim archival color calibration without reference targets and verified camera capture chain.

## Archival operations
Export checksums for image master/video master, retain capture logs and full software/firmware versions. Copy completed projects to an independent backup medium and verify integrity. A single drive is not long-term preservation.

## Audio decision
Earlier design explored 24-bit PCM/BWF and 48/96 kHz if soundtrack film existed. **Owner explicitly confirmed silent film**. Accordingly NO audio subsystem, audio file, AAC track, synchronized separate soundtrack or audio-dependent pipeline is in v1. Documenting discarded possibility here preserves project history without creating unnecessary requirements.

## Caution
“Archival-quality output format” describes chosen preservation encoding, **not proof** that the picture acquisition is archival quality. Optical alignment, cleanliness, gate stability, lighting flicker, frame timing, real capture resolution and compression determine acquired detail.
