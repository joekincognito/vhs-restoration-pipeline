"""Quick test run against a real file."""

import os
import sys
import logging

# Add ffmpeg to PATH for this session
ffmpeg_bin = r"C:\Users\joeki\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ["PATH"]

from vhs_restore.config import load_config
from vhs_restore.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")

input_file = r"C:\Users\joeki\Videos\V 2 OBS.mkv"
output_file = r"C:\Users\joeki\Videos\V 2 OBS_balanced_v2.mp4"

config = load_config(preset="balanced")
config["deinterlace"]["enabled"] = False  # already progressive from OBS capture
config["upscale"]["enabled"] = False      # GT 730 can't handle Real-ESRGAN reliably

print(f"Input:  {input_file}")
print(f"Output: {output_file}")
print()

pipeline = Pipeline(config)
print(pipeline.describe())
print()

pipeline.run(input_file, output_file)
print("\nDone!")
