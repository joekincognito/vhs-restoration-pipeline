"""Scene detection — finds cut points in video using FFmpeg's scene filter.

Analyzes frame-to-frame differences to detect scene changes. Returns a list
of scene segments with start/end timestamps that can be processed independently.

VHS tapes often have:
- Hard cuts between recordings
- Tracking errors that look like scene changes (filtered by min_duration)
- Fade-to-black transitions
- Long continuous shots (home video)
"""

import logging
import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Scene:
    """A single scene segment."""
    index: int
    start: float       # seconds
    end: float         # seconds
    duration: float    # seconds

    # Filled in by analyze step
    metrics: dict = field(default_factory=dict)
    config_overrides: dict = field(default_factory=dict)

    def __repr__(self):
        return f"Scene({self.index}, {self.start:.2f}s-{self.end:.2f}s, {self.duration:.2f}s)"


def get_video_duration(input_path: Path) -> float:
    """Get total video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def detect_scenes(
    input_path: Path,
    threshold: float = 0.3,
    min_duration: float = 1.0,
) -> list[Scene]:
    """Detect scene boundaries in a video.

    Args:
        input_path: Path to input video file.
        threshold: Scene change detection sensitivity (0.0-1.0).
                   Lower = more sensitive (more scene breaks detected).
                   0.3 is good for VHS. Use 0.2 for faded footage, 0.4 for clean.
        min_duration: Minimum scene duration in seconds. Scenes shorter than this
                      are merged with the previous scene. Filters out tracking
                      errors and brief glitches common on VHS.

    Returns:
        List of Scene objects with start/end timestamps.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    total_duration = get_video_duration(input_path)
    logger.info(f"Video duration: {total_duration:.2f}s")

    # Use FFmpeg's select filter to detect scene changes
    # showinfo prints frame metadata including pts_time
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]

    logger.info(f"Detecting scenes (threshold={threshold}, min_duration={min_duration}s)...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse scene change timestamps from showinfo output in stderr
    # Lines look like: [Parsed_showinfo_1 @ ...] n: 123 pts: 12345 pts_time:4.567 ...
    timestamps = [0.0]  # Always start at 0
    for line in result.stderr.split("\n"):
        match = re.search(r"pts_time:\s*([\d.]+)", line)
        if match:
            ts = float(match.group(1))
            timestamps.append(ts)

    timestamps.append(total_duration)  # Always end at video end

    # Remove duplicates and sort
    timestamps = sorted(set(timestamps))

    # Build scene list, merging short scenes
    scenes = []
    i = 0
    while i < len(timestamps) - 1:
        start = timestamps[i]
        end = timestamps[i + 1]
        duration = end - start

        # If scene is too short, extend it to include the next segment
        while duration < min_duration and i + 2 < len(timestamps):
            i += 1
            end = timestamps[i + 1]
            duration = end - start

        scenes.append(Scene(
            index=len(scenes),
            start=start,
            end=end,
            duration=duration,
        ))
        i += 1

    logger.info(f"Detected {len(scenes)} scenes")
    for scene in scenes:
        logger.info(f"  {scene}")

    return scenes


def split_video(input_path: Path, scenes: list[Scene], output_dir: Path) -> list[Path]:
    """Split video into scene segments using FFmpeg.

    Uses stream copy (no re-encoding) for speed. Each segment is written
    as a separate file that can be processed independently.

    Returns list of paths to segment files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    segment_paths = []
    suffix = Path(input_path).suffix or ".mp4"

    for scene in scenes:
        segment_path = output_dir / f"scene_{scene.index:03d}{suffix}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-ss", f"{scene.start:.6f}",
            "-to", f"{scene.end:.6f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(segment_path),
        ]

        logger.debug(f"Splitting scene {scene.index}: {scene.start:.2f}s - {scene.end:.2f}s")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Failed to split scene {scene.index}: {result.stderr[-500:]}")
            raise RuntimeError(f"Scene split failed for scene {scene.index}")

        segment_paths.append(segment_path)

    logger.info(f"Split into {len(segment_paths)} segments in {output_dir}")
    return segment_paths


def join_segments(segment_paths: list[Path], output_path: Path) -> Path:
    """Concatenate processed scene segments back into a single video.

    Uses FFmpeg's concat demuxer for frame-accurate joining.
    """
    import tempfile

    # Write concat file list
    concat_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="concat_"
    )
    for path in segment_paths:
        # FFmpeg concat needs forward slashes and escaped quotes
        safe_path = str(path).replace("\\", "/")
        concat_file.write(f"file '{safe_path}'\n")
    concat_file.close()

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file.name,
            "-c", "copy",
            str(output_path),
        ]

        logger.info(f"Joining {len(segment_paths)} segments → {output_path.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Join failed: {result.stderr[-500:]}")
            raise RuntimeError("Failed to join scene segments")

    finally:
        Path(concat_file.name).unlink(missing_ok=True)

    logger.info(f"Joined → {output_path}")
    return output_path
