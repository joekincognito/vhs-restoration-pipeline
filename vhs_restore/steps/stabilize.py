"""Stabilization step — reduces jitter from VHS playback instability.

Uses FFmpeg's vidstab library (libvidstab) which requires two passes:
  1. Analyze motion vectors → write transform data file
  2. Apply smoothed transforms to stabilize the video
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from .base import PipelineStep

logger = logging.getLogger(__name__)


class StabilizeStep(PipelineStep):
    name = "stabilize"
    description = "Reduce jitter from VHS playback instability"

    def __init__(self, config: dict):
        super().__init__(config)
        self.smoothing = config.get("smoothing", 10)
        # How much of the border to crop vs fill (0=keep, 1=crop)
        self.crop = config.get("crop", "keep")
        # Zoom to hide black borders from stabilization (percentage)
        self.zoom = config.get("zoom", 0)
        self.optzoom = config.get("optzoom", 2)  # 2 = optimal adaptive zoom

    def check_dependencies(self) -> list[str]:
        missing = super().check_dependencies()
        # Check if vidstab is available by running a quick test
        result = subprocess.run(
            ["ffmpeg", "-filters"],
            capture_output=True, text=True,
        )
        if "vidstab" not in result.stdout:
            missing.append("libvidstab (FFmpeg must be compiled with --enable-libvidstab)")
        return missing

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        # This isn't used directly — stabilization needs two passes
        # See run() below
        raise NotImplementedError("StabilizeStep uses custom run() with two passes")

    def run(self, input_path: Path, output_path: Path) -> Path:
        if not self.enabled:
            logger.info(f"[{self.name}] Skipped (disabled)")
            return input_path

        logger.info(f"[{self.name}] Processing: {input_path.name} (two-pass)")

        # Create temp file for motion transform data
        transforms_file = tempfile.NamedTemporaryFile(
            suffix=".trf", delete=False, prefix="vidstab_"
        )
        transforms_path = transforms_file.name
        transforms_file.close()

        # FFmpeg filter parser treats \ as escape and : as separator.
        # Convert to forward slashes and escape colons for Windows paths.
        filter_safe_path = transforms_path.replace("\\", "/").replace(":", "\\\\:")

        try:
            # Pass 1: Detect motion
            logger.info(f"[{self.name}] Pass 1/2: Analyzing motion...")
            cmd_detect = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-vf", f"vidstabdetect=shakiness=5:accuracy=15:result={filter_safe_path}",
                "-f", "null", "-",
            ]
            logger.debug(f"[{self.name}] Pass 1 command: {' '.join(cmd_detect)}")

            result = subprocess.run(cmd_detect, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"[{self.name}] Pass 1 failed:\n{result.stderr[-2000:]}")
                raise RuntimeError(f"Stabilization pass 1 failed")

            # Pass 2: Apply transforms
            logger.info(f"[{self.name}] Pass 2/2: Applying stabilization...")
            transform_filter = (
                f"vidstabtransform="
                f"input={filter_safe_path}:"
                f"smoothing={self.smoothing}:"
                f"crop={self.crop}:"
                f"zoom={self.zoom}:"
                f"optzoom={self.optzoom}"
            )

            cmd_transform = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-vf", transform_filter,
                "-c:v", "libx264",
                "-crf", "16",
                "-preset", "slow",
                "-c:a", "copy",
                str(output_path),
            ]
            logger.debug(f"[{self.name}] Pass 2 command: {' '.join(cmd_transform)}")

            result = subprocess.run(cmd_transform, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"[{self.name}] Pass 2 failed:\n{result.stderr[-2000:]}")
                raise RuntimeError(f"Stabilization pass 2 failed")

        finally:
            Path(transforms_path).unlink(missing_ok=True)

        logger.info(f"[{self.name}] Done → {output_path.name}")
        return output_path
