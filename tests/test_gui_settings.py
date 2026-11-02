"""Sprachwahl der GUI (ADR-006, I33i): Einstellungsdatei, Vorrang beim Start, Menü „Sprache“."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest
from gui_fakes import ALICE, FakeCrypto

from qrvideo.i18n import current_language
from qrvideo_gui.keys import KeyService
from qrvideo_gui.settings import load_language, save_language, settings_path


def test_saved_language_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "qrvideo" / "settings.json"
    assert load_language(path) is None  # noch keine Datei
    save_language("es", path)
    assert load_language(path) == "es"
    save_language("de", path)
    assert load_language(path) == "de"


@pytest.mark.parametrize("content", ["kein json", '{"language": "fr"}', '["es"]', '{"language": 3}'])
def test_broken_or_unsupported_settings_are_ignored(content: str, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    assert load_language(path) is None


def test_settings_live_in_the_user_profile(tmp_path: Path) -> None:
    assert settings_path({"APPDATA": str(tmp_path)}, "nt") == tmp_path / "qrvideo" / "settings.json"
    xdg = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert settings_path(xdg, "posix") == tmp_path / "qrvideo" / "settings.json"
    assert settings_path({}, "posix") == Path.home() / ".config" / "qrvideo" / "settings.json"
    both = {"APPDATA": str(tmp_path / "win"), "XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    assert (
        settings_path(both, "posix") == tmp_path / "xdg" / "qrvideo" / "settings.json"
    )  # APPDATA nur Windows


def test_startup_language_follows_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from qrvideo_gui.app import startup_language

    saved = tmp_path / "settings.json"
    save_language("es", saved)
    monkeypatch.delenv("QRVIDEO_LANG")
    assert startup_language([], saved) == "es"  # gespeicherte Wahl vor der Sprache des Systems
    assert startup_language(["--lang", "en"], saved) == "en"
    monkeypatch.setenv("QRVIDEO_LANG", "de")
    assert startup_language([], saved) == "de"  # Umgebung vor gespeicherter Wahl


def test_language_menu_saves_the_choice_for_the_next_start(root: tk.Toplevel, tmp_path: Path) -> None:
    from qrvideo_gui.app import MainWindow

    saved: list[str] = []
    window = MainWindow(root, KeyService(lambda: FakeCrypto([ALICE])), save=saved.append)
    window.choose_language("es")
    assert saved == ["es"]
    assert window.status.get() == "Sprache gespeichert: Español. Sie gilt nach einem Neustart."
    assert current_language() == "de"  # die laufende Oberfläche wechselt nicht mitten im Betrieb


def test_parse_args_accepts_lang() -> None:
    from qrvideo_gui.app import parse_args

    assert parse_args(["--lang", "es"]).lang == "es"
    with pytest.raises(SystemExit):
        parse_args(["--lang", "fr"])
