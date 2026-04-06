"""Color correction step — fixes faded colors and normalizes levels.

VHS tapes lose color fidelity over time:
- Saturation fades
- Color balance shifts (often toward red/yellow)
- Black levels drift
- Contrast compresses

This step applies corrective filters to restore natural-looking color.
"""

from pathlib import Path
from .base import PipelineStep


class ColorStep(PipelineStep):
    name = "color"
    description = "Fix faded colors and normalize levels"

    def __init__(self, config: dict):
        super().__init__(config)
        self.auto_levels = config.get("auto_levels", True)
        self.saturation = config.get("saturation", 1.0)     # 1.0 = no change
        self.contrast = config.get("contrast", 1.0)         # 1.0 = no change
        self.brightness = config.get("brightness", 0.0)     # 0.0 = no change
        self.gamma = config.get("gamma", 1.0)               # 1.0 = no change

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        filters = []

        # Auto-levels: normalize histogram to use full range
        if self.auto_levels:
            filters.append("normalize=blackpt=black:whitept=white:smoothing=20")

        # Manual EQ adjustments
        eq_parts = []
        if self.saturation != 1.0:
            eq_parts.append(f"saturation={self.saturation}")
        if self.contrast != 1.0:
            eq_parts.append(f"contrast={self.contrast}")
        if self.brightness != 0.0:
            eq_parts.append(f"brightness={self.brightness}")
        if self.gamma != 1.0:
            eq_parts.append(f"gamma={self.gamma}")

        if eq_parts:
            filters.append(f"eq={':'.join(eq_parts)}")

        if not filters:
            # Nothing to do — just copy
            return [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-c", "copy",
                str(output_path),
            ]

        vf = ",".join(filters)

        return [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-crf", "16",
            "-preset", "slow",
            "-c:a", "copy",
            str(output_path),
        ]
