"""Video -> Frames -> Module abtasten -> qrcodegenmod.reader -> Nutzlast.

Ersetzt analyze_video.py: keine 15-fach kopierten Ausschnitte, kein pyzbar. Die Thesis-Korrektur
(2x2-Mittelwert, Schwelle 128) bleibt, die Fehlerkorrektur uebernimmt Reed-Solomon im Reader.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt

from qrcodegenmod.reader import QrDecodeError, decode_modules

from .container import ContainerError, FrameHeader, assemble, group_layout, unpack_symbol
from .erasure import recover
from .i18n import _
from .layout import THESIS_LAYOUT, FrameLayout
from .videoio import read_video

BLANK_BRIGHTNESS = 220.0  # Thesis: Mittelwert > 220 gilt als weisser, leerer Slot


@dataclass
class DecodeReport:
    frames: int = 0
    qr_codes: int = 0
    blank_slots: int = 0
    corrected_bytes: int = 0
    failures: list[tuple[int, int, str]] = field(default_factory=list)  # (Frame, Slot, Grund)


_Item = tuple[int, int, FrameHeader | None, bytes]  # (Frame, Slot, Kopf des Frames oder None, Daten)


def _decode_slots(
    frame: npt.NDArray[np.uint8], index: int, layout: FrameLayout, report: DecodeReport
) -> list[bytes | None]:
    """Pro Slot die Daten, None fuer leere oder unlesbare Slots (letztere landen im Report)."""
    modules, brightness = layout.sample(frame)
    out: list[bytes | None] = []
    for slot in range(layout.slots):
        if brightness[slot] > BLANK_BRIGHTNESS:
            report.blank_slots += 1
            out.append(None)
            continue
        try:
            decoded = decode_modules(modules[slot])
        except QrDecodeError as exc:
            report.failures.append((index, slot, str(exc)))
            out.append(None)
            continue
        report.qr_codes += 1
        report.corrected_bytes += decoded.corrected_bytes
        out.append(decoded.data)
    return out


def _read_header(data: bytes | None, index: int, report: DecodeReport) -> FrameHeader | None:
    if data is None:
        return None
    try:
        return FrameHeader.unpack(data)
    except ContainerError as exc:
        report.failures.append((index, 0, str(exc)))
        return None


def _v2_chunks(items: list[_Item], per_frame: int) -> dict[int, bytes]:
    """v2: Position aus dem Frame-Index im Kopf; Daten aus Frames ohne lesbaren Kopf sind verloren."""
    chunks: dict[int, bytes] = {}
    for _frame, slot, header, data in items:
        if header is not None:
            chunks.setdefault(header.frame_index * per_frame + slot - 1, data)
    return chunks


def _v3_chunks(header: FrameHeader, items: list[_Item], report: DecodeReport) -> dict[int, bytes]:
    """v3: Position aus dem Symbolindex im Daten-QR; CRC-Fehler werden zu Ausloeschungen."""
    symbols: dict[int, bytes] = {}
    for frame, slot, _header, data in items:
        try:
            index, chunk = unpack_symbol(data)
        except ContainerError as exc:
            report.failures.append((frame, slot, str(exc)))
            continue
        symbols.setdefault(index, chunk)
    return _recover_groups(header, symbols)


def _recover_groups(header: FrameHeader, symbols: dict[int, bytes]) -> dict[int, bytes]:
    """Fehlende Datensymbole je Gruppe aus der Paritaet ergaenzen; ohne Paritaet meldet `assemble` Luecken."""
    size, m = header.chunk_bytes, header.group_parity
    chunks: dict[int, bytes] = {}
    for number, (first, start, k) in enumerate(group_layout(header)):
        group = {p: symbols[start + p] for p in range(k + m) if start + p in symbols}
        if m and any(p not in group for p in range(k)):
            try:
                restored = recover({p: s.ljust(size, b"\0") for p, s in group.items()}, k, m)
            except ContainerError as exc:
                raise ContainerError(_("Group {number}: {error}").format(number=number, error=exc)) from exc
            group = dict(enumerate(restored))
        chunks.update({first + p: group[p] for p in range(k) if p in group})
    last = max(1, -(-header.payload_length // size)) - 1
    if last in chunks:  # ein wiederhergestellter letzter Chunk traegt die Polsterung
        chunks[last] = chunks[last][: header.payload_length - last * size]
    return chunks


def decode_frames(
    frames: Iterable[npt.NDArray[np.uint8]], layout: FrameLayout = THESIS_LAYOUT
) -> tuple[bytes, DecodeReport]:
    """Format v2/v3: Kopf in Slot 0, Daten in Slot 1..n.

    v2 ordnet ueber den Frame-Index im Kopf, v3 ueber den Symbolindex im Daten-QR - dort zaehlen auch Frames,
    deren Kopf unlesbar ist.
    """
    report = DecodeReport()
    header: FrameHeader | None = None
    items: list[_Item] = []
    for index, frame in enumerate(frames):
        report.frames += 1
        slots = _decode_slots(frame, index, layout, report)
        current = _read_header(slots[0], index, report)
        if (
            current
            and header
            and (current.sha256, current.frame_count) != (header.sha256, header.frame_count)
        ):
            report.failures.append((index, 0, "Kopf gehoert zu einer anderen Nutzlast"))
            continue
        header = header or current
        items += [(index, slot, current, data) for slot, data in enumerate(slots[1:], 1) if data is not None]
    if header is None:
        raise ContainerError(_("No readable header (v2/v3) in the video"))
    if header.version == 3:
        return assemble(header, _v3_chunks(header, items, report)), report
    return assemble(header, _v2_chunks(items, layout.slots - 1)), report


def decode_frames_legacy(
    frames: Iterable[npt.NDArray[np.uint8]], layout: FrameLayout = THESIS_LAYOUT
) -> tuple[bytes, DecodeReport]:
    """Thesis-Videos (2019): Slot 0 = verschluesselter Status (uebersprungen), danach Armor-Text."""
    report = DecodeReport()
    parts: list[bytes] = []
    for index, frame in enumerate(frames):
        report.frames += 1
        slots = _decode_slots(frame, index, layout, report)
        parts.extend(data for data in slots[1:] if data is not None)
    if report.failures:
        first = report.failures[0]
        text = _("{count} QR codes unreadable, first: frame {frame}, slot {slot}")
        raise ContainerError(text.format(count=len(report.failures), frame=first[0], slot=first[1]))
    return b"".join(parts), report


def decode_video(path: Path, legacy: bool = False) -> tuple[bytes, DecodeReport]:
    frames = read_video(path)
    return decode_frames_legacy(frames) if legacy else decode_frames(frames)
