"""Deinterlacing step — converts interlaced VHS fields to progressive frames."""

from pathlib import Path
from .base import PipelineStep


class DeinterlaceStep(PipelineStep):
    name = "deinterlace"
    description = "Convert interlaced fields to progressive frames"

    # Supported modes:
    #   yadif  — Yet Another DeInterlacing Filter (fast, good quality)
    #   bwdif  — Bob Weaver Deinterlacing Filter (slower, better quality)
    MODES = {"yadif", "bwdif"}

    def __init__(self, config: dict):
        super().__init__(config)
        self.mode = config.get("mode", "bwdif")
        # yadif/bwdif parity: 0=TFF (top field first, standard for VHS NTSC)
        self.parity = config.get("parity", 0)

        if self.mode not in self.MODES:
            raise ValueError(f"Unknown deinterlace mode: {self.mode}. Use: {self.MODES}")

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        if self.mode == "yadif":
            # mode=1 sends each field as a frame (doubles framerate for smoother output)
            # deint=1 only deinterlaces frames marked as interlaced
            vf = f"yadif=mode=1:parity={self.parity}:deint=1"
        else:
            vf = f"bwdif=mode=1:parity={self.parity}:deint=1"

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
