"""Pipeline orchestrator — runs steps in sequence with temp file management."""

import logging
import tempfile
import shutil
from pathlib import Path

from .config import STEP_ORDER
from .steps import (
    DeinterlaceStep,
    DenoiseStep,
    StabilizeStep,
    ColorStep,
    UpscaleStep,
)

logger = logging.getLogger(__name__)

STEP_CLASSES = {
    "deinterlace": DeinterlaceStep,
    "denoise": DenoiseStep,
    "stabilize": StabilizeStep,
    "color": ColorStep,
    "upscale": UpscaleStep,
}


class Pipeline:
    """Orchestrates the restoration pipeline — runs enabled steps in order."""

    def __init__(self, config: dict):
        self.config = config
        self.steps: list[tuple[str, object]] = []

        for step_name in STEP_ORDER:
            step_config = config.get(step_name, {})
            step_class = STEP_CLASSES[step_name]
            step = step_class(step_config)
            self.steps.append((step_name, step))

    def check_dependencies(self) -> dict[str, list[str]]:
        """Check all enabled steps for missing dependencies.

        Returns dict of step_name → list of missing deps. Empty dict = all good.
        """
        issues = {}
        for name, step in self.steps:
            if step.enabled:
                missing = step.check_dependencies()
                if missing:
                    issues[name] = missing
        return issues

    def describe(self) -> str:
        """Return a human-readable description of the pipeline."""
        lines = ["Pipeline steps:"]
        for i, (name, step) in enumerate(self.steps, 1):
            status = "ON" if step.enabled else "off"
            lines.append(f"  {i}. [{status}] {name}: {step.description}")
        return "\n".join(lines)

    def run(self, input_path: Path, output_path: Path) -> Path:
        """Execute the full pipeline.

        Creates temporary intermediate files between steps and cleans them up
        when done. The final step writes directly to output_path.
        """
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Collect enabled steps
        enabled_steps = [(n, s) for n, s in self.steps if s.enabled]

        if not enabled_steps:
            logger.warning("No steps enabled — copying input to output")
            shutil.copy2(input_path, output_path)
            return output_path

        logger.info(f"Running pipeline: {len(enabled_steps)} steps enabled")
        logger.info(f"Input:  {input_path}")
        logger.info(f"Output: {output_path}")

        # Create temp directory for intermediate files
        temp_dir = tempfile.mkdtemp(prefix="vhs_restore_")
        temp_dir_path = Path(temp_dir)

        try:
            current_input = input_path

            for i, (name, step) in enumerate(enabled_steps):
                is_last = (i == len(enabled_steps) - 1)

                if is_last:
                    step_output = output_path
                else:
                    suffix = input_path.suffix or ".mp4"
                    step_output = temp_dir_path / f"step_{i+1}_{name}{suffix}"

                logger.info(f"--- Step {i+1}/{len(enabled_steps)}: {name} ---")
                current_input = step.run(current_input, step_output)

            logger.info(f"Pipeline complete → {output_path}")
            return output_path

        finally:
            # Clean up temp files
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp dir: {temp_dir}")
