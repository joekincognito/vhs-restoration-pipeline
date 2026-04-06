"""Base class for all pipeline steps."""

import logging
import subprocess
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineStep(ABC):
    """Abstract base class that all pipeline steps must implement."""

    name: str = "base"
    description: str = "Base pipeline step"

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", True)

    @abstractmethod
    def build_filter(self, input_path: Path, output_path: Path) -> list[str]:
        """Build the FFmpeg command arguments for this step.

        Returns a complete ffmpeg command as a list of strings.
        """
        ...

    def run(self, input_path: Path, output_path: Path) -> Path:
        """Execute this step. Returns the output path."""
        if not self.enabled:
            logger.info(f"[{self.name}] Skipped (disabled)")
            return input_path

        logger.info(f"[{self.name}] Processing: {input_path.name}")
        cmd = self.build_filter(input_path, output_path)
        logger.debug(f"[{self.name}] Command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"[{self.name}] FFmpeg error:\n{result.stderr[-2000:]}")
            raise RuntimeError(
                f"Step '{self.name}' failed with return code {result.returncode}"
            )

        logger.info(f"[{self.name}] Done → {output_path.name}")
        return output_path

    def check_dependencies(self) -> list[str]:
        """Return a list of missing dependencies. Empty list means all good."""
        missing = []
        if not shutil.which("ffmpeg"):
            missing.append("ffmpeg")
        return missing

    def __repr__(self):
        status = "enabled" if self.enabled else "disabled"
        return f"<{self.__class__.__name__} [{status}]>"
