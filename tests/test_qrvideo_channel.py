"""Kanal-Schnittstelle (ADR-005): YouTube-Adapter ohne Netz, Ordner-Kanal auf echter Platte."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from qrvideo import youtube
from qrvideo.channel import (
    CHANNEL_NAMES,
    Channel,
    FolderChannel,
    Published,
    YouTubeChannel,
    channel_ref,
    make_channel,
    parse_channel_ref,
)


class FakeYdl:
    def __init__(self, options: dict[str, Any]) -> None:
        self.home = Path(options["paths"]["home"])

    def __enter__(self) -> FakeYdl:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool) -> dict[str, str]:
        return {"id": url.rsplit("=", 1)[-1], "ext": "mp4"}

    def prepare_filename(self, info: dict[str, str]) -> str:
        target = self.home / f"{info['id']}.mp4"
        target.write_bytes(b"video")
        return str(target)


def _video(tmp_path: Path, content: bytes = b"qr-video") -> Path:
    video = tmp_path / "Gehaltsliste Mueller.mp4"
    video.write_bytes(content)
    return video


def test_youtube_channel_reads_links_and_fetches_by_id(tmp_path: Path) -> None:
    channel: Channel = YouTubeChannel(ydl_class=FakeYdl)
    ref = channel.parse_ref("https://www.youtube.com/watch?v=AbCdEfGhIjK&t=3")
    assert ref == "AbCdEfGhIjK"
    assert channel.display(ref) == "https://youtu.be/AbCdEfGhIjK"
    assert channel.fetch(ref, tmp_path / "eingang") == tmp_path / "eingang" / "AbCdEfGhIjK.mp4"


def test_youtube_channel_fetches_with_browser_cookies(tmp_path: Path) -> None:
    seen: list[Any] = []

    class CookieYdl(FakeYdl):
        def __init__(self, options: dict[str, Any]) -> None:
            super().__init__(options)
            seen.append(options.get("cookiesfrombrowser"))

    YouTubeChannel(ydl_class=CookieYdl, cookies_from_browser=("firefox",)).fetch("AbCdEfGhIjK", tmp_path)
    YouTubeChannel(ydl_class=CookieYdl).fetch("AbCdEfGhIjK", tmp_path / "ohne")
    assert seen == [("firefox",), None]
    channel = make_channel("youtube", cookies_from_browser=("edge",))
    assert isinstance(channel, YouTubeChannel)
    with pytest.raises(ValueError, match="nur für YouTube"):
        make_channel("folder", folder=tmp_path, cookies_from_browser=("firefox",))


def test_youtube_channel_publishes_only_with_client_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, str, Path]] = []

    def fake_upload(video: Path, title: str, client_secrets: Path, **_: Any) -> youtube.Uploaded:
        calls.append((video, title, client_secrets))
        return youtube.Uploaded("VIDEOID1234", "unlisted")

    monkeypatch.setattr(youtube, "upload", fake_upload)
    video = _video(tmp_path)
    with pytest.raises(ValueError, match="client-secrets"):
        YouTubeChannel().publish(video, "qrvideo 1234abcd")
    assert calls == []
    assert YouTubeChannel(tmp_path / "c.json").publish(video, "qrvideo 1234abcd") == Published("VIDEOID1234")
    assert calls == [(video, "qrvideo 1234abcd", tmp_path / "c.json")]


@pytest.mark.parametrize(("privacy", "notice"), [("private", True), ("unlisted", False), (None, False)])
def test_youtube_channel_notices_a_different_visibility(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, privacy: str | None, notice: bool
) -> None:
    monkeypatch.setattr(youtube, "upload", lambda *a, **kw: youtube.Uploaded("VIDEOID1234", privacy))
    published = YouTubeChannel(tmp_path / "c.json").publish(_video(tmp_path), "t")
    assert published.ref == "VIDEOID1234"
    if notice:
        assert published.notice is not None
        assert "privat" in published.notice and "--cookies-from-browser" in published.notice
    else:
        assert published.notice is None
    assert FolderChannel(tmp_path).publish(_video(tmp_path), "t").notice is None


def test_notice_belongs_to_one_publish(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """I31: Hinweis im Ergebnis statt als Zustand des Kanals — der zweite Upload erbt den ersten nicht."""
    answers = iter([youtube.Uploaded("PRIVATE0001", "private"), youtube.Uploaded("UNLISTED001", "unlisted")])
    monkeypatch.setattr(youtube, "upload", lambda *a, **kw: next(answers))
    channel = YouTubeChannel(tmp_path / "c.json")
    first, second = (channel.publish(_video(tmp_path), "t") for _ in range(2))
    assert first.notice is not None and second == Published("UNLISTED001")
    assert not hasattr(channel, "notice")


def test_folder_channel_round_trip_with_neutral_name(tmp_path: Path) -> None:
    shared, inbox = tmp_path / "geteilt", tmp_path / "eingang"
    shared.mkdir()
    channel: Channel = FolderChannel(shared)
    refs = {channel.publish(_video(tmp_path), "Gehaltsliste").ref for _ in range(3)}
    assert len(refs) == 3
    for ref in refs:
        assert re.fullmatch(r"qrvideo-[0-9a-f]{8}\.mp4", ref)  # Threat T1: weder Dateiname noch Titel
        assert channel.parse_ref(channel.display(ref)) == ref
    assert sorted(p.name for p in shared.iterdir()) == sorted(refs)  # keine .part-Reste
    ref = refs.pop()
    fetched = channel.fetch(ref, inbox)
    assert fetched == inbox / ref and fetched.read_bytes() == b"qr-video"
    assert list(inbox.iterdir()) == [fetched]


def test_folder_channel_needs_an_existing_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Ordner"):
        FolderChannel(tmp_path / "fehlt").publish(_video(tmp_path), "t")


@pytest.mark.parametrize(
    "ref",
    [
        "../geheim.mp4",
        "..\\geheim.mp4",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "sub/x.mp4",
        "CON.mp4",
        "",
        " ",
        "..",
    ],
)
def test_folder_ref_never_leaves_the_folder(ref: str, tmp_path: Path) -> None:
    shared = tmp_path / "a" / "geteilt"
    shared.mkdir(parents=True)
    (tmp_path / "a" / "geheim.mp4").write_bytes(b"geheim")
    channel = FolderChannel(shared)
    with pytest.raises(ValueError):
        channel.parse_ref(ref)
    with pytest.raises(ValueError):
        channel.fetch(ref, tmp_path / "eingang")
    assert not (tmp_path / "eingang").exists()


def test_folder_fetch_reports_missing_and_never_overwrites(tmp_path: Path) -> None:
    shared, inbox = tmp_path / "geteilt", tmp_path / "eingang"
    shared.mkdir()
    inbox.mkdir()
    channel = FolderChannel(shared)
    with pytest.raises(FileNotFoundError):
        channel.fetch("qrvideo-00000000.mp4", inbox)
    ref = channel.publish(_video(tmp_path), "t").ref
    (inbox / ref).write_bytes(b"alt")
    with pytest.raises(FileExistsError):
        channel.fetch(ref, inbox)
    assert (inbox / ref).read_bytes() == b"alt"


def test_fetch_into_the_shared_folder_itself_returns_the_file(tmp_path: Path) -> None:
    channel = FolderChannel(tmp_path)
    ref = channel.publish(_video(tmp_path), "t").ref
    assert channel.fetch(ref, tmp_path) == tmp_path / ref


def test_make_channel(tmp_path: Path) -> None:
    assert CHANNEL_NAMES == ("youtube", "folder")
    assert isinstance(make_channel("youtube"), YouTubeChannel)
    folder = make_channel("folder", folder=tmp_path)
    assert isinstance(folder, FolderChannel) and folder.root == tmp_path
    with pytest.raises(ValueError, match="--folder"):
        make_channel("folder")
    with pytest.raises(ValueError, match="Kanal"):
        make_channel("ftp")


def test_failed_copy_leaves_no_partial_video(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import shutil

    shared = tmp_path / "geteilt"
    shared.mkdir()

    def broken_copy(source: Path, target: Path) -> None:
        Path(target).write_bytes(b"halb")
        raise OSError("Datentraeger voll")

    monkeypatch.setattr(shutil, "copyfile", broken_copy)
    with pytest.raises(OSError, match="voll"):
        FolderChannel(shared).publish(_video(tmp_path), "t")
    assert list(shared.iterdir()) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("youtube:AbCdEfGhIjK", "youtube:AbCdEfGhIjK"),
        ("https://youtu.be/AbCdEfGhIjK", "youtube:AbCdEfGhIjK"),  # Eingabe wie bis I29b
        ("AbCdEfGhIjK", "youtube:AbCdEfGhIjK"),
        (" folder:qrvideo-0123abcd.mp4 ", "folder:qrvideo-0123abcd.mp4"),
    ],
)
def test_channel_ref_from_user_input(text: str, expected: str) -> None:
    assert channel_ref(text) == expected
    assert parse_channel_ref(expected) == tuple(expected.split(":", 1))


@pytest.mark.parametrize(
    "text",
    [
        "ftp:x.mp4",
        "folder:../geheim.mp4",
        r"folder:C:\x.mp4",
        "folder:",
        "youtube:kein-video",
        "kein-video",
        "",
    ],
)
def test_bad_channel_refs_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        channel_ref(text)
    with pytest.raises(ValueError):
        parse_channel_ref(text)


def test_received_refs_must_name_their_channel() -> None:
    """Eine empfangene v2-Nachricht nennt den Kanal immer; nur Nutzereingaben duerfen ihn weglassen."""
    with pytest.raises(ValueError, match="Kanal"):
        parse_channel_ref("AbCdEfGhIjK")
    with pytest.raises(ValueError, match="Kanal"):
        parse_channel_ref("https://youtu.be/AbCdEfGhIjK")
    with pytest.raises(ValueError, match="<Kanal>:<Verweis>"):  # Formathinweis statt „keine ID“
        parse_channel_ref("youtube")
