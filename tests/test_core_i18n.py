"""Meldungen des Kerns, die CLI und GUI dem Nutzer zeigen, folgen der Sprache (ADR-006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qrvideo import channel, youtube
from qrvideo.container import ContainerError, assemble, plan_frames
from qrvideo.handshake import HandshakeError, parse
from qrvideo.i18n import set_language
from qrvideo.qrpng import read_png
from qrvideo.videoio import outdated_ffmpeg_warning


def test_channel_errors_follow_the_language() -> None:
    set_language("es")
    with pytest.raises(ValueError, match="^El canal de carpeta necesita --folder$"):
        channel.make_channel("folder")
    set_language("en")
    with pytest.raises(ValueError, match="^--cookies-from-browser only applies to YouTube$"):
        channel.make_channel("folder", folder=Path("."), cookies_from_browser=("firefox",))


def test_youtube_errors_follow_the_language() -> None:
    set_language("es")
    with pytest.raises(ValueError, match="^No se reconoce ningún ID de vídeo de YouTube: 'x'$"):
        youtube.parse_video_id("x")
    set_language("en")
    with pytest.raises(ValueError, match="^Unknown browser or invalid profile 'netscape'"):
        youtube.parse_browser_spec("netscape")


def test_visibility_notice_translates_the_privacy_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(youtube, "upload", lambda *a, **kw: youtube.Uploaded("PRIVATE0001", "private"))
    set_language("es")
    notice = channel.YouTubeChannel(tmp_path / "secrets.json").publish(tmp_path / "v.mp4", "t").notice
    assert notice is not None and notice.startswith('YouTube guardó el vídeo como "privado"')
    set_language("de")
    notice = channel.YouTubeChannel(tmp_path / "secrets.json").publish(tmp_path / "v.mp4", "t").notice
    assert notice is not None and notice.startswith('YouTube hat das Video als "privat" gespeichert')


def test_ffmpeg_warning_follows_the_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    set_language("en")
    assert outdated_ffmpeg_warning("7.1") == (
        "Note: the bundled FFmpeg 7.1 is older than 8; for videos from the internet set IMAGEIO_FFMPEG_EXE "
        "to a current FFmpeg."
    )


def test_format_and_handshake_errors_follow_the_language(tmp_path: Path) -> None:
    payload = bytes(2331 * 3)
    plan = plan_frames(payload)[0]
    chunks = dict(enumerate(plan.chunks))
    not_png = tmp_path / "bild.png"
    not_png.write_bytes(b"GIF89a")
    set_language("es")
    with pytest.raises(ContainerError, match="^Faltan 1 fragmentos, el primero que falta: 1$"):
        assemble(plan.header, {k: v for k, v in chunks.items() if k != 1})
    with pytest.raises(HandshakeError, match="^No es JSON$"):
        parse(b"\xff")
    with pytest.raises(ValueError, match="no es un archivo PNG$"):
        read_png(not_png)
    set_language("en")
    with pytest.raises(ContainerError, match="^SHA-256 of the payload does not match$"):
        assemble(plan.header, {**chunks, 0: bytes(2330) + b"\x01"})
