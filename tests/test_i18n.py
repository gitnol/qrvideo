"""Sprachwahl, Uebersetzung und Zahlenformat (ADR-006)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_i18n_catalog import catalog_tool

from qrvideo import i18n
from qrvideo.i18n import _, format_number, ngettext, normalize, resolve_language, set_language


@pytest.mark.parametrize(
    ("code", "expected"),
    [("de_AT.UTF-8", "de"), ("es-MX", "es"), ("EN", "en"), ("fr_FR", None), ("", None), (None, None)],
)
def test_normalize_maps_locales_to_supported_languages(code: str | None, expected: str | None) -> None:
    assert normalize(code) == expected


def test_resolve_language_follows_documented_precedence() -> None:
    env = {"QRVIDEO_LANG": "es"}
    assert resolve_language("de", saved="en", env=env, system=lambda: "en") == "de"
    assert resolve_language(None, saved="en", env=env, system=lambda: "en") == "es"
    assert resolve_language(None, saved="de", env={}, system=lambda: "es") == "de"
    assert resolve_language(None, env={}, system=lambda: "es_ES") == "es"
    # Nicht unterstuetzt: naechste Quelle, am Ende Englisch
    assert resolve_language("fr", saved="xx", env={"QRVIDEO_LANG": "it"}, system=lambda: "de") == "de"
    assert resolve_language(None, env={}, system=lambda: None) == "en"


@pytest.mark.parametrize(
    ("language", "value", "decimals", "expected"),
    [
        ("de", 400000, 0, "400.000"),
        ("en", 400000, 0, "400,000"),
        ("es", 400000, 0, "400.000"),
        ("de", 4000, 0, "4.000"),
        ("es", 4000, 0, "4000"),  # CLDR: Spanisch gruppiert erst ab fuenf Stellen
        ("de", 2.5, 1, "2,5"),
        ("en", 1234567.25, 1, "1,234,567.2"),
        ("es", 12345.5, 1, "12.345,5"),
        ("de", 999, 0, "999"),
    ],
)
def test_numbers_follow_the_language(language: str, value: float, decimals: int, expected: str) -> None:
    set_language(language)
    assert format_number(value, decimals) == expected


def test_catalog_translates_and_falls_back_to_msgid(tmp_path: Path) -> None:
    tool = catalog_tool()
    catalog = {
        "Cancelled": tool.Entry("Cancelled", None, ["Cancelado"]),
        "{n} frame": tool.Entry("{n} frame", "{n} frames", ["{n} fotograma", "{n} fotogramas"]),
    }
    target = tmp_path / "es" / "LC_MESSAGES" / "qrvideo.mo"
    target.parent.mkdir(parents=True)
    target.write_bytes(tool.compile_mo("es", catalog))
    set_language("es", localedir=tmp_path)
    assert i18n.current_language() == "es"
    assert _("Cancelled") == "Cancelado"
    assert ngettext("{n} frame", "{n} frames", 1).format(n=1) == "1 fotograma"
    assert ngettext("{n} frame", "{n} frames", 3).format(n=3) == "3 fotogramas"
    assert _("not in the catalog") == "not in the catalog"
    set_language("fr", localedir=tmp_path)  # ohne Katalog: englische msgids, Zahlen wie Englisch
    assert _("Cancelled") == "Cancelled"
    assert format_number(1000) == "1,000"
