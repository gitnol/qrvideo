"""Uebersetzung der Nutzertexte (ADR-006): stdlib `gettext`, Kataloge im Paket, Sprache prozessweit.

Quelltexte (msgids) sind englisch. Texte in Modulkonstanten nur mit `N_` markieren und erst beim Gebrauch
mit `_` uebersetzen, sonst bleiben sie in der Sprache beim Import.
Kataloge pflegen: `python tools/i18n_catalog.py update`.
"""

from __future__ import annotations

import ctypes
import gettext
import locale
import os
from collections.abc import Callable, Mapping
from pathlib import Path

DOMAIN = "qrvideo"
LOCALE_DIR = Path(__file__).parent / "locale"
SUPPORTED = ("de", "en", "es")
FALLBACK = "en"
LANG_ENV = "QRVIDEO_LANG"

# Tausender- und Dezimaltrennzeichen; Spanisch gruppiert nach CLDR erst ab fuenf Stellen (4000, aber 40.000)
_NUMBERS = {"de": (".", ",", 4), "en": (",", ".", 4), "es": (".", ",", 5)}

_translation: gettext.NullTranslations = gettext.NullTranslations()
_language = FALLBACK


def normalize(code: str | None) -> str | None:
    """`de_AT.UTF-8`, `es-MX`, `EN` → unterstuetztes Kuerzel oder None."""
    if not code:
        return None
    short = code.strip().replace("-", "_").split("_")[0].split(".")[0].lower()
    return short if short in SUPPORTED else None


def system_language() -> str | None:
    """Sprache der Oberflaeche des Betriebssystems (Windows: UI-Sprache, sonst LANGUAGE/LC_*/LANG)."""
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for part in os.environ.get(name, "").split(":"):
            if normalize(part):
                return normalize(part)
    windll = getattr(ctypes, "windll", None)
    if windll is not None:
        code = locale.windows_locale.get(windll.kernel32.GetUserDefaultUILanguage())
        if normalize(code):
            return normalize(code)
    return normalize(locale.getlocale()[0])


def resolve_language(
    explicit: str | None = None,
    saved: str | None = None,
    env: Mapping[str, str] | None = None,
    system: Callable[[], str | None] = system_language,
) -> str:
    """Vorrang: Option `--lang` → `QRVIDEO_LANG` → gespeicherte GUI-Wahl → Betriebssystem → Englisch."""
    environ = os.environ if env is None else env
    for candidate in (explicit, environ.get(LANG_ENV), saved):
        if normalize(candidate):
            return normalize(candidate) or FALLBACK
    return normalize(system()) or FALLBACK


def set_language(language: str, localedir: Path = LOCALE_DIR) -> None:
    """Sprache fuer alle folgenden `_`-Aufrufe; ohne Katalog bleiben die englischen msgids."""
    global _translation, _language
    _translation = gettext.translation(DOMAIN, localedir, languages=[language], fallback=True)
    _language = normalize(language) or FALLBACK


def current_language() -> str:
    return _language


def _(message: str) -> str:
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    return _translation.ngettext(singular, plural, count)


def N_(message: str) -> str:  # noqa: N802 - gettext-Konvention
    """Nur Markierung fuer das Extrahieren; uebersetzt wird beim Gebrauch mit `_`."""
    return message


def format_number(value: float, decimals: int = 0) -> str:
    """Zahl mit Tausender- und Dezimaltrennzeichen der aktuellen Sprache (400.000 / 400,000 / 2,5)."""
    thousands, point, min_digits = _NUMBERS.get(_language, _NUMBERS[FALLBACK])
    grouped = abs(round(value, decimals)) >= 10 ** (min_digits - 1)
    text = f"{value:{',' if grouped else ''}.{decimals}f}"
    return text.replace(",", "\0").replace(".", point).replace("\0", thousands)
