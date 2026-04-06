# VHS Restoration Pipeline

A modular, extensible video restoration pipeline designed specifically for digitized VHS footage. Prioritizes **natural-looking results** and **detail preservation** over maximum sharpness.

## Features

- **Deinterlacing** — yadif or bwdif conversion from interlaced to progressive
- **Adaptive denoising** — hqdn3d (fast) or nlmeans (better detail preservation)
- **Video stabilization** — two-pass vidstab to reduce VHS playback jitter
- **Color correction** — auto-levels, saturation, contrast, brightness, gamma
- **AI upscaling** — Real-ESRGAN with automatic lanczos fallback
- **Configurable pipeline** — toggle steps, choose presets, or provide custom JSON config
- **Modular architecture** — easy to add new processing steps

## Requirements

- **Python 3.10+**
- **FFmpeg 5.0+** (must be in PATH)
- **Optional:** [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases) for AI upscaling
- **Optional:** FFmpeg compiled with `--enable-libvidstab` for stabilization

## Installation

```bash
# Clone the repo
git clone https://github.com/joekincognito/vhs-restoration-pipeline.git
cd vhs-restoration-pipeline

# Install in development mode
pip install -e .
```

## Quick Start

```bash
# Basic restoration with balanced preset
vhs-restore input.avi -o output.mp4

# Safe preset (minimal processing)
vhs-restore input.avi -o output.mp4 --preset safe

# Aggressive preset (heavy processing + 4x upscale)
vhs-restore input.avi -o output.mp4 --preset aggressive

# See what the pipeline would do without processing
vhs-restore input.avi --dry-run

# Check if all dependencies are installed
vhs-restore input.avi --check
```

## CLI Reference

```
usage: vhs-restore [-h] [-o OUTPUT] [-p {safe,balanced,aggressive}]
                   [-c CONFIG] [--dry-run] [--check] [-v] [--version]
                   [--no-deinterlace] [--no-denoise] [--no-stabilize]
                   [--no-color] [--no-upscale] [--stabilize] [--upscale]
                   [--color]
                   input

positional arguments:
  input                 Input video file

options:
  -o, --output          Output video file (default: <input>_restored.mp4)
  -p, --preset          Processing preset: safe, balanced, aggressive
  -c, --config          Custom JSON config file (overrides preset)
  --dry-run             Show pipeline steps without processing
  --check               Verify dependencies and exit
  -v, --verbose         Debug logging
  --version             Show version

step toggles:
  --no-deinterlace      Skip deinterlacing
  --no-denoise          Skip denoising
  --no-stabilize        Skip stabilization
  --no-color            Skip color correction
  --no-upscale          Skip upscaling
  --stabilize           Force enable stabilization
  --upscale             Force enable upscaling
  --color               Force enable color correction
```

## Examples

### Override specific steps
```bash
# Use balanced preset but skip upscaling
vhs-restore input.avi -o output.mp4 --preset balanced --no-upscale

# Safe preset with stabilization added
vhs-restore input.avi -o output.mp4 --preset safe --stabilize
```

### Custom config file
```bash
# Apply custom settings on top of a preset
vhs-restore input.avi -o output.mp4 --preset safe --config my_settings.json
```

Example `my_settings.json`:
```json
{
  "denoise": {
    "mode": "nlmeans",
    "strength": "light"
  },
  "color": {
    "enabled": true,
    "saturation": 1.2
  }
}
```

### Python API
```python
from vhs_restore.config import load_config
from vhs_restore.pipeline import Pipeline

config = load_config(preset="balanced")
config["upscale"]["enabled"] = False  # skip upscaling

pipeline = Pipeline(config)
pipeline.run("input.avi", "output.mp4")
```

## Presets

| Preset | Deinterlace | Denoise | Stabilize | Color | Upscale | Use Case |
|--------|-------------|---------|-----------|-------|---------|----------|
| **safe** | bwdif | hqdn3d light | off | auto-levels | off | Decent footage, minimal cleanup |
| **balanced** | bwdif | nlmeans medium | on (10) | auto-levels + sat 1.15 | 2x ESRGAN | Most VHS tapes |
| **aggressive** | bwdif | nlmeans heavy | on (30) | full suite | 4x ESRGAN | Badly degraded tapes |

## FFmpeg Commands Used Internally

The pipeline builds and executes these FFmpeg commands:

```bash
# Deinterlace (bwdif, doubled framerate)
ffmpeg -y -i input.avi -vf "bwdif=mode=1:parity=0:deint=1" -c:v libx264 -crf 16 -preset slow -c:a copy step1.mp4

# Denoise (nlmeans, medium)
ffmpeg -y -i step1.mp4 -vf "nlmeans=s=5:p=7:pc=5:r=11:rc=9" -c:v libx264 -crf 16 -preset slow -c:a copy step2.mp4

# Stabilize pass 1 (detect motion)
ffmpeg -y -i step2.mp4 -vf "vidstabdetect=shakiness=5:accuracy=15:result=transforms.trf" -f null -

# Stabilize pass 2 (apply)
ffmpeg -y -i step2.mp4 -vf "vidstabtransform=input=transforms.trf:smoothing=10:crop=keep:zoom=0:optzoom=2" -c:v libx264 -crf 16 -preset slow -c:a copy step3.mp4

# Color correction
ffmpeg -y -i step3.mp4 -vf "normalize=blackpt=black:whitept=white:smoothing=20,eq=saturation=1.15" -c:v libx264 -crf 16 -preset slow -c:a copy step4.mp4

# Upscale (Real-ESRGAN)
realesrgan-ncnn-vulkan -i step4.mp4 -o output.mp4 -s 2 -n realesrgan-x4plus
```

## Project Structure

```
vhs-restoration-pipeline/
├── README.md
├── VHS_Restoration_Roadmap.md
├── pyproject.toml
├── LICENSE
├── examples/
│   └── custom_config.json
└── vhs_restore/
    ├── __init__.py
    ├── cli.py              # CLI entry point
    ├── config.py           # Config loading and preset management
    ├── pipeline.py         # Pipeline orchestrator
    ├── presets/
    │   ├── safe.json
    │   ├── balanced.json
    │   └── aggressive.json
    └── steps/
        ├── __init__.py
        ├── base.py         # Abstract base class
        ├── deinterlace.py  # Yadif / BWDIF
        ├── denoise.py      # hqdn3d / nlmeans
        ├── stabilize.py    # VidStab two-pass
        ├── color.py        # Color normalization
        └── upscale.py      # Real-ESRGAN + lanczos fallback
```

## Extending to Version 3

The architecture is designed for easy extension:

### Adding a new pipeline step

1. Create a new file in `vhs_restore/steps/` (e.g., `grain.py`)
2. Inherit from `PipelineStep` and implement `build_filter()`
3. Register it in `steps/__init__.py`
4. Add it to `STEP_ORDER` in `config.py`
5. Add default config values in `DEFAULT_CONFIG`

```python
# vhs_restore/steps/grain.py
from pathlib import Path
from .base import PipelineStep

class GrainStep(PipelineStep):
    name = "grain"
    description = "Add natural film grain after restoration"

    def __init__(self, config: dict):
        super().__init__(config)
        self.intensity = config.get("intensity", 25)
        self.size = config.get("size", 1.5)

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        vf = f"noise=alls={self.intensity}:allf=t+u"
        return [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "16", "-preset", "slow",
            "-c:a", "copy",
            str(output_path),
        ]
```

### Planned V3 features

- **Scene detection** — split video into scenes, apply different settings per scene
- **Adaptive filtering** — auto-detect noise levels and adjust denoise strength
- **Face enhancement** — GFPGAN/CodeFormer for face regions (optional, off by default)
- **Multi-pass upscaling** — 2x + denoise + 2x for better quality than single 4x
- **Batch processing** — queue system for processing folders of VHS captures
- **GPU acceleration** — NVENC encoding, CUDA FFmpeg filters

See [VHS_Restoration_Roadmap.md](VHS_Restoration_Roadmap.md) for the full roadmap.

## License

MIT
