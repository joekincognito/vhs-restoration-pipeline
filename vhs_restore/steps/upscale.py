"""Upscaling step — AI-powered resolution enhancement.

Supports:
- Real-ESRGAN (realesrgan-ncnn-vulkan) — best quality for real-world footage
- Lanczos (FFmpeg built-in) — fallback when Real-ESRGAN isn't available

Real-ESRGAN processes images, not video, so the workflow is:
  1. Extract frames from video as PNG
  2. Upscale each frame with Real-ESRGAN
  3. Reassemble frames into video with FFmpeg (preserving audio)

Real-ESRGAN models:
- realesrgan-x4plus — general purpose, best for real-world/VHS footage
- realesr-animevideov3 — optimized for animated content
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from .base import PipelineStep

logger = logging.getLogger(__name__)

ESRGAN_DEFAULT_PATH = r"C:\tools\realesrgan\realesrgan-ncnn-vulkan.exe"


class UpscaleStep(PipelineStep):
    name = "upscale"
    description = "AI-powered resolution upscaling"

    SCALE_FACTORS = {2, 3, 4}

    def __init__(self, config: dict):
        super().__init__(config)
        self.scale = config.get("scale", 2)
        self.model = config.get("model", "realesrgan-x4plus")
        self.esrgan_path = config.get("esrgan_path", ESRGAN_DEFAULT_PATH)
        self.fallback_to_lanczos = config.get("fallback_to_lanczos", True)

        if self.scale not in self.SCALE_FACTORS:
            raise ValueError(f"Scale must be one of {self.SCALE_FACTORS}, got {self.scale}")

    def _has_realesrgan(self) -> bool:
        path = Path(self.esrgan_path)
        return path.exists() or shutil.which(self.esrgan_path) is not None

    def _get_esrgan_exe(self) -> str:
        """Return the resolved path to the Real-ESRGAN executable."""
        path = Path(self.esrgan_path)
        if path.exists():
            return str(path)
        found = shutil.which(self.esrgan_path)
        if found:
            return found
        return self.esrgan_path

    def check_dependencies(self) -> list[str]:
        missing = super().check_dependencies()
        if not self._has_realesrgan() and not self.fallback_to_lanczos:
            missing.append("realesrgan-ncnn-vulkan")
        return missing

    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        """Build FFmpeg lanczos upscale command (fallback mode)."""
        return [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"scale=iw*{self.scale}:ih*{self.scale}:flags=lanczos",
            "-c:v", "libx264",
            "-crf", "16",
            "-preset", "slow",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]

    def _run_esrgan(self, input_path: Path, output_path: Path) -> None:
        """Upscale video using Real-ESRGAN frame-by-frame.

        1. Extract frames as PNG
        2. Real-ESRGAN upscales the entire directory of frames
        3. Reassemble with FFmpeg, copying audio from original
        """
        temp_dir = tempfile.mkdtemp(prefix="esrgan_")
        frames_in = Path(temp_dir) / "frames_in"
        frames_out = Path(temp_dir) / "frames_out"
        frames_in.mkdir()
        frames_out.mkdir()

        try:
            # Step 1: Extract frames
            logger.info(f"[{self.name}] Extracting frames...")
            cmd_extract = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-qscale:v", "1",
                "-qmin", "1",
                str(frames_in / "frame_%06d.png"),
            ]
            result = subprocess.run(cmd_extract, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Frame extraction failed: {result.stderr[-1000:]}")

            frame_count = len(list(frames_in.glob("*.png")))
            logger.info(f"[{self.name}] Extracted {frame_count} frames")

            # Step 2: Upscale all frames with Real-ESRGAN
            # It supports directory input/output natively
            logger.info(
                f"[{self.name}] Upscaling {frame_count} frames {self.scale}x "
                f"with Real-ESRGAN ({self.model})..."
            )
            esrgan_exe = self._get_esrgan_exe()
            cmd_upscale = [
                esrgan_exe,
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-s", str(self.scale),
                "-n", self.model,
                "-f", "png",
            ]
            result = subprocess.run(cmd_upscale, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Real-ESRGAN failed: {result.stderr[-1000:]}")

            upscaled_count = len(list(frames_out.glob("*.png")))
            logger.info(f"[{self.name}] Upscaled {upscaled_count} frames")

            # Step 3: Get framerate from source
            probe_cmd = [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                str(input_path),
            ]
            probe = subprocess.run(probe_cmd, capture_output=True, text=True)
            fps = probe.stdout.strip() or "30"

            # Step 4: Reassemble frames into video with audio from original
            logger.info(f"[{self.name}] Reassembling video at {fps} fps...")
            cmd_assemble = [
                "ffmpeg", "-y",
                "-framerate", fps,
                "-i", str(frames_out / "frame_%06d.png"),
                "-i", str(input_path),
                "-map", "0:v",
                "-map", "1:a?",
                "-c:v", "libx264",
                "-crf", "16",
                "-preset", "slow",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                str(output_path),
            ]
            result = subprocess.run(cmd_assemble, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Frame reassembly failed: {result.stderr[-1000:]}")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def run(self, input_path: Path, output_path: Path) -> Path:
        if not self.enabled:
            logger.info(f"[{self.name}] Skipped (disabled)")
            return input_path

        if self._has_realesrgan():
            try:
                self._run_esrgan(input_path, output_path)
                logger.info(f"[{self.name}] Done → {output_path.name}")
                return output_path
            except RuntimeError as e:
                if self.fallback_to_lanczos:
                    logger.warning(f"[{self.name}] Real-ESRGAN failed ({e}), falling back to lanczos")
                else:
                    raise
        elif not self.fallback_to_lanczos:
            raise RuntimeError(
                "Real-ESRGAN not found and fallback_to_lanczos is disabled. "
                "Install realesrgan-ncnn-vulkan or enable fallback."
            )

        # Lanczos fallback
        logger.info(f"[{self.name}] Upscaling {self.scale}x with lanczos")
        cmd = self.build_filter(input_path, output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Lanczos upscale failed: {result.stderr[-1000:]}")

        logger.info(f"[{self.name}] Done → {output_path.name}")
        return output_path
