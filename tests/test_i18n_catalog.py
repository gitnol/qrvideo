"""Katalog-Gate (ADR-006): jede msgid in jeder Sprache uebersetzt, Platzhalter gleich, .mo aktuell."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "i18n_catalog.py"


def catalog_tool() -> ModuleType:
    """`tools/` ist kein Paket: einmal laden und registrieren (für dataclasses)."""
    if "i18n_catalog" in sys.modules:
        return sys.modules["i18n_catalog"]
    spec = importlib.util.spec_from_file_location("i18n_catalog", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["i18n_catalog"] = module
    spec.loader.exec_module(module)
    return module


def test_shipped_catalogs_are_complete_and_compiled() -> None:
    assert catalog_tool().check() == []


@pytest.fixture
def project(tmp_path: Path) -> tuple[ModuleType, Path, Path]:
    tool = catalog_tool()
    source = tmp_path / "pkg"
    source.mkdir()
    (source / "m.py").write_text(
        'from qrvideo.i18n import _, ngettext\nA = _("Save {name}")\n'
        'B = ngettext("{n} file", "{n} files", 2)\n',
        encoding="utf-8",
    )
    return tool, source, tmp_path / "locale"


def _po(tool: ModuleType, locale: Path, language: str, entries: dict[str, list[str]]) -> None:
    catalog = {
        "Save {name}": tool.Entry("Save {name}", None, entries.get("Save {name}", [])),
        "{n} file": tool.Entry("{n} file", "{n} files", entries.get("{n} file", [])),
    }
    path = tool.po_path(language, locale)
    path.parent.mkdir(parents=True)
    path.write_text(tool.write_po(language, catalog), encoding="utf-8")
    path.with_suffix(".mo").write_bytes(
        tool.compile_mo(language, tool.parse_po(path.read_text(encoding="utf-8")))
    )


def test_complete_catalog_passes(project: tuple[ModuleType, Path, Path]) -> None:
    tool, source, locale = project
    _po(tool, locale, "es", {"Save {name}": ["Guardar {name}"], "{n} file": ["{n} archivo", "{n} archivos"]})
    assert tool.check((source,), locale, ("es",)) == []


def test_gate_reports_missing_wrong_and_stale(project: tuple[ModuleType, Path, Path]) -> None:
    tool, source, locale = project
    _po(tool, locale, "es", {"Save {name}": ["Guardar {nombre}"], "{n} file": ["", ""]})
    problems = tool.check((source,), locale, ("es", "de"))
    assert "es: Platzhalter weichen ab: 'Save {name}'" in problems
    assert "es: nicht uebersetzt: '{n} file'" in problems
    assert any(p.startswith("de: qrvideo.po fehlt") for p in problems)
    (source / "m.py").write_text(
        'from qrvideo.i18n import _\nA = _("Save {name}")\nC = _("New")\n', encoding="utf-8"
    )
    problems = tool.check((source,), locale, ("es",))
    assert "es: fehlt im Katalog: 'New'" in problems
    assert "es: veraltet im Katalog: '{n} file'" in problems


def test_gate_reports_stale_mo_and_non_literal_calls(project: tuple[ModuleType, Path, Path]) -> None:
    tool, source, locale = project
    _po(tool, locale, "es", {"Save {name}": ["Guardar {name}"], "{n} file": ["{n} archivo", "{n} archivos"]})
    po = tool.po_path("es", locale)
    po.write_text(po.read_text(encoding="utf-8").replace("Guardar", "Grabar"), encoding="utf-8")
    assert tool.check((source,), locale, ("es",)) == [
        "es: qrvideo.mo fehlt oder ist veraltet (update laufen lassen)"
    ]
    (source / "m.py").write_text(
        'from qrvideo.i18n import _\nname = "x"\nA = _(f"Save {name}")\n', encoding="utf-8"
    )
    assert any("braucht Zeichenkettenliterale" in p for p in tool.check((source,), locale, ("es",)))
    (source / "m.py").write_text(
        'from qrvideo.i18n import _\nA = _("Save {name}") + _(TEXTS[0])\n', encoding="utf-8"
    )
    assert not any("Zeichenkettenliterale" in p for p in tool.check((source,), locale, ("es",)))


def test_update_keeps_translations_and_po_round_trips(project: tuple[ModuleType, Path, Path]) -> None:
    tool, source, locale = project
    text = 'Zeile 1\nZeile "2"\t\\ende'
    entry = tool.Entry(text, None, ["Línea 1\nLínea «2»"])
    parsed = tool.parse_po(tool.write_po("es", {text: entry}))
    assert parsed[text].strings == ["Línea 1\nLínea «2»"]


def test_percent_placeholders_of_argparse_are_compared() -> None:
    placeholders = catalog_tool()._placeholders
    assert placeholders("%(prog)s: error: %(message)s %s") == {"%(prog)", "%(message)", "%"}
    assert placeholders("%(prog)s: Fehler: %(nachricht)s") != placeholders("%(prog)s: error: %(message)s")
