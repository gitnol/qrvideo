"""Dateinamen aus fremden Quellen (YouTube-Titel, Handshake-Nachrichten) entschaerfen."""

from __future__ import annotations

import re
import unicodedata

_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


def safe_filename(name: str, fallback: str = "datei") -> str:
    """Nur der Basisname, ohne Steuer- und Pfadzeichen, ohne reservierte Windows-Namen (THREAT_MODEL T5)."""
    name = unicodedata.normalize("NFC", name).replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE.sub("_", name)[:200].strip(" .")  # erst kuerzen, dann strippen (Code-Review #14)
    if not name or name.split(".", 1)[0].upper() in _RESERVED:
        name = f"{fallback}_{name}" if name else fallback
    return name
