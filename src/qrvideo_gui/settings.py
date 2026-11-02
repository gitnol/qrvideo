"""Einstellungen der GUI im Benutzerprofil (ADR-006, I33i): bisher nur die gewählte Sprache.

Ohne Tk-Import (ADR-004). Die Datei ist Komfort, keine Pflicht: fehlt sie oder ist sie kaputt, gilt die
Sprache aus `QRVIDEO_LANG` bzw. dem System; Schreibfehler meldet der Aufrufer.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from qrvideo.i18n import normalize

APP_DIR = "qrvideo"
FILE_NAME = "settings.json"
LANGUAGE_KEY = "language"


def settings_path(env: Mapping[str, str] | None = None, os_name: str = os.name) -> Path:
    """Windows: `%APPDATA%\\qrvideo\\settings.json`; sonst `$XDG_CONFIG_HOME` bzw. `~/.config`."""
    environ = os.environ if env is None else env
    if os_name == "nt" and environ.get("APPDATA"):
        base = Path(environ["APPDATA"])
    else:
        base = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIR / FILE_NAME


def load_language(path: Path | None = None) -> str | None:
    """Gespeicherte Sprache oder None (keine Datei, kaputt, nicht unterstuetzt)."""
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get(LANGUAGE_KEY) if isinstance(data, dict) else None
    return normalize(value) if isinstance(value, str) else None


def save_language(language: str, path: Path | None = None) -> None:
    """Sprache dauerhaft merken; atomar ueber eine Zwischendatei, andere Schluessel bleiben erhalten."""
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    settings = {**(data if isinstance(data, dict) else {}), LANGUAGE_KEY: language}
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(partial, target)
