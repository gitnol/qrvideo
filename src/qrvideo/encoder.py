"""Nutzlast -> Frames -> Video. Ein Prozess-Pool fuer die ganze Datei, Frames werden gestreamt.

Thesis: Pool pro Charge neu (Numba kompilierte in jedem Worker neu), numpy.append in Schleifen,
alle Frames im RAM. Hier: Pool einmal, Numba-Cache auf Platte, ein gleitendes Fenster von hoechstens
2 x Worker Frames in Arbeit (Code-Review #1: pool.map staute fertige Frames im RAM) -> ffmpeg-Pipe.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import numpy.typing as npt

import qrcodegenmod as q

from .container import GROUP_SYMBOLS, FramePlan, header_payload, plan_frames, plan_frames_v3
from .layout import THESIS_LAYOUT, FrameLayout
from .videoio import DEFAULT_SETTINGS, VideoSettings, write_video

_V40 = {"minversion": 40, "maxversion": 40, "boostecl": False}


def render_tile(data: bytes, ecl: q.Ecc, layout: FrameLayout = THESIS_LAYOUT) -> npt.NDArray[np.uint8]:
    """Ein QR-Code V40 mit Maske 1 (Thesis-Einstellung) als Bildkachel."""
    qr = q.QrCode.encode_binary(data, ecl, mask=1, **_V40)
    return qr.to_image(scale=layout.scale, border=layout.border)


def render_frame(plan: FramePlan, layout: FrameLayout = THESIS_LAYOUT) -> npt.NDArray[np.uint8]:
    ecl = next(e for e in q.Ecc if e.ordinal == plan.header.ecc_ordinal)
    tiles: list[npt.NDArray[np.uint8] | None] = [
        render_tile(header_payload(plan.header), q.Ecc.MEDIUM, layout)
    ]
    tiles += [render_tile(chunk, ecl, layout) for chunk in plan.chunks]
    return layout.compose(tiles)


# v3: die letzten Frames wiederholt; eine bitratenbegrenzte Zweitkodierung zerstoerte 2-3 Frames kurz vor dem
# Videoende (Messung I17d), Kopien ersetzt der Decoder ueber den Symbolindex
TAIL_FRAMES = 3
# Standard fuer CLI und GUI seit I18: Format v3 mit ECC L und 10 % Paritaet (Live-Messung I17e)
DEFAULT_ECC = q.Ecc.LOW
DEFAULT_PARITY_PERCENT = 10
WINDOWS_MAX_WORKERS = 61  # Grenze von ProcessPoolExecutor unter Windows (Code-Review #9)


def worker_count(requested: int | None, frames: int, windows: bool = os.name == "nt") -> int:
    """Gewuenschte bzw. alle Kerne, hoechstens so viele wie Frames, unter Windows hoechstens 61."""
    count = requested if requested is not None else min(frames, os.cpu_count() or 1)
    return min(count, WINDOWS_MAX_WORKERS) if windows else count


def iter_frames(
    payload: bytes,
    ecl: q.Ecc = q.Ecc.MEDIUM,
    workers: int | None = None,
    version: int = 2,
    parity: int = 0,
) -> Iterator[npt.NDArray[np.uint8]]:
    """Frames in Reihenfolge; ab `workers` > 1 parallel, mit hoechstens 2 x workers Frames in Arbeit.

    `version=3` schreibt Format v3 mit `parity` Paritaetssymbolen je Gruppe und Nachlauf (ADR-003), sonst v2.
    """
    slots = THESIS_LAYOUT.slots - 1
    if version == 3:
        plans = plan_frames_v3(payload, ecl, slots, parity)
        plans += plans[-TAIL_FRAMES:]
    else:
        plans = plan_frames(payload, ecl, slots)
    workers = worker_count(workers, len(plans))
    if workers <= 1:
        yield from (render_frame(p) for p in plans)
        return
    todo = iter(plans)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = deque(
            pool.submit(render_frame, plan) for _, plan in zip(range(2 * workers), todo, strict=False)
        )
        while pending:
            frame = pending.popleft().result()
            following = next(todo, None)
            if following is not None:
                pending.append(pool.submit(render_frame, following))
            yield frame


def encode_file(
    source: Path,
    target: Path,
    ecl: q.Ecc = q.Ecc.MEDIUM,
    workers: int | None = None,
    settings: VideoSettings = DEFAULT_SETTINGS,
    parity: int | None = None,
) -> int:
    """Datei (typisch .gpg) als QR-Code-Video schreiben; `parity` None = Format v2. Rueckgabe: Frames."""
    return encode_bytes(source.read_bytes(), target, ecl, workers, settings, parity)


def encode_bytes(
    payload: bytes,
    target: Path,
    ecl: q.Ecc = q.Ecc.MEDIUM,
    workers: int | None = None,
    settings: VideoSettings = DEFAULT_SETTINGS,
    parity: int | None = None,
) -> int:
    """Nutzlast ohne Zwischendatei als Video schreiben; `parity` None = Format v2. Rueckgabe: Frames."""
    version = 2 if parity is None else 3
    return write_video(target, iter_frames(payload, ecl, workers, version, parity or 0), settings)


def parity_symbols(percent: int) -> int | None:
    """Prozent der Symbole je Gruppe -> Paritaetssymbole m; 0 % = None = Format v2 (ADR-003)."""
    return round(GROUP_SYMBOLS * percent / 100) or None


def frame_count(payload: bytes, ecl: q.Ecc, parity: int | None = None) -> int:
    """Frames, die `encode_bytes` mit denselben Werten schreibt (v3 inklusive Nachlauf)."""
    slots = THESIS_LAYOUT.slots - 1
    if parity is None:
        return len(plan_frames(payload, ecl, slots))
    planned = len(plan_frames_v3(payload, ecl, slots, parity))
    return planned + min(TAIL_FRAMES, planned)
