"""Logo und README-Grafiken als SVG, je Sprache, reproduzierbar aus den Messdaten (I35).

    uv run python tools/readme_graphics.py          # schreibt docs/images/logo.svg und <lang>/*.svg
    uv run python tools/readme_graphics.py --check   # Exit 1, wenn eine eingecheckte Grafik veraltet ist

Das Tempo-Diagramm liest `bench/results.json` (`bench/bench_qrcode.py`); die übrigen Kennzahlen sind
Messungen aus `docs/STATE.md` (Ende-zu-Ende 2,55 MB, YouTube-Lauf v3) und stehen unten mit Quelle.
Farben folgen per `prefers-color-scheme` dem hellen oder dunklen Modus der Seite.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path

from qrvideo.i18n import SUPPORTED, current_language, format_number, set_language

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
RESULTS = ROOT / "bench" / "results.json"

# Kennzahlen aus docs/STATE.md (I17d): Ende-zu-Ende 2,55 MB → 72 Frames; YouTube v3 → 659 QR, 0 unlesbar
END_TO_END_MB = 2.55
END_TO_END_FRAMES = 72
FPS = 30
QR_PER_FRAME = 15
YOUTUBE_QR = 659
YOUTUBE_UNREADABLE = 0

FONT = "font-family:'Segoe UI',system-ui,-apple-system,Helvetica,Arial,sans-serif"
STYLE = f"""<style>
text{{{FONT};fill:#1f2937}} .muted{{fill:#6b7280}} .accent{{fill:#d97706}} .box{{fill:#f8fafc;stroke:#cbd5e1}}
.arrow{{stroke:#94a3b8;fill:none}} .tip{{fill:#94a3b8}}
@media (prefers-color-scheme: dark){{text{{fill:#e5e7eb}} .muted{{fill:#9ca3af}} .accent{{fill:#fbbf24}}
.box{{fill:#111827;stroke:#374151}} .arrow{{stroke:#6b7280}} .tip{{fill:#6b7280}}}}
</style>"""

BAR_COLORS = ("#94a3b8", "#38bdf8", "#14b8a6", "#f59e0b")

Line3 = tuple[str, str, str]


@dataclass(frozen=True)
class Texts:
    headline: str
    subtitle: str
    rows: tuple[str, str, str, str]
    source: str
    stats: tuple[Line3, Line3, Line3]
    steps: tuple[Line3, Line3, Line3, Line3, Line3]


TEXTS: dict[str, Texts] = {
    "de": Texts(
        headline="{factor}× schneller als das Original",
        subtitle="Zeit pro QR-Code (Version 40) · kürzer ist besser · logarithmische Skala",
        rows=("Original qrcodegen 1.8.0", "Thesis 2019", "2026 ohne Numba", "2026 mit Numba"),
        source="Messung: bench/results.json, {n} QR-Codes je Variante",
        stats=(
            ("{factor}×", "schnellere QR-Erzeugung", "als das Original"),
            ("{seconds} s", "Video für {mb} MB", "{fps} fps, {qr} QR-Codes je Bild"),
            ("{unreadable}", "unlesbare QR-Codes", "nach YouTube ({total} QR-Codes)"),
        ),
        steps=(
            ("Datei", "beliebiger Inhalt", ""),
            ("GnuPG", "verschlüsselt", "und signiert"),
            ("QR-Video", "{qr} QR je Bild", "Parität heilt Ausfälle"),
            ("Kanal", "YouTube oder", "Gemeinsamer Ordner"),
            ("Datei", "entschlüsselt,", "Signatur geprüft"),
        ),
    ),
    "en": Texts(
        headline="{factor}× faster than the original",
        subtitle="Time per QR code (version 40) · shorter is better · logarithmic scale",
        rows=("Original qrcodegen 1.8.0", "Thesis 2019", "2026 without Numba", "2026 with Numba"),
        source="Measured: bench/results.json, {n} QR codes per variant",
        stats=(
            ("{factor}×", "faster QR generation", "than the original"),
            ("{seconds} s", "of video for {mb} MB", "{fps} fps, {qr} QR codes per frame"),
            ("{unreadable}", "unreadable QR codes", "after YouTube ({total} QR codes)"),
        ),
        steps=(
            ("File", "any content", ""),
            ("GnuPG", "encrypted", "and signed"),
            ("QR video", "{qr} QR per frame", "parity heals losses"),
            ("Channel", "YouTube or", "shared folder"),
            ("File", "decrypted,", "signature checked"),
        ),
    ),
    "es": Texts(
        headline="{factor} veces más rápido que el original",
        subtitle="Tiempo por código QR (versión 40) · más corto es mejor · escala logarítmica",
        rows=("Original qrcodegen 1.8.0", "Tesis 2019", "2026 sin Numba", "2026 con Numba"),
        source="Medición: bench/results.json, {n} códigos QR por variante",
        stats=(
            ("{factor}×", "generación de QR más rápida", "que el original"),
            ("{seconds} s", "de vídeo para {mb} MB", "{fps} fps, {qr} códigos QR por fotograma"),
            ("{unreadable}", "códigos QR ilegibles", "tras YouTube ({total} códigos QR)"),
        ),
        steps=(
            ("Archivo", "cualquier contenido", ""),
            ("GnuPG", "cifrado", "y firmado"),
            ("Vídeo QR", "{qr} QR por fotograma", "la paridad repara"),
            ("Canal", "YouTube o", "carpeta compartida"),
            ("Archivo", "descifrado,", "firma verificada"),
        ),
    ),
}


def _in_language(lang: str, build: Callable[[], str]) -> str:
    """`format_number` richtet sich nach der prozessweiten Sprache; danach die vorige wiederherstellen."""
    previous = current_language()
    set_language(lang)
    try:
        return build()
    finally:
        set_language(previous)


def _svg(width: int, height: int, title: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" role="img" aria-label="{escape(title)}">\n<title>{escape(title)}</title>\n'
        f"{STYLE}\n{body}</svg>\n"
    )


def _text(x: float, y: float, content: str, size: int, extra: str = "") -> str:
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}" {extra}>{escape(content)}</text>\n'


def _load(results: Path) -> tuple[list[float], int | None]:
    data = json.loads(results.read_text(encoding="utf-8"))
    return [float(v) for v in data["ms_per_qr"].values()], data.get("meta", {}).get("n")


def _factor(times: list[float]) -> str:
    return format_number(times[0] / times[-1])


def speed_chart(lang: str, results: Path = RESULTS) -> str:
    """Balken auf logarithmischer Skala (0,1 ms bis 100 ms) mit Zeit und Faktor zum Original."""
    texts = TEXTS[lang]
    times, n = _load(results)

    def build() -> str:
        body = _text(16, 34, texts.headline.format(factor=_factor(times)), 22, 'font-weight="700"')
        body += _text(16, 58, texts.subtitle, 13, 'class="muted"')
        left, span = 230, 380
        for i, (label, ms) in enumerate(zip(texts.rows, times, strict=True)):
            y = 84 + i * 40
            share = max(math.log10(ms / 0.1) / 3, 0.02)
            body += _text(16, y + 19, label, 14)
            body += (
                f'<rect x="{left}" y="{y + 4}" width="{span * share:.1f}" height="22" rx="4" '
                f'fill="{BAR_COLORS[i]}"/>\n'
            )
            value = f"{format_number(ms, 2)} ms · {format_number(times[0] / ms)}×"
            body += _text(left + span * share + 8, y + 20, value, 13, 'font-weight="600"')
        body += _text(16, 262, texts.source.format(n=format_number(n or 0)), 11, 'class="muted"')
        return _svg(760, 276, texts.headline.format(factor=_factor(times)), body)

    return _in_language(lang, build)


def stats_strip(lang: str, results: Path = RESULTS) -> str:
    """Drei Kennzahlen: Tempo, Videolänge je Datenmenge, Lesbarkeit nach YouTube."""
    texts = TEXTS[lang]
    times, _ = _load(results)

    def build() -> str:
        values = {
            "factor": _factor(times),
            "seconds": format_number(END_TO_END_FRAMES / FPS, 1),
            "mb": format_number(END_TO_END_MB, 2),
            "fps": FPS,
            "qr": QR_PER_FRAME,
            "unreadable": YOUTUBE_UNREADABLE,
            "total": format_number(YOUTUBE_QR),
        }
        body, captions = "", []
        for i, (big, line1, line2) in enumerate(texts.stats):
            x = 4 + i * 252
            lines = [line1.format(**values), line2.format(**values)]
            captions.append(f"{big.format(**values)} {lines[0]}")
            body += f'<rect class="box" x="{x}" y="4" width="240" height="112" rx="12" stroke-width="1.5"/>\n'
            body += _text(
                x + 120, 50, big.format(**values), 36, 'class="accent" font-weight="800" text-anchor="middle"'
            )
            body += _text(x + 120, 78, lines[0], 14, 'font-weight="600" text-anchor="middle"')
            body += _text(x + 120, 98, lines[1], 12, 'class="muted" text-anchor="middle"')
        return _svg(760, 120, " · ".join(captions), body)

    return _in_language(lang, build)


def pipeline(lang: str) -> str:
    """Ablauf in fünf Schritten von der Datei über den Kanal zurück zur Datei."""
    steps = TEXTS[lang].steps
    body = ""
    for i, (title, line1, line2) in enumerate(steps):
        x = 4 + i * 152
        body += f'<rect class="box" x="{x}" y="4" width="124" height="96" rx="12" stroke-width="1.5"/>\n'
        body += _text(x + 62, 40, title, 16, 'font-weight="700" text-anchor="middle"')
        body += _text(x + 62, 64, line1.format(qr=QR_PER_FRAME), 11, 'class="muted" text-anchor="middle"')
        body += _text(x + 62, 80, line2, 11, 'class="muted" text-anchor="middle"')
        if i < len(steps) - 1:
            body += f'<path class="arrow" d="M{x + 130} 52 H{x + 144}" stroke-width="2"/>\n'
            body += f'<path class="tip" d="M{x + 146} 52 l-7 -5 v10 z"/>\n'
    label = " → ".join(step[0] for step in steps)
    return _svg(760, 104, label, body)


def logo() -> str:
    """Filmbild mit Perforation; darin ein QR-Code aus Suchmustern, Datenpunkten und einem Play-Dreieck."""
    finders = ""
    for fx, fy in ((34, 34), (73, 34), (34, 73)):
        finders += (
            f'<rect x="{fx}" y="{fy}" width="21" height="21" rx="2" fill="#0b1f3a"/>'
            f'<rect x="{fx + 3}" y="{fy + 3}" width="15" height="15" rx="1" fill="#ffffff"/>'
            f'<rect x="{fx + 6}" y="{fy + 6}" width="9" height="9" rx="1" fill="#0b1f3a"/>\n'
        )
    dots = "".join(
        f'<rect x="{x}" y="{y}" width="5" height="5" rx="1" fill="#0b1f3a"/>'
        for x, y in ((61, 34), (61, 46), (61, 61), (34, 61), (46, 61), (73, 61), (61, 73))
    )
    holes = "".join(
        f'<rect x="{x}" y="{y}" width="8" height="10" rx="2" fill="#ffffff" fill-opacity="0.35"/>'
        for x in (9, 111)
        for y in (17, 41, 65, 89, 113 - 12)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128" '
        'role="img" aria-label="qrvideo">\n<title>qrvideo</title>\n'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#0b1f3a"/><stop offset="1" stop-color="#0d9488"/>'
        "</linearGradient></defs>\n"
        '<rect width="128" height="128" rx="28" fill="url(#g)"/>\n'
        f"{holes}\n"
        '<rect x="26" y="26" width="76" height="76" rx="10" fill="#ffffff"/>\n'
        f"{finders}{dots}\n"
        '<path d="M76 72 L96 83.5 L76 95 Z" fill="#f59e0b" stroke="#f59e0b" stroke-width="3" '
        'stroke-linejoin="round"/>\n'
        "</svg>\n"
    )


def build() -> dict[Path, str]:
    files = {IMAGES / "logo.svg": logo()}
    for lang in SUPPORTED:
        files[IMAGES / lang / "stats.svg"] = stats_strip(lang)
        files[IMAGES / lang / "speed.svg"] = speed_chart(lang)
        files[IMAGES / lang / "pipeline.svg"] = pipeline(lang)
    return files


def stale() -> list[Path]:
    """Grafiken, die fehlen oder nicht dem Erzeuger entsprechen (Zeilenenden egal)."""
    return [
        path
        for path, content in build().items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="nur prüfen, nichts schreiben")
    args = parser.parse_args(argv)
    if args.check:
        outdated = stale()
        for path in outdated:
            print(f"veraltet: {path.relative_to(ROOT)}")
        return 1 if outdated else 0
    for path, content in build().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
