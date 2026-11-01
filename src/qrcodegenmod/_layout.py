"""Geometrie einer QR-Code-Version, einmal berechnet und gecacht.

Entspricht den Thesis-Aenderungen 7 (Funktionsmuster vorberechnen), 10 (cw2datapos:
Zickzack-Reihenfolge der Datenmodule) und 11 (Masken mit NumPy). Neu: Pro
(Version, ECC, Maske) gibt es eine fertige Vorlage, in die nur noch die Datenbits
per XOR geschrieben werden.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache, lru_cache

import numpy as np

from ._tables import check_version, num_raw_data_modules


@dataclass(frozen=True)
class VersionLayout:
    version: int
    size: int
    is_function: np.ndarray  # bool (size, size)
    base: np.ndarray  # bool (size, size): Funktionsmuster ohne Formatbits
    data_positions: np.ndarray  # int64: flache Indizes der Datenmodule in Zickzack-Reihenfolge


def _alignment_positions(version: int, size: int) -> list[int]:
    if version == 1:
        return []
    numalign = version // 7 + 2
    step = (version * 8 + numalign * 3 + 5) // (numalign * 4 - 4) * 2
    result = [size - 7 - i * step for i in range(numalign - 1)] + [6]
    return list(reversed(result))


def _version_bits(version: int) -> int:
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return version << 12 | rem


def format_bits(ecl_formatbits: int, mask: int) -> int:
    data = ecl_formatbits << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


@cache
def _format_coordinates(size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(ys, xs, bitindex) beider Formatbit-Kopien; Reihenfolge wie bei nayuki."""
    coords: list[tuple[int, int, int]] = []  # (x, y, bit)
    coords += [(8, i, i) for i in range(6)]
    coords += [(8, 7, 6), (8, 8, 7), (7, 8, 8)]
    coords += [(14 - i, 8, i) for i in range(9, 15)]
    coords += [(size - 1 - i, 8, i) for i in range(8)]
    coords += [(8, size - 15 + i, i) for i in range(8, 15)]
    xs, ys, bits = (np.array(col, dtype=np.int64) for col in zip(*coords, strict=True))
    return ys, xs, bits


def _draw_function_patterns(version: int, size: int) -> tuple[np.ndarray, np.ndarray]:
    modules = np.zeros((size, size), dtype=bool)
    is_function = np.zeros((size, size), dtype=bool)

    def put(x: int, y: int, dark: bool) -> None:
        modules[y, x] = dark
        is_function[y, x] = True

    for i in range(size):  # Timing-Muster
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):  # Finder-Muster inkl. Trennrand
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = cx + dx, cy + dy
                if 0 <= xx < size and 0 <= yy < size:
                    put(xx, yy, max(abs(dx), abs(dy)) not in (2, 4))
    pos = _alignment_positions(version, size)
    last = len(pos) - 1
    for i, ax in enumerate(pos):
        for j, ay in enumerate(pos):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    ys, xs, _ = _format_coordinates(size)  # Formatbereich reservieren, Bits kommen spaeter
    is_function[ys, xs] = True
    put(8, size - 8, True)  # immer dunkel
    if version >= 7:
        bits = _version_bits(version)
        for i in range(18):
            bit = (bits >> i) & 1 != 0
            a, b = size - 11 + i % 3, i // 3
            put(a, b, bit)
            put(b, a, bit)
    return modules, is_function


def _zigzag_positions(size: int, is_function: np.ndarray) -> np.ndarray:
    order: list[int] = []
    for right in range(size - 1, 0, -2):
        if right <= 6:
            right -= 1
        upward = (right + 1) & 2 == 0
        for vert in range(size):
            y = size - 1 - vert if upward else vert
            for j in range(2):
                x = right - j
                if not is_function[y, x]:
                    order.append(y * size + x)
    return np.array(order, dtype=np.int64)


@cache
def version_layout(version: int) -> VersionLayout:
    check_version(version)
    size = version * 4 + 17
    base, is_function = _draw_function_patterns(version, size)
    positions = _zigzag_positions(size, is_function)
    assert positions.size >= num_raw_data_modules(version) // 8 * 8
    for arr in (base, is_function, positions):
        arr.setflags(write=False)
    return VersionLayout(version, size, is_function, base, positions)


_MASK_FUNCS = (
    lambda x, y: (x + y) % 2,
    lambda x, y: y % 2,
    lambda x, y: x % 3,
    lambda x, y: (x + y) % 3,
    lambda x, y: (x // 3 + y // 2) % 2,
    lambda x, y: x * y % 2 + x * y % 3,
    lambda x, y: (x * y % 2 + x * y % 3) % 2,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2,
)


@cache
def mask_pattern(size: int, mask: int) -> np.ndarray:
    """True dort, wo die Maske ein Modul invertiert (ohne Ruecksicht auf Funktionsmodule)."""
    y, x = np.indices((size, size))
    pattern: np.ndarray = np.asarray(_MASK_FUNCS[mask](x, y) == 0)
    pattern.setflags(write=False)
    return pattern


@lru_cache(maxsize=256)
def masked_template(version: int, ecl_formatbits: int, mask: int) -> np.ndarray:
    """Fertiges Bild ohne Daten: Funktionsmuster, Formatbits und Maske auf allen Datenzellen.

    Weil Datenbits per XOR mit der Maske verknuepft werden, reicht anschliessend
    `template.flat[positions] ^= bits` fuer einen vollstaendigen QR-Code.
    """
    layout = version_layout(version)
    template = layout.base.copy()
    ys, xs, bitidx = _format_coordinates(layout.size)
    template[ys, xs] = ((format_bits(ecl_formatbits, mask) >> bitidx) & 1).astype(bool)
    template ^= mask_pattern(layout.size, mask) & ~layout.is_function
    template.setflags(write=False)
    return template
