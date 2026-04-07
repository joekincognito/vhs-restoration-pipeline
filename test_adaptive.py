"""Test the adaptive pipeline on real VHS footage."""

import os
import logging

# Add ffmpeg to PATH for this session
ffmpeg_bin = r"C:\Users\joeki\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ["PATH"]

from vhs_restore.config import load_config
from vhs_restore.pipeline import AdaptivePipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")

input_file = r"C:\Users\joeki\Videos\rg2.mpg"
output_file = r"C:\Users\joeki\Videos\rg2_adaptive.mp4"

# Use balanced as base — this file is interlaced so we need deinterlace on
# Adaptive will override denoise/sharpen/color per-scene
config = load_config(preset="balanced")
config["upscale"]["enabled"] = False  # GT 730 can't handle Real-ESRGAN

pipeline = AdaptivePipeline(
    base_config=config,
    scene_threshold=0.3,
    min_scene_duration=1.0,
)

print(f"Input:  {input_file}")
print(f"Output: {output_file}")
print()

pipeline.run(input_file, output_file)
print("\nDone!")
