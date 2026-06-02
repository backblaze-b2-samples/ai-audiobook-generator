"""ffmpeg adapter for assembling a chapterized M4B master.

ffmpeg is an external tool, so (like boto3 and the TTS SDKs) it is contained in
the repo/ layer. It is invoked via subprocess. The assembler concatenates the
per-chapter MP3 renders and embeds chapter markers so players show a chapter
list and seekable boundaries.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioAssemblyError(Exception):
    """Raised when ffmpeg is unavailable or master assembly fails."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _format_ts(seconds: float) -> int:
    """ffmpeg metadata chapter timestamps are in milliseconds (TIMEBASE 1/1000)."""
    return round(seconds * 1000)


def _build_chapter_metadata(chapters: list[tuple[str, float]]) -> str:
    """Build an ffmpeg metadata file describing chapter markers.

    `chapters` is an ordered list of (title, duration_seconds).
    """
    lines = [";FFMETADATA1"]
    cursor = 0
    for title, duration in chapters:
        start = _format_ts(cursor)
        cursor += duration
        end = _format_ts(cursor)
        safe_title = title.replace("=", " ").replace(";", " ").replace("#", " ")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start}")
        lines.append(f"END={end}")
        lines.append(f"title={safe_title}")
    return "\n".join(lines) + "\n"


def assemble_master(
    chapter_audio: list[bytes],
    chapter_meta: list[tuple[str, float]],
) -> bytes:
    """Concatenate chapter MP3s into a chapterized M4B and return its bytes.

    `chapter_audio` and `chapter_meta` are parallel ordered lists. Raises
    AudioAssemblyError if ffmpeg is missing or the encode fails.
    """
    if not ffmpeg_available():
        raise AudioAssemblyError(
            "ffmpeg is not installed — cannot assemble the M4B master."
        )
    if not chapter_audio:
        raise AudioAssemblyError("No chapter audio to assemble.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp3_paths: list[Path] = []
        for i, data in enumerate(chapter_audio):
            p = tmp_path / f"ch-{i:03d}.mp3"
            p.write_bytes(data)
            mp3_paths.append(p)

        concat_list = tmp_path / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.name}'" for p in mp3_paths) + "\n"
        )

        meta_file = tmp_path / "chapters.txt"
        meta_file.write_text(_build_chapter_metadata(chapter_meta))

        out_path = tmp_path / "master.m4b"
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "concat.txt",
            "-i",
            "chapters.txt",
            "-map_metadata",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "mp4",
            "master.m4b",
        ]
        result = subprocess.run(
            cmd,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not out_path.exists():
            logger.error("ffmpeg master assembly failed: %s", result.stderr[-2000:])
            raise AudioAssemblyError(
                f"ffmpeg exited with code {result.returncode} during assembly."
            )
        return out_path.read_bytes()
