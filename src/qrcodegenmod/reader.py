"""QR-Codes aus einer bekannten Modul-Matrix lesen (ohne Bilderkennung).

Gedacht fuer Faelle, in denen die Geometrie feststeht, etwa die Video-Frames der Thesis:
Module abtasten, dann hier Formatbits, Maske, Zickzack, De-Interleaving, Reed-Solomon-
Korrektur und Segmente auswerten.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np

from . import _tables
from ._layout import _format_coordinates, format_bits, mask_pattern, version_layout
from ._rs_decode import ReedSolomonError, correct_block
from .qrcode import Ecc
from .segment import Mode

_ALPHANUMERIC_CHARSET = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"


class QrDecodeError(ValueError):
    """Die Modul-Matrix laesst sich nicht als QR-Code lesen."""


@dataclass(frozen=True)
class DecodedQr:
    data: bytes
    version: int
    ecl: Ecc
    mask: int
    corrected_bytes: int  # Summe der von Reed-Solomon korrigierten Bytes


@cache
def _format_table() -> np.ndarray:
    """Zeilen (formatbits, mask, 15-Bit-Codewort) fuer alle 32 Kombinationen."""
    return np.array([(fb, m, format_bits(fb, m)) for fb in range(4) for m in range(8)], dtype=np.int64)


def _read_format(modules: np.ndarray) -> tuple[Ecc, int]:
    ys, xs, bitidx = _format_coordinates(modules.shape[0])
    values = modules[ys, xs].astype(np.int64) << bitidx
    copies = (int(values[:15].sum()), int(values[15:].sum()))
    table = _format_table()
    best, best_dist = None, 99
    for fb, mask, code in table.tolist():
        dist = min(bin(code ^ c).count("1") for c in copies)
        if dist < best_dist:
            best, best_dist = (fb, mask), dist
    if best is None or best_dist > 3:
        raise QrDecodeError("Formatbits nicht lesbar")
    ecl = next(e for e in Ecc if e.formatbits == best[0])
    return ecl, best[1]


@cache
def _block_indices(version: int, ordinal: int) -> tuple[tuple[np.ndarray, ...], int]:
    """Pro Block die Indizes seiner Bytes (Daten, dann ECC) im verschraenkten Codewortstrom."""
    numblocks = _tables.NUM_ERROR_CORRECTION_BLOCKS[ordinal][version]
    eccl = _tables.ECC_CODEWORDS_PER_BLOCK[ordinal][version]
    raw = _tables.num_raw_data_modules(version) // 8
    numshort = numblocks - raw % numblocks
    shortdata = raw // numblocks - eccl
    ecc_base = shortdata * numblocks + (numblocks - numshort)
    blocks = []
    for i in range(numblocks):
        data_idx = [b * numblocks + i for b in range(shortdata)]
        if i >= numshort:
            data_idx.append(shortdata * numblocks + (i - numshort))
        ecc_idx = [ecc_base + j * numblocks + i for j in range(eccl)]
        blocks.append(np.array(data_idx + ecc_idx, dtype=np.int64))
    return tuple(blocks), eccl


class _BitReader:
    def __init__(self, data: bytes) -> None:
        self._bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
        self._pos = 0

    def remaining(self) -> int:
        return self._bits.size - self._pos

    def read(self, n: int) -> int:
        if n > self.remaining():
            raise QrDecodeError("Bitstrom endet vorzeitig")
        chunk = self._bits[self._pos : self._pos + n].astype(np.int64)
        self._pos += n
        return int(chunk @ (1 << np.arange(n - 1, -1, -1, dtype=np.int64)))

    def read_bytes(self, count: int) -> bytes:
        if count * 8 > self.remaining():
            raise QrDecodeError("Bitstrom endet vorzeitig")
        out = np.packbits(self._bits[self._pos : self._pos + count * 8]).tobytes()
        self._pos += count * 8
        return out


def _parse_segments(data: bytes, version: int) -> bytes:
    reader = _BitReader(data)
    out = bytearray()
    while reader.remaining() >= 4:
        mode_bits = reader.read(4)
        if mode_bits == 0:
            break
        mode = next((m for m in Mode if m.get_mode_bits() == mode_bits), None)
        if mode is None or mode is Mode.KANJI:
            raise QrDecodeError(f"Segment-Modus {mode_bits:#x} wird nicht unterstuetzt")
        if mode is Mode.ECI:
            first = reader.read(8)
            if first & 0x80:
                reader.read(8 if first & 0x40 == 0 else 16)
            continue
        count = reader.read(mode.num_char_count_bits(version))
        if mode is Mode.BYTE:
            out += reader.read_bytes(count)
        elif mode is Mode.NUMERIC:
            for done in range(0, count, 3):
                n = min(3, count - done)
                value = reader.read(n * 3 + 1)
                if value >= 10**n:
                    raise QrDecodeError(f"Numeric-Wert {value} hat mehr als {n} Ziffern")
                out += str(value).zfill(n).encode("ascii")
        else:  # ALPHANUMERIC
            for _ in range(count // 2):
                value = reader.read(11)
                if value >= 45 * 45:
                    raise QrDecodeError(f"Alphanumeric-Wert {value} ausserhalb des Zeichensatzes")
                out += bytes((_ALPHANUMERIC_CHARSET[value // 45], _ALPHANUMERIC_CHARSET[value % 45]))
            if count % 2:
                value = reader.read(6)
                if value >= 45:
                    raise QrDecodeError(f"Alphanumeric-Wert {value} ausserhalb des Zeichensatzes")
                out.append(_ALPHANUMERIC_CHARSET[value])
    return bytes(out)


def decode_modules(modules: np.ndarray) -> DecodedQr:
    """Liest eine quadratische bool-Matrix (True = dunkel, ohne Rand) als QR-Code."""
    size = modules.shape[0]
    if modules.ndim != 2 or modules.shape[1] != size or (size - 17) % 4 or not 21 <= size <= 177:
        raise QrDecodeError(f"Keine gueltige QR-Matrix: {modules.shape}")
    version = (size - 17) // 4
    modules = np.asarray(modules, dtype=bool)
    ecl, mask = _read_format(modules)

    raw = _tables.num_raw_data_modules(version) // 8
    positions = version_layout(version).data_positions[: raw * 8]
    bits = modules.reshape(-1)[positions] ^ mask_pattern(size, mask).reshape(-1)[positions]
    codewords = np.packbits(bits)

    blocks, eccl = _block_indices(version, ecl.ordinal)
    data_parts = []
    corrected = 0
    for idx in blocks:
        block = codewords[idx].copy()
        try:
            corrected += correct_block(block, eccl)
        except ReedSolomonError as exc:
            raise QrDecodeError(str(exc)) from exc
        data_parts.append(block[: idx.size - eccl])
    payload = _parse_segments(np.concatenate(data_parts).tobytes(), version)
    return DecodedQr(payload, version, ecl, mask, corrected)
