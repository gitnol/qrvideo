"""Reiter „Handshake“: Challenge erstellen, Nachricht öffnen (.asc, QR-PNG), Response wählen, speichern."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import cast

import pytest
from gui_fakes import ALICE, BOB, FakeCrypto, pump

from qrvideo.crypto import Crypto, SignatureInfo, UntrustedSignatureError
from qrvideo.handshake import Response, open_sealed
from qrvideo.i18n import set_language
from qrvideo.qrpng import read_qr_png
from qrvideo_gui.handshake import ChallengeRequest, HandshakePresenter, ResponseRequest
from qrvideo_gui.jobs import Progress
from qrvideo_gui.keys import KeyService

VIDEO_ID = "dQw4w9WgXcQ"
SIGNED_BY_BOB = SignatureInfo(BOB.keyid, BOB.fingerprint, "Bob <bob@example.test>")


def _presenter(signer: SignatureInfo | None = SIGNED_BY_BOB) -> tuple[HandshakePresenter, FakeCrypto]:
    crypto = FakeCrypto([ALICE, BOB], signer=signer)
    return HandshakePresenter(KeyService(lambda: crypto)), crypto


def _offer(tmp_path: Path) -> Path:
    offer = tmp_path / "angebot"
    (offer / "unterordner").mkdir(parents=True)
    (offer / "b.pdf").write_bytes(b"b")
    (offer / "a.txt").write_bytes(b"a")
    return offer


def _challenge(tmp_path: Path, **changes: object) -> ChallengeRequest:
    values: dict[str, object] = {
        "directory": _offer(tmp_path),
        "videos": (f"https://youtu.be/{VIDEO_ID}",),
        "recipients": (BOB.fingerprint,),
        "signer": ALICE.fingerprint,
        "target": tmp_path / "challenge.asc",
        "png": True,
    }
    values.update(changes)
    return ChallengeRequest(**values)  # type: ignore[arg-type]


def test_challenge_lists_files_and_videos_and_writes_asc_and_png(tmp_path: Path) -> None:
    presenter, crypto = _presenter()
    result = presenter.create_challenge(_challenge(tmp_path), Progress())
    assert crypto.encrypted == [([BOB.fingerprint], ALICE.fingerprint, None, True)]
    sealed = (tmp_path / "challenge.asc").read_bytes()
    assert read_qr_png(tmp_path / "challenge.png") == sealed
    assert result.png == tmp_path / "challenge.png"
    opened = presenter.open_message(tmp_path / "challenge.asc", Progress())
    assert opened.kind == "challenge"
    assert opened.entries == ("a.txt", "b.pdf", f"youtube:{VIDEO_ID}")  # Format v2 (I29c1)
    assert "2 Dateien" in result.summary and "1 Video" in result.summary


def test_png_message_opens_like_the_text_file(tmp_path: Path) -> None:
    presenter, _ = _presenter()
    presenter.create_challenge(_challenge(tmp_path), Progress())
    opened = presenter.open_message(tmp_path / "challenge.png", Progress())
    assert (opened.signer_name, opened.signer_fingerprint) == (SIGNED_BY_BOB.username, BOB.fingerprint)
    assert opened.entries == ("a.txt", "b.pdf", f"youtube:{VIDEO_ID}")  # Format v2 (I29c1)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"directory": Path("fehlt")}, "Ordner"),
        ({"recipients": ()}, "Empfänger"),
        ({"signer": ""}, "Signaturschlüssel"),
        ({"target": Path("challenge.txt")}, ".asc"),
        ({"videos": ("kein-link",)}, "kein-link"),
        (
            {"videos": ("folder:../geheim.mp4",)},
            "folder:<Dateiname>",
        ),  # Fehlertext nennt beide Formen (I29c2)
    ],
)
def test_challenge_input_is_validated(tmp_path: Path, changes: dict[str, object], expected: str) -> None:
    presenter, crypto = _presenter()
    with pytest.raises(ValueError, match=expected):
        presenter.create_challenge(_challenge(tmp_path, **changes), Progress())
    assert crypto.encrypted == []


def test_videos_may_name_their_channel(tmp_path: Path) -> None:
    """ADR-005: neben YouTube-Links auch `<kanal>:<verweis>`, z. B. ein Video im Kanal-Ordner (I29c2)."""
    presenter, _ = _presenter()
    videos = (f"https://youtu.be/{VIDEO_ID}", " folder:qrvideo-0123abcd.mp4 ", "", f"youtube:{VIDEO_ID}")
    result = presenter.create_challenge(_challenge(tmp_path, videos=videos), Progress())
    opened = presenter.open_message(tmp_path / "challenge.asc", Progress())
    assert opened.entries[2:] == (f"youtube:{VIDEO_ID}", "folder:qrvideo-0123abcd.mp4", f"youtube:{VIDEO_ID}")
    assert "3 Videos" in result.summary


def test_existing_files_need_confirmation(tmp_path: Path) -> None:
    presenter, _ = _presenter()
    request = _challenge(tmp_path)
    (tmp_path / "challenge.png").write_bytes(b"alt")
    assert presenter.existing(request.target, request.png) == [tmp_path / "challenge.png"]
    with pytest.raises(FileExistsError):
        presenter.create_challenge(request, Progress())
    assert (tmp_path / "challenge.png").read_bytes() == b"alt"
    assert not request.target.exists()
    presenter.create_challenge(request, Progress(), overwrite=True)
    assert request.target.exists()


def test_response_goes_back_to_the_sender_of_the_challenge(tmp_path: Path) -> None:
    presenter, crypto = _presenter()
    presenter.create_challenge(_challenge(tmp_path, png=False), Progress())
    opened = presenter.open_message(tmp_path / "challenge.asc", Progress())
    answer = ResponseRequest(opened, 1, ALICE.fingerprint, tmp_path / "response.asc", png=False)
    result = presenter.create_response(answer, Progress())
    assert crypto.encrypted[-1] == ([BOB.fingerprint], ALICE.fingerprint, None, True)
    message, _ = open_sealed(cast(Crypto, crypto), (tmp_path / "response.asc").read_bytes())
    assert message == Response("b.pdf")
    assert "b.pdf" in result.summary and "Bob" in result.summary


def test_response_needs_a_valid_choice_from_a_challenge(tmp_path: Path) -> None:
    presenter, _ = _presenter()
    presenter.create_challenge(_challenge(tmp_path, png=False), Progress())
    opened = presenter.open_message(tmp_path / "challenge.asc", Progress())
    with pytest.raises(ValueError, match="Eintrag"):
        presenter.create_response(
            ResponseRequest(opened, 3, ALICE.fingerprint, tmp_path / "r.asc", False), Progress()
        )
    presenter.create_response(
        ResponseRequest(opened, 0, ALICE.fingerprint, tmp_path / "r.asc", False), Progress()
    )
    response = presenter.open_message(tmp_path / "r.asc", Progress())
    assert (response.kind, response.selection) == ("response", "a.txt")
    with pytest.raises(ValueError, match="keine Challenge"):
        presenter.create_response(
            ResponseRequest(response, 0, ALICE.fingerprint, tmp_path / "r2.asc", False), Progress()
        )


def test_message_without_trusted_signature_is_refused(tmp_path: Path) -> None:
    _presenter()[0].create_challenge(_challenge(tmp_path, png=False), Progress())
    untrusting, _ = _presenter(signer=None)
    with pytest.raises(UntrustedSignatureError):
        untrusting.open_message(tmp_path / "challenge.asc", Progress())


def test_handshake_tab_creates_opens_and_answers(tmp_path: Path, root: tk.Toplevel) -> None:
    from qrvideo_gui.handshake_view import HandshakeTab

    presenter, crypto = _presenter()
    tab = HandshakeTab(root, presenter, tk.StringVar(root), ask=lambda title, text: True)
    tab.pack()
    tab.set_keys(KeyService(lambda: crypto).rows())
    tab.directory.set(str(_offer(tmp_path)))
    tab.videos.insert("1.0", f"https://youtu.be/{VIDEO_ID}\n")
    tab.recipients.set_checked([BOB.fingerprint])
    tab.challenge_target.set(str(tmp_path / "challenge.asc"))
    tab.challenge_button.invoke()
    pump(root, lambda: "Gespeichert" in tab.challenge_result.get())

    tab.message.set(str(tmp_path / "challenge.png"))
    tab.open_button.invoke()
    pump(root, lambda: tab.entries.size() == 3)
    assert "Bob" in tab.message_result.get()
    tab.entries.selection_set(2)
    tab.response_target.set(str(tmp_path / "response.asc"))
    tab.response_button.invoke()
    pump(root, lambda: "Gespeichert" in tab.response_result.get())
    message, _ = open_sealed(cast(Crypto, crypto), (tmp_path / "response.asc").read_bytes())
    assert message == Response(f"youtube:{VIDEO_ID}")


@pytest.mark.parametrize(
    ("lang", "summary", "error"),
    [
        (
            "en",
            "Saved: challenge.asc and challenge.png – offer with 2 files and 1 video.",
            "“kein-link” is neither a YouTube link nor a reference like folder:<file name>.",
        ),
        (
            "es",
            "Guardado: challenge.asc y challenge.png – oferta con 2 archivos y 1 vídeo.",
            "«kein-link» no es ni un enlace de YouTube ni una referencia como folder:<nombre de archivo>.",
        ),
    ],
)
def test_challenge_texts_follow_the_language(lang: str, summary: str, error: str, tmp_path: Path) -> None:
    set_language(lang)
    presenter, _ = _presenter()
    assert presenter.create_challenge(_challenge(tmp_path), Progress()).summary == summary
    with pytest.raises(ValueError) as caught:
        presenter.create_challenge(_challenge(tmp_path / "b", videos=("kein-link",)), Progress())
    assert str(caught.value) == error
