"""Videos schreiben und lesen ueber eine ffmpeg-Pipe (imageio-ffmpeg bringt das Binary mit).

Die Thesis sammelte alle Frames im RAM und schrieb 5-Sekunden-Segmente per Thread (POC.py
write_video_file_segment). Hier fliessen die Frames einzeln durch die Pipe.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import numpy.typing as npt

from .i18n import _


@dataclass(frozen=True)
class VideoSettings:
    fps: int = 30
    crf: int = 12  # 0 = verlustfrei; YouTube kodiert ohnehin neu
    preset: str = "medium"
    extra: tuple[str, ...] = field(default=("-bf", "2", "-g", "15", "-movflags", "+faststart"))

    @property
    def profile(self) -> str:
        """Verlustfreies H.264 (crf 0) gibt es nur im Profil high444 - deshalb setzte die Thesis es."""
        return "high444" if self.crf == 0 else "high"


DEFAULT_SETTINGS = VideoSettings()


def write_video(
    path: Path, frames: Iterable[npt.NDArray[np.uint8]], settings: VideoSettings = DEFAULT_SETTINGS
) -> int:
    """Schreibt Graustufen-Frames als H.264/yuv420p-MP4. Rueckgabe: Anzahl Frames.

    Geschrieben wird in `<name>.part<endung>` und erst nach Erfolg umbenannt; ein Abbruch hinterlaesst kein
    halbes, scheinbar gueltiges Video (Code-Review #13).
    """
    iterator = iter(frames)
    first = next(iterator, None)
    if first is None:
        raise ValueError("Keine Frames zum Schreiben")
    height, width = first.shape
    partial = path.with_name(f"{path.stem}.part{path.suffix}")
    writer = imageio_ffmpeg.write_frames(
        str(partial),
        (width, height),
        pix_fmt_in="gray",
        pix_fmt_out="yuv420p",
        fps=settings.fps,
        codec="libx264",
        quality=None,
        macro_block_size=8,
        output_params=[
            "-crf",
            str(settings.crf),
            "-preset",
            settings.preset,
            "-profile:v",
            settings.profile,
            *settings.extra,
        ],
    )
    writer.send(None)
    count = 0
    try:
        for frame in _chain(first, iterator):
            writer.send(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
            count += 1
    except BaseException:
        writer.close()
        partial.unlink(missing_ok=True)
        raise
    writer.close()
    os.replace(partial, path)
    return count


def _chain(
    first: npt.NDArray[np.uint8], rest: Iterator[npt.NDArray[np.uint8]]
) -> Iterator[npt.NDArray[np.uint8]]:
    yield first
    yield from rest


MIN_FFMPEG_MAJOR = 8  # Decoder-Fixes aus security/DEPENDENCY_AUDIT.md (2026-10-26) erst ab 8.1.3


def ffmpeg_version() -> str:
    """Version des FFmpeg, das imageio-ffmpeg benutzt (gebuendelt oder IMAGEIO_FFMPEG_EXE)."""
    out = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-version"], capture_output=True, text=True, check=True
    )
    match = re.match(r"ffmpeg version n?(\S+)", out.stdout)
    return match.group(1) if match else "unbekannt"


def outdated_ffmpeg_warning(version: str | None = None) -> str | None:
    """Hinweis, wenn fremde Videos mit einem gebuendelten FFmpeg < 8 geoeffnet werden (STATE-Risiko, T4)."""
    if os.environ.get("IMAGEIO_FFMPEG_EXE"):
        return None
    version = version or ffmpeg_version()
    major = re.match(r"(\d+)", version)
    if major and int(major.group(1)) >= MIN_FFMPEG_MAJOR:
        return None
    text = _(
        "Note: the bundled FFmpeg {version} is older than {major}; for videos from the internet set "
        "IMAGEIO_FFMPEG_EXE to a current FFmpeg."
    )
    return text.format(version=version, major=MIN_FFMPEG_MAJOR)


def read_video(path: Path) -> Iterator[npt.NDArray[np.uint8]]:
    """Liefert die Frames eines Videos als Graustufen-Arrays (Luma, wie die Thesis Kanal 1 nutzte)."""
    if not path.is_file():
        raise FileNotFoundError(path)
    # Nur MP4/MOV-Demuxer und lokale Dateien: sonst liest ffmpeg z. B. ein ffconcat-Skript namens .mp4 und
    # oeffnet die darin genannten Dateien (Code-Review #10, reproduziert)
    reader = imageio_ffmpeg.read_frames(
        str(path),
        pix_fmt="gray",
        bpp=1,
        input_params=["-f", "mov,mp4,m4a,3gp,3g2,mj2", "-protocol_whitelist", "file"],
    )
    try:
        meta = next(reader)
        width, height = meta["size"]
        for raw in reader:
            yield np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
    finally:
        reader.close()
