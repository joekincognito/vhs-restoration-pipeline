"""Sharpening step — restores detail lost to VHS softness and denoising.

Uses FFmpeg's unsharp mask filter. Applied after denoise to recover
edges without amplifying noise.

Parameters:
  luma_x/y: sharpen matrix size (must be odd, 3-13)
  luma_amount: strength (negative = blur, 0 = off, positive = sharpen)
  chroma_x/y: same for color channels
  chroma_amount: same for color channels
"""

from pathlib import Path
from .base import PipelineStep


class SharpenStep(PipelineStep):
    name = "sharpen"
    description = "Restore detail lost to VHS softness"

    def __init__(self, config: dict):
        super().__init__(config)
        self.strength = config.get("strength", "light")

    def _params(self) -> str:
        presets = {
            "light":  "5:5:0.5:5:5:0.3",
            "medium": "5:5:0.8:5:5:0.5",
            "heavy":  "7:7:1.2:5:5:0.8",
        }
        params = presets.get(self.strength, presets["light"])
        return f"unsharp={params}"

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", self._params(),
            "-c:v", "libx264",
            "-crf", "16",
            "-preset", "slow",
            "-c:a", "copy",
            str(output_path),
        ]
