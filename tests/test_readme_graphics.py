"""README-Grafiken (I35): aus Messdaten erzeugt, eingecheckt und aktuell."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

TOOL = Path(__file__).resolve().parent.parent / "tools" / "readme_graphics.py"


def graphics_tool() -> ModuleType:
    """`tools/` ist kein Paket: einmal laden und registrieren."""
    if "readme_graphics" in sys.modules:
        return sys.modules["readme_graphics"]
    spec = importlib.util.spec_from_file_location("readme_graphics", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["readme_graphics"] = module
    spec.loader.exec_module(module)
    return module


def test_committed_graphics_match_the_generator() -> None:
    assert graphics_tool().stale() == []


def test_every_language_gets_its_own_charts() -> None:
    names = {path.relative_to(graphics_tool().IMAGES).as_posix() for path in graphics_tool().build()}
    for lang in ("de", "en", "es"):
        assert {
            f"{lang}/stats.svg",
            f"{lang}/speed.svg",
            f"{lang}/pipeline.svg",
            f"{lang}/architecture.svg",
        } <= names
    assert "logo.svg" in names


def test_speedup_comes_from_the_benchmark_results(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"ms_per_qr": {"a": 50.0, "b": 5.0, "c": 1.0, "d": 0.5}}), encoding="utf-8")
    svg = graphics_tool().speed_chart("en", results)
    assert "100× faster" in svg
    assert "50.00 ms" in svg and "0.50 ms" in svg


def test_numbers_follow_the_language() -> None:
    assert "52,87 ms" in graphics_tool().speed_chart("de")
    assert "52.87 ms" in graphics_tool().speed_chart("en")


def test_building_charts_keeps_the_process_language() -> None:
    from qrvideo.i18n import current_language

    graphics_tool().stats_strip("es")
    assert current_language() == "de"


def test_architecture_shows_the_three_layers_and_the_external_tools() -> None:
    svg = graphics_tool().architecture("en")
    for name in ("qrvideo-gui", "qrvideo", "qrcodegenmod", "GnuPG", "ffmpeg", "yt-dlp", "import-linter"):
        assert name in svg
    assert "Sprachen (gettext)" in graphics_tool().architecture("de")
