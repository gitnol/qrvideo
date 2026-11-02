"""GUI in drei Sprachen (ADR-006): Reiter, Schritte, Schlüsseltabelle, Prüfmeldungen, Fortschritt."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest
from gui_fakes import ALICE, BOB, NAMELESS, FakeCrypto, pump

from qrvideo.crypto import GpgNotFoundError
from qrvideo.i18n import set_language
from qrvideo_gui.errors import friendly_message
from qrvideo_gui.jobs import ProgressEvent
from qrvideo_gui.keys import KeyService
from qrvideo_gui.receive import ReceiveRequest, channel_for
from qrvideo_gui.send import SendRequest, validate
from qrvideo_gui.widgets import ProgressPanel

TABS = {
    "de": ["Senden", "Empfangen", "Handshake", "Schlüssel"],
    "en": ["Send", "Receive", "Handshake", "Keys"],
    "es": ["Enviar", "Recibir", "Handshake", "Claves"],
}


@pytest.mark.parametrize("lang", ["de", "en", "es"])
def test_main_window_speaks_the_language(lang: str, root: tk.Toplevel) -> None:
    from qrvideo_gui.app import MainWindow

    set_language(lang)
    window = MainWindow(root, KeyService(lambda: FakeCrypto([BOB, ALICE])))
    tabs = [window.notebook.tab(t, "text") for t in window.notebook.tabs()]  # type: ignore[no-untyped-call]
    assert tabs == TABS[lang]
    assert window.send_tab.send_button.cget("text") == {"de": "Senden", "en": "Send", "es": "Enviar"}[lang]
    pump(root, lambda: len(window.keys_tab.table.get_children()) == 2)
    expected = {"de": "2 vertraute Schlüssel", "en": "2 trusted keys", "es": "2 claves de confianza"}[lang]
    assert window.status.get() == expected


def test_key_rows_translate_trust_and_missing_name() -> None:
    set_language("es")
    rows = KeyService(lambda: FakeCrypto([BOB, NAMELESS, ALICE])).rows()
    assert [r.trust for r in rows] == ["absoluta (clave propia)", "plena", "plena"]
    assert rows[2].name == "(sin nombre)"  # sortiert weiterhin ans Ende


def test_send_validation_in_english(tmp_path: Path) -> None:
    set_language("en")
    request = SendRequest(tmp_path / "missing.txt", (), "", tmp_path / "out.avi")
    assert validate(request) == [
        "Please choose an existing file to send.",
        "Please tick at least one recipient.",
        "Please choose your own signing key.",
        "The target video must end in .mp4.",
    ]


def test_progress_uses_the_language_and_its_numbers(root: tk.Toplevel) -> None:
    set_language("en")
    panel = ProgressPanel(root)
    panel.show(ProgressEvent(1500, 2000, "Frame"))
    assert panel.text.get() == "Frame 1,500 of 2,000"
    set_language("de")
    panel.show(ProgressEvent(1500, 2000, "Frame"))
    assert panel.text.get() == "Frame 1.500 von 2.000"


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", "Please choose an existing channel folder."),
        ("es", "Elija una carpeta de canal existente."),
    ],
)
def test_receive_channel_errors_follow_the_language(lang: str, expected: str, tmp_path: Path) -> None:
    set_language(lang)
    with pytest.raises(ValueError, match=f"^{expected}$"):
        channel_for(ReceiveRequest("x", tmp_path, channel="folder", folder=tmp_path / "missing"))


def test_friendly_messages_follow_the_language() -> None:
    set_language("es")
    assert friendly_message(GpgNotFoundError("x")).startswith("GnuPG no está instalado.")
    assert friendly_message(FileNotFoundError(2, "No such file", "a.mp4")) == "Archivo no encontrado: a.mp4"
    set_language("en")
    assert friendly_message(ZeroDivisionError("x")) == (
        "Unexpected error. Technical details are in the console window."
    )


def test_receive_summary_uses_the_language(tmp_path: Path) -> None:
    from qrvideo_gui.receive import ReceiveResult
    from qrvideo_gui.receive_view import _summary

    result = ReceiveResult(tmp_path / "bericht.pdf", 400000, "Bob", "AB" * 20, 30, 420, 0, None, None)
    set_language("en")
    assert _summary(result).startswith("Done: “bericht.pdf” saved (400,000 bytes).\nSigned by: Bob\n")
    set_language("es")
    assert _summary(result).endswith("30 fotogramas, 420 códigos QR leídos, 0 ilegibles.")
