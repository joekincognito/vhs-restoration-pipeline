"""Denoising step — removes analog noise while preserving detail."""

from pathlib import Path
from .base import PipelineStep


class DenoiseStep(PipelineStep):
    name = "denoise"
    description = "Remove analog noise while preserving detail"

    # Supported modes:
    #   hqdn3d  — Fast, good for light noise (3D denoiser)
    #   nlmeans — Slower, much better detail preservation (non-local means)
    MODES = {"hqdn3d", "nlmeans"}

    def __init__(self, config: dict):
        super().__init__(config)
        self.mode = config.get("mode", "hqdn3d")
        self.strength = config.get("strength", "medium")  # light, medium, heavy

        if self.mode not in self.MODES:
            raise ValueError(f"Unknown denoise mode: {self.mode}. Use: {self.MODES}")

    def _hqdn3d_params(self) -> str:
        """hqdn3d=luma_spatial:chroma_spatial:luma_tmp:chroma_tmp"""
        presets = {
            "light":  "2:1.5:3:2",
            "medium": "4:3:6:4",
            "heavy":  "8:6:12:8",
        }
        params = presets.get(self.strength, presets["medium"])
        return f"hqdn3d={params}"

    def _nlmeans_params(self) -> str:
        """nlmeans with strength-based presets.

        s  = denoise strength (higher = more aggressive)
        p  = patch size (area compared for similarity)
        pc = patch size for chroma
        r  = research window size (search area)
        rc = research window for chroma
        """
        presets = {
            "light":  "s=3:p=7:pc=5:r=9:rc=7",
            "medium": "s=5:p=7:pc=5:r=11:rc=9",
            "heavy":  "s=8:p=7:pc=5:r=15:rc=11",
        }
        params = presets.get(self.strength, presets["medium"])
        return f"nlmeans={params}"

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        if self.mode == "hqdn3d":
            vf = self._hqdn3d_params()
        else:
            vf = self._nlmeans_params()

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
