"""Reiter „Empfangen“: Presenter mit Fakes (Download, Frames, Decoder, Crypto) und Oberflächen-Durchlauf."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from gui_fakes import ALICE, BOB, FakeCrypto, pump

from qrvideo import youtube
from qrvideo.channel import FolderChannel, YouTubeChannel
from qrvideo.crypto import SignatureInfo, UntrustedSignatureError
from qrvideo.decoder import DecodeReport
from qrvideo_gui.jobs import Cancelled, Progress, ProgressEvent
from qrvideo_gui.keys import KeyService
from qrvideo_gui.receive import ReceivePresenter, ReceiveRequest

Frame = npt.NDArray[np.uint8]
VIDEO_ID = "dQw4w9WgXcQ"
SIGNED_BY_ALICE = SignatureInfo(ALICE.keyid, ALICE.fingerprint, "Alice <alice@example.test>")


class Channel(YouTubeChannel):
    """YouTube-Kanal mit Attrappe fürs Abholen, dazu Video lesen und Dekodieren; liefert `payload`."""

    def __init__(self, payload: bytes = FakeCrypto.PREFIX + b"Inhalt", frames: int = 4) -> None:
        super().__init__()
        self.payload, self.frames = payload, frames
        self.downloaded: list[tuple[str, Path]] = []
        self.read: list[Path] = []

    def fetch(self, video: str, target_dir: Path) -> Path:
        self.downloaded.append((video, target_dir))
        path = target_dir / f"{VIDEO_ID}.mp4"
        path.write_bytes(b"video")
        return path

    def read_video(self, path: Path) -> Iterator[Frame]:
        self.read.append(path)
        for _ in range(self.frames):
            yield np.zeros((2, 2), dtype=np.uint8)

    def decode(self, frames: Iterable[Frame]) -> tuple[bytes, DecodeReport]:
        count = sum(1 for _ in frames)
        return self.payload, DecodeReport(frames=count, qr_codes=3 * count, corrected_bytes=7)


def _presenter(channel: Channel, signer: SignatureInfo | None = SIGNED_BY_ALICE) -> ReceivePresenter:
    crypto = FakeCrypto([ALICE, BOB], signer=signer)
    return ReceivePresenter(
        KeyService(lambda: crypto),
        channel=channel,
        reader=channel.read_video,
        decode=channel.decode,
        warning=lambda: None,
    )


def _video(tmp_path: Path, name: str = "bericht.xlsx.mp4") -> Path:
    video = tmp_path / name
    video.write_bytes(b"video")
    return video


def test_local_video_is_decoded_decrypted_and_saved(tmp_path: Path) -> None:
    channel = Channel()
    out = tmp_path / "eingang"
    out.mkdir()
    events: list[ProgressEvent] = []

    class Spy(Progress):
        def report(self, done: int, total: int | None = None, text: str = "") -> None:
            events.append(ProgressEvent(done, total, text))

    result = _presenter(channel).run(ReceiveRequest(str(_video(tmp_path)), out), Spy())
    assert result.target == out / "bericht.xlsx"
    assert result.target.read_bytes() == b"Inhalt"
    assert (result.signer_name, result.signer_fingerprint) == (SIGNED_BY_ALICE.username, ALICE.fingerprint)
    assert (result.frames, result.qr_codes, result.unreadable) == (4, 12, 0)
    assert channel.downloaded == []
    assert [e.done for e in events if e.done] == [1, 2, 3, 4]
    assert list(out.iterdir()) == [result.target]


def test_youtube_link_is_downloaded_into_the_output_folder(tmp_path: Path) -> None:
    channel = Channel()
    request = ReceiveRequest(f"  https://youtu.be/{VIDEO_ID}  ", tmp_path)
    presenter = _presenter(channel)
    assert presenter.target_for(request) == tmp_path / VIDEO_ID
    result = presenter.run(request, Progress())
    assert channel.downloaded == [(VIDEO_ID, tmp_path)]
    assert channel.read == [tmp_path / f"{VIDEO_ID}.mp4"]
    assert result.target == tmp_path / VIDEO_ID
    assert result.downloaded == tmp_path / f"{VIDEO_ID}.mp4"


def _request_presenter(fake: Channel, crypto: FakeCrypto | None = None) -> ReceivePresenter:
    """Ohne festen Kanal: der Presenter baut ihn aus der Anfrage (I32a)."""
    crypto = crypto or FakeCrypto([ALICE, BOB], signer=SIGNED_BY_ALICE)
    return ReceivePresenter(
        KeyService(lambda: crypto), reader=fake.read_video, decode=fake.decode, warning=lambda: None
    )


def test_receive_from_the_folder_channel(tmp_path: Path) -> None:
    """ADR-005, I32a: Kanal und Kanal-Ordner kommen aus der Anfrage; ein Dateiname im Kanal-Ordner genügt."""
    shared, out = tmp_path / "geteilt", tmp_path / "eingang"
    shared.mkdir()
    out.mkdir()
    ref = FolderChannel(shared).publish(_video(tmp_path), "t").ref
    fake = Channel()
    crypto = FakeCrypto([ALICE, BOB], signer=SIGNED_BY_ALICE)
    crypto.embedded_name = "bericht.xlsx"
    presenter = _request_presenter(fake, crypto)
    request = ReceiveRequest(ref, out, channel="folder", folder=shared)
    # Rückfallname ohne `.mp4`, sonst kollidiert er mit dem geholten Video
    assert presenter.target_for(request) == out / ref.removesuffix(".mp4")
    result = presenter.run(request, Progress())
    assert result.downloaded == out / ref and fake.read == [out / ref]
    assert result.target == out / "bericht.xlsx" and result.target.read_bytes() == b"Inhalt"
    with pytest.raises(ValueError, match="Kanal-Ordner"):
        presenter.target_for(ReceiveRequest("../geheim.mp4", out, channel="folder", folder=shared))


def test_browser_login_reaches_yt_dlp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """I32a: `BROWSER[:PROFIL]` aus dem Reiter landet als `cookiesfrombrowser` beim Download."""
    seen: list[tuple[str, ...] | None] = []

    def download(video: str, target_dir: Path, **kw: object) -> Path:
        seen.append(kw.get("cookies_from_browser"))  # type: ignore[arg-type]
        path = target_dir / f"{video}.mp4"
        path.write_bytes(b"video")
        return path

    monkeypatch.setattr(youtube, "download", download)
    request = ReceiveRequest(f"https://youtu.be/{VIDEO_ID}", tmp_path, browser=" Firefox:Arbeit ")
    result = _request_presenter(Channel()).run(request, Progress())
    assert seen == [("firefox", "Arbeit")]
    assert result.downloaded == tmp_path / f"{VIDEO_ID}.mp4"
    _request_presenter(Channel()).run(ReceiveRequest(VIDEO_ID, tmp_path, browser="  "), Progress())
    assert seen[-1] is None


@pytest.mark.parametrize(
    ("channel", "folder", "browser", "expected"),
    [
        ("folder", "geteilt", "firefox", "Browser-Anmeldung gilt nur für YouTube"),
        ("folder", None, "", "Kanal-Ordner"),
        ("folder", "fehlt", "", "Kanal-Ordner"),
        ("youtube", None, "netscape", "Unbekannter Browser „netscape“. Erlaubt: brave, chrome"),
        ("youtube", None, "firefox:", "optional mit „:Profil“"),
        ("telegraf", None, "", "Unbekannter Kanal „telegraf“"),
    ],
)
def test_wrong_channel_settings_are_explained(
    tmp_path: Path, channel: str, folder: str | None, browser: str, expected: str
) -> None:
    (tmp_path / "geteilt").mkdir()
    folder_path = tmp_path / folder if folder else None
    request = ReceiveRequest(
        "qrvideo-1a2b3c4d.mp4", tmp_path, channel=channel, folder=folder_path, browser=browser
    )
    with pytest.raises(ValueError, match=expected):
        _request_presenter(Channel()).target_for(request)


def test_local_video_needs_no_channel(tmp_path: Path) -> None:
    """Eine lokale Datei wird nie über den Kanal geholt; falsche Kanalangaben stören dann nicht."""
    request = ReceiveRequest(
        str(_video(tmp_path)), tmp_path, channel="folder", folder=None, browser="netscape"
    )
    assert _request_presenter(Channel()).target_for(request) == tmp_path / "bericht.xlsx"


def test_untrusted_signature_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "eingang"
    out.mkdir()
    with pytest.raises(UntrustedSignatureError):
        _presenter(Channel(), signer=None).run(ReceiveRequest(str(_video(tmp_path)), out), Progress())
    assert list(out.iterdir()) == []


def test_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    """Der Name steht erst nach dem Entschluesseln fest (I27b1): keine Rueckfrage, sondern ein freier Name."""
    out = tmp_path / "eingang"
    out.mkdir()
    (out / "bericht.xlsx").write_bytes(b"alt")
    (out / "bericht (2).xlsx").write_bytes(b"auch alt")
    presenter = _presenter(Channel())
    result = presenter.run(ReceiveRequest(str(_video(tmp_path)), out), Progress())
    assert result.target == out / "bericht (3).xlsx"
    assert result.target.read_bytes() == b"Inhalt"
    assert (out / "bericht.xlsx").read_bytes() == b"alt"
    assert (out / "bericht (2).xlsx").read_bytes() == b"auch alt"


def _named_presenter(name: str | None) -> ReceivePresenter:
    crypto = FakeCrypto([ALICE, BOB], signer=SIGNED_BY_ALICE)
    crypto.embedded_name = name
    channel = Channel()
    return ReceivePresenter(
        KeyService(lambda: crypto),
        channel=channel,
        reader=channel.read_video,
        decode=channel.decode,
        warning=lambda: None,
    )


def test_file_is_named_after_the_encrypted_name(tmp_path: Path) -> None:
    """Threat T1: das Video heisst neutral, der Originalname reist verschluesselt mit (I27a)."""
    out = tmp_path / "eingang"
    out.mkdir()
    request = ReceiveRequest(str(_video(tmp_path, "qrvideo-1a2b3c4d.mp4")), out)
    result = _named_presenter("Quartal Ärger.xlsx").run(request, Progress())
    assert result.target == out / "Quartal Ärger.xlsx"
    assert _named_presenter(None).run(request, Progress()).target == out / "qrvideo-1a2b3c4d"


def test_hostile_embedded_name_stays_in_the_output_folder(tmp_path: Path) -> None:
    out = tmp_path / "eingang"
    out.mkdir()
    request = ReceiveRequest(str(_video(tmp_path)), out)
    result = _named_presenter("../../CON").run(request, Progress())
    assert result.target.parent == out
    assert [p.name for p in out.iterdir()] == [result.target.name] == ["datei_CON"]


@pytest.mark.parametrize(
    ("source", "output", "expected"),
    [
        ("", ".", "Videodatei"),
        ("kein link und keine datei", ".", "Videodatei"),
        ("VIDEO", "fehlt", "Ausgabeordner"),
    ],
)
def test_invalid_input_is_explained(tmp_path: Path, source: str, output: str, expected: str) -> None:
    source = str(_video(tmp_path)) if source == "VIDEO" else source
    out = tmp_path if output == "." else tmp_path / output
    with pytest.raises(ValueError, match=expected):
        _presenter(Channel()).run(ReceiveRequest(source, out), Progress())


def test_hostile_video_name_gives_safe_target(tmp_path: Path) -> None:
    presenter = _presenter(Channel())
    request = ReceiveRequest(str(_video(tmp_path, "CON.mp4")), tmp_path)
    assert presenter.target_for(request) == tmp_path / "datei_CON"


def test_cancel_while_reading_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "eingang"
    out.mkdir()
    progress = Progress()
    original = progress.report

    def cancel_after_first(done: int, total: int | None = None, text: str = "") -> None:
        original(done, total, text)
        if done == 1:
            progress.cancel()

    progress.report = cancel_after_first  # type: ignore[method-assign]
    with pytest.raises(Cancelled):
        _presenter(Channel(frames=50)).run(ReceiveRequest(str(_video(tmp_path)), out), progress)
    assert list(out.iterdir()) == []


def test_receive_tab_shows_signer_and_fingerprint(tmp_path: Path, root: tk.Toplevel) -> None:
    from qrvideo_gui.receive_view import ReceiveTab

    tab = ReceiveTab(root, _presenter(Channel()), tk.StringVar(root))  # fragt nie (I27b1, I28)
    (tmp_path / "bericht.xlsx").write_bytes(b"alt")
    tab.pack()
    tab.source.set(str(_video(tmp_path)))
    tab.output.set(str(tmp_path))
    tab.receive_button.invoke()
    pump(root, lambda: "Fertig" in tab.result.get())
    text = tab.result.get()
    assert "Alice <alice@example.test>" in text
    assert "AAAA AAAA" in text
    assert (tmp_path / "bericht (2).xlsx").read_bytes() == b"Inhalt"
    assert (tmp_path / "bericht.xlsx").read_bytes() == b"alt"


def test_receive_tab_with_the_folder_channel(tmp_path: Path, root: tk.Toplevel) -> None:
    """I32b: Kanalwahl im Reiter; echte Kopie aus dem Kanal-Ordner, Attrappe nur für Frames und Krypto."""
    from qrvideo_gui.receive_view import ReceiveTab

    shared, out = tmp_path / "geteilt", tmp_path / "eingang"
    shared.mkdir()
    out.mkdir()
    ref = FolderChannel(shared).publish(_video(tmp_path), "t").ref
    tab = ReceiveTab(root, _request_presenter(Channel()), tk.StringVar(root))
    tab.pack()
    tab.channel.set("folder")
    tab.folder.set(str(shared))
    tab.source.set(ref)
    tab.output.set(str(out))
    tab.receive_button.invoke()
    pump(root, lambda: "Fertig" in tab.result.get())
    assert (out / ref).read_bytes() == b"video"  # aus dem Kanal-Ordner geholt
    assert (out / ref.removesuffix(".mp4")).read_bytes() == b"Inhalt"


def test_receive_tab_shows_only_the_fields_of_the_chosen_channel(root: tk.Toplevel) -> None:
    from qrvideo_gui.receive_view import ReceiveTab

    tab = ReceiveTab(root, _request_presenter(Channel()), tk.StringVar(root))
    tab.pack()
    root.update_idletasks()
    youtube_hint = tab.source_hint.cget("text")
    assert tab.browser_row.winfo_manager() == "grid" and tab.folder_row.winfo_manager() == ""
    tab.channel.set("folder")
    assert tab.browser_row.winfo_manager() == "" and tab.folder_row.winfo_manager() == "grid"
    assert "Kanal-Ordner" in tab.source_hint.cget("text") and "YouTube" in youtube_hint
    tab.channel.set("youtube")
    assert tab.browser_row.winfo_manager() == "grid" and tab.source_hint.cget("text") == youtube_hint


def test_receive_tab_passes_the_browser_login(tmp_path: Path, root: tk.Toplevel) -> None:
    from qrvideo_gui.receive_view import ReceiveTab

    tab = ReceiveTab(root, _request_presenter(Channel()), tk.StringVar(root))
    tab.source.set(VIDEO_ID)
    tab.output.set(str(tmp_path))
    tab.browser.set("netscape")
    tab.receive_button.invoke()
    assert "Unbekannter Browser „netscape“" in tab.result.get()
    assert tab.job is None  # geprüft, bevor ein Job startet
