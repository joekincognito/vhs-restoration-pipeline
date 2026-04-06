"""Command-line interface for the VHS restoration pipeline."""

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load_config, PRESETS_DIR
from .pipeline import Pipeline


def get_available_presets() -> list[str]:
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    presets = get_available_presets()

    parser = argparse.ArgumentParser(
        prog="vhs-restore",
        description="VHS Restoration Pipeline — modular video restoration for digitized VHS footage",
    )
    parser.add_argument("input", help="Input video file")
    parser.add_argument(
        "-o", "--output",
        help="Output video file (default: <input>_restored.mp4)",
    )
    parser.add_argument(
        "-p", "--preset",
        default="balanced",
        choices=presets,
        help=f"Processing preset (default: balanced). Available: {presets}",
    )
    parser.add_argument(
        "-c", "--config",
        help="Custom JSON config file (overrides preset settings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without processing",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check dependencies and exit",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Step toggles — override preset
    toggle = parser.add_argument_group("step toggles (override preset)")
    toggle.add_argument("--no-deinterlace", action="store_true", help="Skip deinterlacing")
    toggle.add_argument("--no-denoise", action="store_true", help="Skip denoising")
    toggle.add_argument("--no-stabilize", action="store_true", help="Skip stabilization")
    toggle.add_argument("--no-color", action="store_true", help="Skip color correction")
    toggle.add_argument("--no-upscale", action="store_true", help="Skip upscaling")
    toggle.add_argument("--stabilize", action="store_true", help="Force enable stabilization")
    toggle.add_argument("--upscale", action="store_true", help="Force enable upscaling")
    toggle.add_argument("--color", action="store_true", help="Force enable color correction")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
    )

    # Resolve paths
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        logging.error(f"Input file not found: {args.input}")
        return 1

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = input_path.with_stem(input_path.stem + "_restored").with_suffix(".mp4")

    # Load config
    try:
        config = load_config(preset=args.preset, config_file=args.config)
    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        return 1

    # Apply CLI step toggles
    if args.no_deinterlace:
        config["deinterlace"]["enabled"] = False
    if args.no_denoise:
        config["denoise"]["enabled"] = False
    if args.no_stabilize:
        config["stabilize"]["enabled"] = False
    if args.no_color:
        config["color"]["enabled"] = False
    if args.no_upscale:
        config["upscale"]["enabled"] = False
    if args.stabilize:
        config["stabilize"]["enabled"] = True
    if args.upscale:
        config["upscale"]["enabled"] = True
    if args.color:
        config["color"]["enabled"] = True

    # Build pipeline
    pipeline = Pipeline(config)

    # Dependency check
    if args.check:
        issues = pipeline.check_dependencies()
        if issues:
            logging.error("Missing dependencies:")
            for step, deps in issues.items():
                logging.error(f"  {step}: {', '.join(deps)}")
            return 1
        else:
            logging.info("All dependencies satisfied!")
            return 0

    # Dry run
    if args.dry_run:
        print(f"\nPreset: {args.preset}")
        if args.config:
            print(f"Custom config: {args.config}")
        print(f"Input:  {input_path}")
        print(f"Output: {output_path}")
        print()
        print(pipeline.describe())
        return 0

    # Run pipeline
    try:
        pipeline.run(input_path, output_path)
        return 0
    except Exception as e:
        logging.error(f"\nPipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
