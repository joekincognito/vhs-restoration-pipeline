"""Pipeline orchestrator — runs steps in sequence with temp file management.

Supports two modes:
  - Standard: same settings for the entire video
  - Adaptive: analyze video, detect scenes, apply per-scene settings
"""

import logging
import tempfile
import shutil
from pathlib import Path

from .config import STEP_ORDER, load_config
from .steps import (
    DeinterlaceStep,
    DenoiseStep,
    SharpenStep,
    StabilizeStep,
    ColorStep,
    UpscaleStep,
)

logger = logging.getLogger(__name__)

STEP_CLASSES = {
    "deinterlace": DeinterlaceStep,
    "denoise": DenoiseStep,
    "sharpen": SharpenStep,
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
        """Check all enabled steps for missing dependencies."""
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
        """Execute the full pipeline (standard mode — same settings for all)."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        enabled_steps = [(n, s) for n, s in self.steps if s.enabled]

        if not enabled_steps:
            logger.warning("No steps enabled — copying input to output")
            shutil.copy2(input_path, output_path)
            return output_path

        logger.info(f"Running pipeline: {len(enabled_steps)} steps enabled")
        logger.info(f"Input:  {input_path}")
        logger.info(f"Output: {output_path}")

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
            shutil.rmtree(temp_dir, ignore_errors=True)


class AdaptivePipeline:
    """Adaptive pipeline — analyzes video and applies per-scene settings.

    Workflow:
      1. Detect scene boundaries
      2. Analyze each scene (noise, brightness, motion)
      3. Generate per-scene config overrides
      4. Split video into scenes
      5. Process each scene with its own pipeline settings
      6. Join processed scenes back together
    """

    def __init__(
        self,
        base_config: dict,
        scene_threshold: float = 0.3,
        min_scene_duration: float = 1.0,
    ):
        self.base_config = base_config
        self.scene_threshold = scene_threshold
        self.min_scene_duration = min_scene_duration

    def run(self, input_path: Path, output_path: Path) -> Path:
        from .scene_detect import detect_scenes, split_video, join_segments
        from .analyze import analyze_scenes
        from .adaptive import generate_scene_configs, apply_overrides

        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        logger.info("=" * 60)
        logger.info("ADAPTIVE PIPELINE")
        logger.info("=" * 60)

        # Phase 1: Detect scenes
        logger.info("\n--- Phase 1: Scene Detection ---")
        scenes = detect_scenes(
            input_path,
            threshold=self.scene_threshold,
            min_duration=self.min_scene_duration,
        )

        if len(scenes) <= 1:
            logger.info("Single scene detected — running standard pipeline")
            pipeline = Pipeline(self.base_config)
            return pipeline.run(input_path, output_path)

        # Phase 2: Analyze scenes
        logger.info("\n--- Phase 2: Scene Analysis ---")
        scenes = analyze_scenes(input_path, scenes)

        # Phase 3: Generate per-scene configs
        logger.info("\n--- Phase 3: Adaptive Config Generation ---")
        scenes = generate_scene_configs(scenes)

        # Phase 4: Split, process, join
        logger.info("\n--- Phase 4: Processing ---")
        temp_dir = tempfile.mkdtemp(prefix="vhs_adaptive_")
        temp_dir_path = Path(temp_dir)

        try:
            segments_dir = temp_dir_path / "segments"
            processed_dir = temp_dir_path / "processed"
            segments_dir.mkdir()
            processed_dir.mkdir()

            # Split video into scene segments
            segment_paths = split_video(input_path, scenes, segments_dir)

            # Process each scene with its own settings
            processed_paths = []
            for scene, segment_path in zip(scenes, segment_paths):
                logger.info(f"\n--- Processing Scene {scene.index} ({scene.duration:.1f}s) ---")

                # Build scene-specific config
                scene_config = apply_overrides(self.base_config, scene.config_overrides)
                scene_pipeline = Pipeline(scene_config)

                # Log what's different for this scene
                if scene.config_overrides:
                    logger.info(f"  Overrides: {_summarize_overrides(scene.config_overrides)}")

                processed_path = processed_dir / f"scene_{scene.index:03d}.mp4"
                scene_pipeline.run(segment_path, processed_path)
                processed_paths.append(processed_path)

            # Join all processed scenes
            logger.info(f"\n--- Phase 5: Joining {len(processed_paths)} scenes ---")
            join_segments(processed_paths, output_path)

            logger.info(f"\nAdaptive pipeline complete → {output_path}")
            return output_path

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _summarize_overrides(overrides: dict) -> str:
    """One-line summary of config overrides for logging."""
    parts = []
    if "denoise" in overrides:
        d = overrides["denoise"]
        parts.append(f"denoise={d.get('mode', '?')}/{d.get('strength', '?')}")
    if "sharpen" in overrides:
        s = overrides["sharpen"]
        if s.get("enabled", True):
            parts.append(f"sharpen={s.get('strength', 'on')}")
        else:
            parts.append("sharpen=off")
    if "color" in overrides:
        c = overrides["color"]
        if c.get("saturation", 1.0) != 1.0:
            parts.append(f"sat={c['saturation']}")
    return ", ".join(parts) or "defaults"
