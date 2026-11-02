"""Uebersetzungskataloge pflegen und pruefen (ADR-006), nur Standardbibliothek.

    uv run python tools/i18n_catalog.py update   # msgids aus dem Code in alle .po, .mo neu schreiben
    uv run python tools/i18n_catalog.py check    # Gate-Pruefung wie tests/test_i18n_catalog.py

Extrahiert werden Aufrufe von `_`, `N_` (ein Literal) und `ngettext` (zwei Literale) in den Quellpaketen.
Neue Eintraege bekommen ein leeres msgstr (das Gate meldet sie), veraltete werden entfernt.
"""

from __future__ import annotations

import ast
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = (ROOT / "src" / "qrvideo", ROOT / "src" / "qrvideo_gui")
LOCALE_DIR = ROOT / "src" / "qrvideo" / "locale"
DOMAIN = "qrvideo"
LANGUAGES = ("de", "en", "es")
SINGLE = frozenset({"_", "N_"})
PLURAL = "ngettext"
HEADER = (
    "Project-Id-Version: qrvideo\n"
    "Language: {language}\n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=UTF-8\n"
    "Content-Transfer-Encoding: 8bit\n"
    "Plural-Forms: nplurals=2; plural=(n != 1);\n"
)
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_PERCENT = re.compile(r"%(\(\w+\))?[sr]")  # Texte von argparse: %(prog)s, %s


@dataclass
class Entry:
    msgid: str
    plural: str | None = None
    strings: list[str] = field(default_factory=list)  # msgstr bzw. msgstr[0..n]
    locations: list[str] = field(default_factory=list)


def _literal(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_lookup(node: ast.expr) -> bool:
    """Name, Attribut oder Index (`_(TEXTE[k])`); f-Strings, `+` und Aufrufe bleiben Fehler."""
    return isinstance(node, (ast.Name, ast.Attribute, ast.Subscript))


def extract(sources: tuple[Path, ...] = SOURCES) -> tuple[dict[str, Entry], list[str]]:
    """msgid → Eintrag; dazu Fehler fuer Aufrufe ohne Literal (die liessen sich nie uebersetzen)."""
    found: dict[str, Entry] = {}
    errors: list[str] = []
    for path in sorted(p for source in sources for p in source.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            name, where = node.func.id, f"{rel}:{node.lineno}"
            if name in SINGLE:
                texts = [_literal(a) for a in node.args[:1]]
                plural = None
            elif name == PLURAL:
                texts = [_literal(a) for a in node.args[:2]]
                plural = texts[1] if len(texts) == 2 else None
            else:
                continue
            if texts and texts[0] is None and name == "_" and _is_lookup(node.args[0]):
                continue  # `_(KONSTANTE)`: Text steht per `N_` markiert an der Konstante
            if not texts or texts[0] is None or (name == PLURAL and plural is None):
                errors.append(f"{where}: {name}() braucht Zeichenkettenliterale")
                continue
            msgid = texts[0]
            assert msgid is not None
            entry = found.setdefault(msgid, Entry(msgid, plural))
            entry.locations.append(where)
    return found, errors


def _unquote(text: str) -> str:
    return str(ast.literal_eval(text))


def _quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    lines = escaped.split("\n")
    parts = [line + "\\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    if len(parts) <= 1:
        return f'"{parts[0] if parts else ""}"'
    return '""\n' + "\n".join(f'"{part}"' for part in parts)


def parse_po(text: str) -> dict[str, Entry]:
    """Eintraege einer .po-Datei (ohne Kopf); versteht das Format von `write_po` samt Fortsetzungszeilen."""
    entries: dict[str, Entry] = {}
    key = ""
    values: dict[str, str] = {}

    def flush() -> None:
        if "msgid" in values and values["msgid"]:
            plural = values.get("msgid_plural")
            if plural is None:
                strings = [values.get("msgstr", "")]
            else:
                strings = [values.get(f"msgstr[{i}]", "") for i in range(2)]
            entries[values["msgid"]] = Entry(values["msgid"], plural, strings)
        values.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if not line and values:
                flush()
            continue
        if line.startswith('"'):
            values[key] += _unquote(line)
            continue
        key, _, rest = line.partition(" ")
        if key == "msgid" and "msgid" in values:
            flush()
        values[key] = _unquote(rest)
    if values:
        flush()
    return entries


def write_po(language: str, entries: dict[str, Entry]) -> str:
    out = [
        f"# {language} – qrvideo (ADR-006). Pflege: tools/i18n_catalog.py",
        'msgid ""',
        "msgstr " + _quote(HEADER.format(language=language)),
        "",
    ]
    for msgid in sorted(entries):
        entry = entries[msgid]
        out += [f"#: {location}" for location in entry.locations]
        out.append("msgid " + _quote(msgid))
        if entry.plural is None:
            out.append("msgstr " + _quote(entry.strings[0] if entry.strings else ""))
        else:
            out.append("msgid_plural " + _quote(entry.plural))
            strings = entry.strings + [""] * (2 - len(entry.strings))
            out += [f"msgstr[{i}] " + _quote(s) for i, s in enumerate(strings[:2])]
        out.append("")
    return "\n".join(out)


def compile_mo(language: str, entries: dict[str, Entry]) -> bytes:
    """GNU-.mo, deterministisch (sortiert, ohne Hash-Tabelle); leere Uebersetzungen bleiben draussen."""
    pairs = {"": HEADER.format(language=language)}
    for entry in entries.values():
        if not all(entry.strings):
            continue
        if entry.plural is None:
            pairs[entry.msgid] = entry.strings[0]
        else:
            pairs[f"{entry.msgid}\0{entry.plural}"] = "\0".join(entry.strings)
    keys = sorted(pairs)
    ids = [k.encode("utf-8") for k in keys]
    strs = [pairs[k].encode("utf-8") for k in keys]
    start = 7 * 4 + 16 * len(keys)
    offsets_ids, offsets_strs, blob_ids, blob_strs = [], [], b"", b""
    for item in ids:
        offsets_ids.append((len(item), start + len(blob_ids)))
        blob_ids += item + b"\0"
    for item in strs:
        offsets_strs.append((len(item), start + len(blob_ids) + len(blob_strs)))
        blob_strs += item + b"\0"
    header = struct.pack("<7I", 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + 8 * len(keys), 0, 0)
    table = b"".join(struct.pack("<2I", *o) for o in offsets_ids + offsets_strs)
    return header + table + blob_ids + blob_strs


def po_path(language: str, locale_dir: Path = LOCALE_DIR) -> Path:
    return locale_dir / language / "LC_MESSAGES" / f"{DOMAIN}.po"


def _placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text)) | {f"%{m.group(1) or ''}" for m in _PERCENT.finditer(text)}


def check(
    sources: tuple[Path, ...] = SOURCES, locale_dir: Path = LOCALE_DIR, languages: tuple[str, ...] = LANGUAGES
) -> list[str]:
    """Alle Befunde des Katalog-Gates; leer = gruen."""
    code, problems = extract(sources)
    for msgid, entry in code.items():
        if entry.plural is not None and _placeholders(msgid) != _placeholders(entry.plural):
            problems.append(f"Platzhalter Singular/Plural verschieden: {msgid!r}")
        if "" in _placeholders(msgid):
            problems.append(f"Platzhalter ohne Namen: {msgid!r}")
    for language in languages:
        path = po_path(language, locale_dir)
        if not path.is_file():
            problems.append(f"{language}: {path.name} fehlt")
            continue
        catalog = parse_po(path.read_text(encoding="utf-8"))
        problems += [f"{language}: fehlt im Katalog: {m!r}" for m in sorted(code.keys() - catalog.keys())]
        problems += [f"{language}: veraltet im Katalog: {m!r}" for m in sorted(catalog.keys() - code.keys())]
        for msgid, entry in catalog.items():
            expected = _placeholders(entry.plural or msgid)
            if not all(entry.strings):
                problems.append(f"{language}: nicht uebersetzt: {msgid!r}")
            elif any(_placeholders(s) != expected for s in entry.strings):
                problems.append(f"{language}: Platzhalter weichen ab: {msgid!r}")
        mo = path.with_suffix(".mo")
        if not mo.is_file() or mo.read_bytes() != compile_mo(language, catalog):
            problems.append(f"{language}: {mo.name} fehlt oder ist veraltet (update laufen lassen)")
    return problems


def update(sources: tuple[Path, ...] = SOURCES, locale_dir: Path = LOCALE_DIR) -> None:
    code, errors = extract(sources)
    if errors:
        raise SystemExit("\n".join(errors))
    for language in LANGUAGES:
        path = po_path(language, locale_dir)
        old = parse_po(path.read_text(encoding="utf-8")) if path.is_file() else {}
        merged = {
            msgid: Entry(msgid, entry.plural, old[msgid].strings if msgid in old else [], entry.locations)
            for msgid, entry in code.items()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(write_po(language, merged), encoding="utf-8", newline="\n")
        path.with_suffix(".mo").write_bytes(compile_mo(language, parse_po(path.read_text(encoding="utf-8"))))


def main(argv: list[str]) -> int:
    if argv == ["update"]:
        update()
        return 0
    if argv == ["check"]:
        problems = check()
        print("\n".join(problems) or "Kataloge vollstaendig")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
