"""Schlüssel-Presenter ohne Tk und Smoke-Test des Hauptfensters (übersprungen ohne Display)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator
from pathlib import Path

import pytest
from gui_fakes import ALICE, BOB, NAMELESS, FakeCrypto, pump

from qrvideo.crypto import GpgError
from qrvideo_gui.keys import KeyService, default_signer, format_fingerprint


def test_rows_show_name_trust_and_own_keys_first() -> None:
    rows = KeyService(lambda: FakeCrypto([BOB, NAMELESS, ALICE])).rows()
    assert [r.fingerprint for r in rows] == [ALICE.fingerprint, BOB.fingerprint, NAMELESS.fingerprint]
    assert rows[0].name == "Alice <alice@example.test>"
    assert rows[0].own and not rows[1].own
    assert "eigener" in rows[0].trust and rows[1].trust == "voll"
    assert rows[2].name == "(ohne Namen)"


def test_fingerprint_in_groups_of_four() -> None:
    assert format_fingerprint("0123456789ABCDEF") == "0123 4567 89AB CDEF"


def test_default_signer_is_first_own_key() -> None:
    rows = KeyService(lambda: FakeCrypto([BOB, ALICE])).rows()
    assert default_signer(rows) == ALICE.fingerprint
    assert default_signer(KeyService(lambda: FakeCrypto([BOB])).rows()) is None


def test_crypto_is_created_once_and_errors_propagate() -> None:
    calls: list[int] = []

    def factory() -> FakeCrypto:
        calls.append(1)
        return FakeCrypto([ALICE])

    service = KeyService(factory)
    assert service.crypto() is service.crypto()
    assert calls == [1]

    def broken() -> FakeCrypto:
        raise GpgError("gpg nicht gefunden: GnuPG installieren oder QRVIDEO_GPG setzen")

    with pytest.raises(GpgError):
        KeyService(broken).rows()


def test_main_window_shows_trusted_keys(root: tk.Toplevel) -> None:
    from qrvideo_gui.app import MainWindow

    window = MainWindow(root, KeyService(lambda: FakeCrypto([BOB, ALICE])))
    tabs = [window.notebook.tab(t, "text") for t in window.notebook.tabs()]  # type: ignore[no-untyped-call]
    assert "Schlüssel" in tabs
    pump(root, lambda: len(window.keys_tab.table.get_children()) == 2)
    first = window.keys_tab.table.item(window.keys_tab.table.get_children()[0], "values")
    assert first[0] == "Alice <alice@example.test>"


def test_main_window_shows_friendly_error_without_gnupg(root: tk.Toplevel) -> None:
    from qrvideo_gui.app import MainWindow

    def broken() -> FakeCrypto:
        raise GpgError("gpg nicht gefunden: GnuPG installieren oder QRVIDEO_GPG setzen")

    window = MainWindow(root, KeyService(broken))
    pump(root, lambda: "Gpg4win" in window.status.get())


def test_parse_args_accepts_gnupghome(tmp_path: Path) -> None:
    from qrvideo_gui.app import parse_args

    assert parse_args(["--gnupghome", str(tmp_path)]).gnupghome == tmp_path
    assert parse_args([]).gnupghome is None


def test_send_tab_gets_keys_and_own_signer(root: tk.Toplevel) -> None:
    from qrvideo_gui.app import MainWindow

    window = MainWindow(root, KeyService(lambda: FakeCrypto([BOB, ALICE])))
    tabs = [window.notebook.tab(t, "text") for t in window.notebook.tabs()]  # type: ignore[no-untyped-call]
    assert tabs == ["Senden", "Empfangen", "Handshake", "Schlüssel"]
    pump(root, lambda: window.send_tab.signer_fingerprint() == ALICE.fingerprint)
    assert window.handshake_tab.response_signer.fingerprint() == ALICE.fingerprint


def test_closing_while_busy_asks_and_cancels(root: tk.Toplevel) -> None:
    from qrvideo_gui.app import MainWindow

    questions: list[str] = []

    def refuse(title: str, text: str) -> bool:
        questions.append(title)
        return False

    window = MainWindow(root, KeyService(lambda: FakeCrypto([ALICE])), ask=refuse)

    class Busy:
        running = True
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    busy = Busy()
    window.send_tab.job = busy  # type: ignore[assignment]
    assert window.close() is False
    assert questions and not busy.cancelled
    window.send_tab.job = None
    window.receive_tab.job = busy  # type: ignore[assignment]
    assert window.close() is False
    window._ask = lambda t, m: True
    assert window.close() is True
    assert busy.cancelled


def _descendants(widget: tk.Misc) -> list[tk.Misc]:
    children = widget.winfo_children()
    return children + [w for child in children for w in _descendants(child)]


@pytest.fixture
def scaled(root: tk.Toplevel) -> Iterator[tk.Toplevel]:
    """Wie Windows bei 150 % Anzeige mit DPI-Bewusstsein: Tk rechnet 2 Pixel je Punkt (sonst 1,33)."""
    before = float(root.tk.call("tk", "scaling"))
    root.tk.call("tk", "scaling", 2.0)
    yield root
    root.tk.call("tk", "scaling", before)


def test_every_tab_fits_at_minimum_window_size(scaled: tk.Toplevel) -> None:
    """Screenshot 2026-11-02 (150 %): Das Fenster ließ sich kleiner ziehen, als der Handshake braucht."""
    from qrvideo.crypto import KeyInfo
    from qrvideo_gui.app import MainWindow

    root = scaled
    own = KeyInfo("6C12DA0E29EC9B93", "9" * 40, ("Alice Beispiel <alice@example.test>",), "u")
    other = KeyInfo("F882BB89A0DAC37F", "5" * 40, ("Bob Beispiel <bob@example.test>",), "f")
    window = MainWindow(root, KeyService(lambda: FakeCrypto([own, other])))
    pump(root, lambda: len(window.keys_tab.table.get_children()) == 2)
    root.deiconify()
    width, height = root.wm_minsize()
    root.geometry(f"{width}x{height}")
    for tab in (window.send_tab, window.receive_tab, window.handshake_tab, window.keys_tab):
        window.notebook.select(tab)  # type: ignore[no-untyped-call]
        root.update()
        bottom = root.winfo_rooty() + root.winfo_height()
        for widget in _descendants(tab):
            visible_text = widget.winfo_class() in {"TLabel", "TButton", "TCheckbutton"}
            if not visible_text or not widget.winfo_ismapped():
                continue
            name = f"{tab.winfo_class()}: {widget.cget('text') or widget}"
            assert widget.winfo_width() >= widget.winfo_reqwidth(), f"abgeschnitten: {name}"
            assert widget.winfo_rooty() + widget.winfo_height() <= bottom, f"unten abgeschnitten: {name}"
