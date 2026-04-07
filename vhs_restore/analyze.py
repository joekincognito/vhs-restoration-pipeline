"""Video analysis — measures noise, brightness, and motion per scene.

Runs FFmpeg's signalstats filter to extract quality metrics, then
summarizes them per-scene to inform adaptive filter settings.

Key metrics:
  YMIN/YMAX/YAVG  — luma (brightness) min/max/average
  YDIF            — frame-to-frame luma difference (motion indicator)
  SATAVG          — average saturation
  HUEAVG          — average hue
  TOUT            — temporal outlier count (noise indicator)
"""

import logging
import subprocess
import re
from pathlib import Path
from dataclasses import dataclass

from .scene_detect import Scene

logger = logging.getLogger(__name__)


@dataclass
class SceneMetrics:
    """Analysis results for a single scene."""
    noise_level: float      # 0-100, higher = noisier
    brightness: float       # 0-255, average luma
    motion: float           # 0-100, higher = more movement
    saturation: float       # 0-100, average saturation
    contrast_range: float   # 0-255, difference between darkest and brightest

    @property
    def noise_category(self) -> str:
        if self.noise_level < 15:
            return "clean"
        elif self.noise_level < 35:
            return "light"
        elif self.noise_level < 60:
            return "moderate"
        else:
            return "heavy"

    @property
    def brightness_category(self) -> str:
        if self.brightness < 50:
            return "dark"
        elif self.brightness < 170:
            return "normal"
        else:
            return "bright"

    @property
    def motion_category(self) -> str:
        if self.motion < 5:
            return "still"
        elif self.motion < 20:
            return "low"
        elif self.motion < 50:
            return "moderate"
        else:
            return "high"


def analyze_scene(input_path: Path, scene: Scene) -> SceneMetrics:
    """Analyze a scene segment using FFmpeg signalstats.

    Samples frames across the scene and computes aggregate metrics.
    """
    # Run signalstats on the scene's time range
    # Sample every 5th frame to keep analysis fast
    cmd = [
        "ffmpeg",
        "-ss", f"{scene.start:.6f}",
        "-to", f"{scene.end:.6f}",
        "-i", str(input_path),
        "-vf", "select='not(mod(n\\,5))',signalstats=stat=tout+vrep+brng,metadata=print:file=-",
        "-f", "null", "-",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse metrics from stdout (metadata print output)
    yavg_values = []
    ymin_values = []
    ymax_values = []
    ydif_values = []
    satavg_values = []
    tout_values = []

    for line in result.stdout.split("\n"):
        # Lines look like: lavfi.signalstats.YAVG=128.45
        if "signalstats.YAVG=" in line:
            val = _extract_value(line)
            if val is not None:
                yavg_values.append(val)
        elif "signalstats.YMIN=" in line:
            val = _extract_value(line)
            if val is not None:
                ymin_values.append(val)
        elif "signalstats.YMAX=" in line:
            val = _extract_value(line)
            if val is not None:
                ymax_values.append(val)
        elif "signalstats.YDIF=" in line:
            val = _extract_value(line)
            if val is not None:
                ydif_values.append(val)
        elif "signalstats.SATAVG=" in line:
            val = _extract_value(line)
            if val is not None:
                satavg_values.append(val)
        elif "signalstats.TOUT=" in line:
            val = _extract_value(line)
            if val is not None:
                tout_values.append(val)

    # Also parse from stderr as fallback (some FFmpeg versions output there)
    if not yavg_values:
        for line in result.stderr.split("\n"):
            if "YAVG" in line:
                val = _extract_value(line)
                if val is not None:
                    yavg_values.append(val)
            elif "YDIF" in line:
                val = _extract_value(line)
                if val is not None:
                    ydif_values.append(val)
            elif "SATAVG" in line:
                val = _extract_value(line)
                if val is not None:
                    satavg_values.append(val)
            elif "TOUT" in line:
                val = _extract_value(line)
                if val is not None:
                    tout_values.append(val)

    # Compute aggregates (use safe defaults if no data)
    avg_brightness = _safe_avg(yavg_values, default=128.0)
    avg_motion = _safe_avg(ydif_values, default=10.0)
    avg_saturation = _safe_avg(satavg_values, default=50.0)
    avg_tout = _safe_avg(tout_values, default=0.02)

    # Contrast range: average of (YMAX - YMIN) per frame
    if ymin_values and ymax_values:
        contrast_range = _safe_avg(ymax_values) - _safe_avg(ymin_values)
    else:
        contrast_range = 200.0

    # Noise estimation: TOUT (temporal outlier ratio) is our best noise proxy.
    # TOUT ranges 0.0-1.0 where higher = more temporal outliers = more noise.
    # Scale to 0-100 for easier reasoning.
    noise_level = min(avg_tout * 200, 100.0)  # 0.5 TOUT → 100 noise

    metrics = SceneMetrics(
        noise_level=noise_level,
        brightness=avg_brightness,
        motion=avg_motion,
        saturation=avg_saturation,
        contrast_range=contrast_range,
    )

    return metrics


def analyze_scenes(input_path: Path, scenes: list[Scene]) -> list[Scene]:
    """Analyze all scenes and attach metrics to each Scene object.

    Returns the same scene list with metrics populated.
    """
    input_path = Path(input_path)
    logger.info(f"Analyzing {len(scenes)} scenes...")

    for scene in scenes:
        logger.info(f"  Analyzing scene {scene.index} ({scene.duration:.1f}s)...")
        metrics = analyze_scene(input_path, scene)
        scene.metrics = {
            "noise_level": metrics.noise_level,
            "noise_category": metrics.noise_category,
            "brightness": metrics.brightness,
            "brightness_category": metrics.brightness_category,
            "motion": metrics.motion,
            "motion_category": metrics.motion_category,
            "saturation": metrics.saturation,
            "contrast_range": metrics.contrast_range,
        }
        logger.info(
            f"    noise={metrics.noise_category}({metrics.noise_level:.1f}) "
            f"brightness={metrics.brightness_category}({metrics.brightness:.0f}) "
            f"motion={metrics.motion_category}({metrics.motion:.1f}) "
            f"saturation={metrics.saturation:.0f}"
        )

    return scenes


def _extract_value(line: str) -> float | None:
    """Extract numeric value from a signalstats metadata line."""
    match = re.search(r"=(-?[\d.]+)", line)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _safe_avg(values: list[float], default: float = 0.0) -> float:
    """Average of a list, with a default if empty."""
    if not values:
        return default
    return sum(values) / len(values)
