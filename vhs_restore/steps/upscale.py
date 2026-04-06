"""Upscaling step — AI-powered resolution enhancement.

Supports:
- Real-ESRGAN (realesrgan-ncnn-vulkan) — best quality for anime/video content
- Lanczos (FFmpeg built-in) — fallback when Real-ESRGAN isn't available

Real-ESRGAN models for video:
- realesr-animevideov3 — best for animated content and clean video
- realesrgan-x4plus — general purpose, good for real-world footage
"""

import logging
import shutil
from pathlib import Path
from .base import PipelineStep

logger = logging.getLogger(__name__)


class UpscaleStep(PipelineStep):
    name = "upscale"
    description = "AI-powered resolution upscaling"

    SCALE_FACTORS = {2, 3, 4}

    def __init__(self, config: dict):
        super().__init__(config)
        self.scale = config.get("scale", 2)
        self.model = config.get("model", "realesrgan-x4plus")
        # Path to realesrgan-ncnn-vulkan binary (if not in PATH)
        self.esrgan_path = config.get("esrgan_path", "realesrgan-ncnn-vulkan")
        self.fallback_to_lanczos = config.get("fallback_to_lanczos", True)

        if self.scale not in self.SCALE_FACTORS:
            raise ValueError(f"Scale must be one of {self.SCALE_FACTORS}, got {self.scale}")

    def _has_realesrgan(self) -> bool:
        return shutil.which(self.esrgan_path) is not None

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
            "-c:a", "copy",
            str(output_path),
        ]

    def _build_esrgan_command(self, input_path: Path, output_path: Path) -> list[str]:
        """Build Real-ESRGAN command."""
        return [
            self.esrgan_path,
            "-i", str(input_path),
            "-o", str(output_path),
            "-s", str(self.scale),
            "-n", self.model,
        ]

    def run(self, input_path: Path, output_path: Path) -> Path:
        if not self.enabled:
            logger.info(f"[{self.name}] Skipped (disabled)")
            return input_path

        if self._has_realesrgan():
            logger.info(
                f"[{self.name}] Upscaling {self.scale}x with Real-ESRGAN "
                f"(model: {self.model})"
            )
            cmd = self._build_esrgan_command(input_path, output_path)
        elif self.fallback_to_lanczos:
            logger.warning(
                f"[{self.name}] Real-ESRGAN not found — falling back to lanczos {self.scale}x"
            )
            cmd = self.build_filter(input_path, output_path)
        else:
            raise RuntimeError(
                "Real-ESRGAN not found and fallback_to_lanczos is disabled. "
                "Install realesrgan-ncnn-vulkan or enable fallback."
            )

        logger.debug(f"[{self.name}] Command: {' '.join(cmd)}")

        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            if self._has_realesrgan() and self.fallback_to_lanczos:
                logger.warning(
                    f"[{self.name}] Real-ESRGAN failed, falling back to lanczos"
                )
                cmd = self.build_filter(input_path, output_path)
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"Upscale fallback also failed")
            else:
                logger.error(f"[{self.name}] Error:\n{result.stderr[-2000:]}")
                raise RuntimeError(f"Upscale step failed")

        logger.info(f"[{self.name}] Done → {output_path.name}")
        return output_path
