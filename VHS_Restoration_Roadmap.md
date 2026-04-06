# VHS Restoration Pipeline — Project Roadmap

## Overview

A modular, extensible video restoration pipeline designed specifically for digitized VHS footage. The system prioritizes **natural-looking results**, **detail preservation**, and **configurability** over maximum sharpness or artificial enhancement.

VHS footage has specific artifacts that generic video enhancement tools handle poorly:
- Interlaced fields (60i → 30p or 24p)
- Analog noise (chroma bleed, dot crawl, rainbow artifacts)
- Head-switching noise (bottom-of-frame distortion)
- Tracking errors and horizontal jitter
- Color drift and faded saturation
- Generation loss from tape-to-tape copies

This pipeline addresses each of these systematically.

---

## Version 1 — Minimal Baseline (Reference Only)

> **Not implemented as a standalone tool.** Documented here as a conceptual baseline to show what a naive approach looks like and why Version 2 exists.

### What it would do
A single FFmpeg command chain with hardcoded parameters:

```bash
ffmpeg -i input.avi \
  -vf "yadif=1,hqdn3d=4:3:6:4,unsharp=5:5:0.8:5:5:0.3" \
  -c:v libx264 -crf 18 -preset slow \
  output.mp4
```

### Why this isn't enough
- No adaptability — same filters for clean footage and heavily damaged footage
- No modularity — can't skip or reorder steps
- No upscaling — stuck at original resolution (usually 480i/240p effective)
- Denoising is global and destroys fine detail
- No stabilization for jittery playback
- No color correction for faded/shifted colors

### Value as a baseline
Useful for A/B comparisons. Run this on a clip, then run the same clip through V2, and the difference demonstrates why the modular approach matters.

---

## Version 2 — Modular Pipeline (START HERE)

> **This is the initial implementation target.**

### Architecture

```
vhs_restore/
├── __init__.py
├── cli.py              # Command-line interface (argparse)
├── pipeline.py         # Orchestrator — runs steps in order
├── config.py           # Config loading, preset management
├── steps/
│   ├── __init__.py
│   ├── base.py         # Abstract base class for pipeline steps
│   ├── deinterlace.py  # Yadif / BWDIF deinterlacing
│   ├── denoise.py      # hqdn3d / nlmeans denoising
│   ├── stabilize.py    # VidStab two-pass stabilization
│   ├── upscale.py      # Real-ESRGAN / Video2X AI upscaling
│   └── color.py        # Color normalization and correction
└── presets/
    ├── safe.json
    ├── balanced.json
    └── aggressive.json
```

### Features
- **Toggle steps on/off** — skip stabilization, skip upscaling, etc.
- **Three built-in presets** — safe, balanced, aggressive
- **Custom config files** — JSON overrides for any parameter
- **CLI interface** — `vhs-restore input.avi -o output.mp4 --preset balanced`
- **Step base class** — all steps implement the same interface for easy extension
- **FFmpeg subprocess management** — proper error handling, progress reporting
- **Intermediate file management** — temp files between steps, cleanup on completion
- **Audio passthrough** — audio is preserved without re-encoding

### Pipeline Steps (in order)

| Step | Tool | Purpose |
|------|------|---------|
| 1. Deinterlace | FFmpeg yadif/bwdif | Convert interlaced fields to progressive frames |
| 2. Denoise | FFmpeg hqdn3d/nlmeans | Remove analog noise while preserving detail |
| 3. Stabilize | FFmpeg vidstabdetect + vidstabtransform | Reduce jitter from playback instability |
| 4. Color Correct | FFmpeg eq/colorbalance/curves | Fix faded colors, normalize levels |
| 5. Upscale | Real-ESRGAN (realesrgan-ncnn-vulkan) | AI upscale to 2x or 4x resolution |

### Presets

**Safe** — Minimal processing. Light denoise, no upscaling. For footage that's already decent.
- Deinterlace: bwdif (better quality)
- Denoise: hqdn3d with conservative settings
- Stabilize: off
- Color: auto-levels only
- Upscale: off

**Balanced** — Good results for most VHS footage. Moderate denoise, 2x upscale.
- Deinterlace: bwdif
- Denoise: nlmeans (slower but better)
- Stabilize: on, smoothing=10
- Color: auto-levels + saturation boost
- Upscale: 2x Real-ESRGAN

**Aggressive** — Maximum restoration. Heavy denoise, 4x upscale. Risk of over-processing.
- Deinterlace: bwdif
- Denoise: nlmeans with strong settings
- Stabilize: on, smoothing=30
- Color: full correction suite
- Upscale: 4x Real-ESRGAN

### Technical Milestones

1. ✅ Project structure and base classes
2. ✅ Deinterlace step working
3. ✅ Denoise step with hqdn3d and nlmeans
4. ✅ CLI with preset selection
5. ⬜ Stabilization (vidstab)
6. ⬜ Color correction
7. ⬜ Real-ESRGAN integration
8. ⬜ End-to-end pipeline test with real VHS footage
9. ⬜ Progress reporting

---

## Version 3 — Advanced/Pro System (Future)

### New Capabilities

#### Scene Detection
- Use FFmpeg `scene` filter or PySceneDetect to split video into scenes
- Apply different denoise/color settings per scene (dark scenes need less denoise)
- Avoid applying transitions across scene boundaries

#### Adaptive Filtering
- Analyze noise levels per-frame or per-scene
- Automatically adjust denoise strength based on measured noise
- Use histogram analysis to detect and correct color shifts per-segment

#### Face Enhancement
- Detect faces using OpenCV or MTCNN
- Apply targeted enhancement (GFPGAN or CodeFormer) to face regions only
- Blend enhanced faces back into the frame to avoid the "AI face" look
- Optional — off by default to preserve natural appearance

#### Multi-Pass Upscaling
- First pass: 2x upscale with Real-ESRGAN
- Intermediate denoise pass to clean upscaling artifacts
- Second pass: 2x upscale for final 4x result
- Better quality than single 4x pass for heavily degraded source

#### Film Grain Reintroduction
- After denoising and upscaling, footage can look "too clean"
- Add subtle film grain to restore natural texture
- Configurable grain intensity and size

#### Batch Processing
- Process entire folders of VHS captures
- Queue management with progress tracking
- Resume interrupted batches
- Per-file or per-folder config overrides

#### GPU Acceleration
- NVENC/QSV hardware encoding for faster output
- CUDA-accelerated FFmpeg filters where available
- Real-ESRGAN already supports Vulkan GPU

### Architecture Changes for V3
- **Plugin system** — drop new step modules into `steps/` and they auto-register
- **Step dependency graph** — steps declare what they need (progressive input, specific resolution)
- **Analysis pass** — pre-scan the video to collect metadata before processing
- **Project files** — save/load pipeline configurations per video or collection
- **Web UI** — optional browser-based interface for preview and parameter tuning

### Risks and Tradeoffs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Over-processing (plastic look) | High — defeats the purpose | Conservative defaults, A/B preview |
| Real-ESRGAN not installed | Medium — upscale step fails | Graceful fallback to lanczos scaling |
| VidStab two-pass is slow | Medium — long processing times | Make stabilization optional, show progress |
| Face enhancement looks artificial | High — uncanny valley | Off by default, blend strength configurable |
| Large intermediate files | Medium — disk space | Temp dir management, cleanup between steps |
| FFmpeg version differences | Low — filter availability | Check filter availability at startup |
| Color correction too aggressive | Medium — unnatural colors | Conservative defaults, before/after preview |

---

## Tools and Libraries

### Required
- **Python 3.10+** — main language
- **FFmpeg 5.0+** — core video processing (must be in PATH)

### Optional (for advanced features)
- **Real-ESRGAN (realesrgan-ncnn-vulkan)** — AI upscaling binary
- **Video2X** — alternative upscaling framework
- **vidstab** — FFmpeg must be compiled with `--enable-libvidstab`
- **PySceneDetect** — scene detection (V3)
- **OpenCV** — face detection and analysis (V3)
- **GFPGAN / CodeFormer** — face enhancement (V3)

### Python Dependencies
- `subprocess` (stdlib) — FFmpeg execution
- `json` (stdlib) — config management
- `argparse` (stdlib) — CLI
- `pathlib` (stdlib) — cross-platform paths
- `shutil` (stdlib) — temp file management
- `logging` (stdlib) — structured logging
- `tqdm` — progress bars (optional)

---

## Development Timeline (Suggested)

| Phase | Scope | Est. Effort |
|-------|-------|-------------|
| V2 Core | Pipeline + deinterlace + denoise + CLI | Weekend project |
| V2 Stabilize | VidStab integration | 1-2 sessions |
| V2 Color | Color correction step | 1-2 sessions |
| V2 Upscale | Real-ESRGAN integration | 1-2 sessions |
| V2 Polish | Error handling, progress, docs | 1 session |
| V3 Scene Detection | PySceneDetect + per-scene config | 2-3 sessions |
| V3 Adaptive | Noise analysis + auto-tuning | 3-4 sessions |
| V3 Face Enhancement | Detection + GFPGAN + blending | 3-4 sessions |
| V3 Batch + GPU | Queue system + hardware accel | 2-3 sessions |
