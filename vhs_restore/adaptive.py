"""Adaptive config mapper — translates scene metrics into per-scene filter settings.

Takes the analysis results from analyze.py and generates config overrides
for each scene. This is the "brain" that decides how aggressively to process
each part of the video.

Design principles:
- Clean scenes get minimal processing (preserve detail)
- Noisy scenes get stronger denoise (but not stronger sharpen — that amplifies noise)
- Dark scenes get reduced denoise (dark areas are destroyed by aggressive filtering)
- High-motion scenes favor temporal denoise (hqdn3d) over spatial (nlmeans)
- Still scenes can use nlmeans (slow but better detail preservation)
- Color correction is light everywhere — just normalize, don't overcorrect
"""

import logging
from .scene_detect import Scene

logger = logging.getLogger(__name__)


def generate_scene_configs(scenes: list[Scene], base_preset: str = "balanced") -> list[Scene]:
    """Generate per-scene config overrides based on analysis metrics.

    Each scene gets config_overrides dict that layers on top of the base preset.
    Only settings that differ from the base are included.

    Returns the same scene list with config_overrides populated.
    """
    logger.info(f"Generating adaptive configs for {len(scenes)} scenes...")

    for scene in scenes:
        m = scene.metrics
        if not m:
            logger.warning(f"  Scene {scene.index}: no metrics, using defaults")
            continue

        overrides = {}
        noise = m.get("noise_level", 30)
        noise_cat = m.get("noise_category", "light")
        brightness = m.get("brightness", 128)
        brightness_cat = m.get("brightness_category", "normal")
        motion = m.get("motion", 10)
        motion_cat = m.get("motion_category", "low")
        saturation = m.get("saturation", 50)

        # --- DENOISE ---
        denoise = {}

        if noise_cat == "clean":
            # Barely any noise — very light denoise or skip
            denoise["mode"] = "hqdn3d"
            denoise["strength"] = "light"
        elif noise_cat == "light":
            # Light noise — hqdn3d is fast and sufficient
            denoise["mode"] = "hqdn3d"
            denoise["strength"] = "medium"
        elif noise_cat == "moderate":
            # Moderate noise — use nlmeans for still/low-motion, hqdn3d for action
            if motion_cat in ("still", "low"):
                denoise["mode"] = "nlmeans"
                denoise["strength"] = "medium"
            else:
                denoise["mode"] = "hqdn3d"
                denoise["strength"] = "heavy"
        else:
            # Heavy noise — go aggressive but watch for dark scenes
            if brightness_cat == "dark":
                # Dark + noisy: nlmeans medium (heavy would destroy shadow detail)
                denoise["mode"] = "nlmeans"
                denoise["strength"] = "medium"
            elif motion_cat in ("still", "low"):
                denoise["mode"] = "nlmeans"
                denoise["strength"] = "heavy"
            else:
                denoise["mode"] = "hqdn3d"
                denoise["strength"] = "heavy"

        overrides["denoise"] = denoise

        # --- SHARPEN ---
        sharpen = {"enabled": True}

        if noise_cat in ("moderate", "heavy"):
            # Don't sharpen noisy footage — it amplifies the noise
            sharpen["enabled"] = False
        elif noise_cat == "light":
            sharpen["strength"] = "light"
        else:
            # Clean footage — can sharpen more aggressively
            sharpen["strength"] = "medium"

        overrides["sharpen"] = sharpen

        # --- COLOR ---
        color = {"enabled": True, "auto_levels": True}

        if saturation < 30:
            # Very desaturated — boost more
            color["saturation"] = 1.2
        elif saturation < 50:
            # Typical faded VHS
            color["saturation"] = 1.1
        else:
            # Already decent saturation
            color["saturation"] = 1.0

        if brightness_cat == "dark":
            color["gamma"] = 1.1
            color["brightness"] = 0.03
        elif brightness_cat == "bright":
            color["gamma"] = 0.95

        overrides["color"] = color

        scene.config_overrides = overrides

        logger.info(
            f"  Scene {scene.index}: "
            f"denoise={denoise.get('mode', '?')}/{denoise.get('strength', '?')} "
            f"sharpen={'on' if sharpen.get('enabled') else 'off'} "
            f"sat_boost={color.get('saturation', 1.0)}"
        )

    return scenes


def apply_overrides(base_config: dict, overrides: dict) -> dict:
    """Apply scene-specific overrides to a base config.

    Returns a new config dict (doesn't modify base).
    """
    import json
    config = json.loads(json.dumps(base_config))  # deep copy

    for step_name, step_overrides in overrides.items():
        if step_name in config:
            config[step_name].update(step_overrides)
        else:
            config[step_name] = step_overrides

    return config
