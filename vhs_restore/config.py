"""Configuration management — loads presets and custom config files."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent / "presets"

# Default pipeline configuration
DEFAULT_CONFIG = {
    "deinterlace": {
        "enabled": True,
        "mode": "bwdif",
        "parity": 0,
    },
    "denoise": {
        "enabled": True,
        "mode": "hqdn3d",
        "strength": "medium",
    },
    "sharpen": {
        "enabled": False,
        "strength": "light",
    },
    "stabilize": {
        "enabled": False,
        "smoothing": 10,
        "crop": "keep",
        "zoom": 0,
        "optzoom": 2,
    },
    "color": {
        "enabled": False,
        "auto_levels": True,
        "saturation": 1.0,
        "contrast": 1.0,
        "brightness": 0.0,
        "gamma": 1.0,
    },
    "upscale": {
        "enabled": False,
        "scale": 2,
        "model": "realesrgan-x4plus",
        "fallback_to_lanczos": True,
    },
}

# Ordered list of steps (this determines pipeline execution order)
STEP_ORDER = ["deinterlace", "denoise", "sharpen", "stabilize", "color", "upscale"]


def load_preset(name: str) -> dict:
    """Load a named preset from the presets directory."""
    preset_path = PRESETS_DIR / f"{name}.json"
    if not preset_path.exists():
        available = [p.stem for p in PRESETS_DIR.glob("*.json")]
        raise FileNotFoundError(
            f"Preset '{name}' not found. Available: {available}"
        )

    with open(preset_path) as f:
        preset = json.load(f)

    logger.info(f"Loaded preset: {name}")
    return preset


def load_config(preset: str = "safe", config_file: str | None = None) -> dict:
    """Build final configuration by merging defaults → preset → custom config.

    Priority (highest wins): custom config > preset > defaults
    """
    # Start with defaults
    config = _deep_copy(DEFAULT_CONFIG)

    # Layer preset on top
    preset_config = load_preset(preset)
    _deep_merge(config, preset_config)

    # Layer custom config file on top (if provided)
    if config_file:
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_path) as f:
            custom = json.load(f)
        _deep_merge(config, custom)
        logger.info(f"Applied custom config: {config_file}")

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (modifies base in-place)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _deep_copy(d: dict) -> dict:
    """Simple deep copy for nested dicts with primitive values."""
    return json.loads(json.dumps(d))
