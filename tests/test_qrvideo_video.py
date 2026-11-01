"""Integration: echte MP4-Dateien ueber ffmpeg (imageio-ffmpeg)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from qrvideo import decode_video, encode_file
from qrvideo.videoio import VideoSettings, read_video, write_video

pytestmark = pytest.mark.integration

# Thesis-Video von 2019 samt .pgp daneben; liegt nicht im Repo (live/ ist gitignored, Video-ID nur lokal)
THESIS_VIDEO = Path(
    os.environ.get("QRVIDEO_THESIS_VIDEO", Path(__file__).parent.parent / "live" / "thesis_1080p.mp4")
)


@pytest.mark.parametrize("crf", [0, 23])
def test_file_roundtrip_through_h264(tmp_path: Path, crf: int) -> None:
    source = tmp_path / "nutzlast.gpg"
    source.write_bytes(os.urandom(150_000))
    video = tmp_path / "video.mp4"
    frames = encode_file(source, video, workers=2, settings=VideoSettings(crf=crf, preset="veryfast"))
    data, report = decode_video(video)
    assert data == source.read_bytes()
    assert report.frames == frames == 5
    assert report.failures == []


def test_write_requires_frames(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_video(tmp_path / "leer.mp4", [])
    with pytest.raises(FileNotFoundError):
        next(read_video(tmp_path / "fehlt.mp4"))


@pytest.mark.skipif(not THESIS_VIDEO.is_file(), reason="Thesis-Video nicht vorhanden")
def test_original_thesis_youtube_video() -> None:
    """Orakel: das 2019 von YouTube geladene Video und die damals daraus dekodierte PGP-Datei."""
    expected = THESIS_VIDEO.with_suffix(".pgp").read_bytes()
    data, report = decode_video(THESIS_VIDEO, legacy=True)
    # Die Thesis schrieb die .pgp im Windows-Textmodus (\n -> \r\n)
    assert data.replace(b"\n", b"\r\n") == expected
    assert report.frames == 90
    assert report.qr_codes == 90 + 1197
    assert report.failures == []
