"""QR-Code-Symbol: Kodierung, Fehlerkorrektur, Platzierung und Maskierung.

API-kompatibel zu nayuki/qrcodegen (Python) und zum Thesis-Stand qrcodegenmod,
mit Modulen als NumPy-Array statt verschachtelter Listen.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

import numpy as np

from . import _tables
from ._kernels import ecc_and_interleave, penalty_score
from ._layout import masked_template, version_layout
from .segment import QrSegment, int_to_bits

_PAD_BYTES = np.array([0xEC, 0x11], dtype=np.uint8)


class EccLevel(Enum):
    """Fehlerkorrekturstufe: (ordinal, formatbits)."""

    LOW = (0, 1)  # ca.  7 % fehlerhafte Codewoerter tolerierbar
    MEDIUM = (1, 0)  # ca. 15 %
    QUARTILE = (2, 3)  # ca. 25 %
    HIGH = (3, 2)  # ca. 30 %

    @property
    def ordinal(self) -> int:
        return self.value[0]

    @property
    def formatbits(self) -> int:
        return self.value[1]


Ecc = EccLevel  # oeffentlicher Name, kompatibel zu QrCode.Ecc.LOW


class DataTooLongError(ValueError):
    """Die Daten passen in keine Version im erlaubten Bereich."""


class QrCode:
    """Unveraenderliches QR-Code-Symbol (Model 2, Version 1-40, alle ECC-Stufen)."""

    Ecc = EccLevel
    MIN_VERSION = _tables.MIN_VERSION
    MAX_VERSION = _tables.MAX_VERSION
    __slots__ = ("_errcorlvl", "_mask", "_modules", "_size", "_version")

    # ---- Fabrikfunktionen ----

    @staticmethod
    def encode_text(text: str, ecl: EccLevel, **kwargs: int | bool) -> QrCode:
        """Text als QR-Code; kwargs gehen an encode_segments (minversion, maxversion, mask, boostecl)."""
        return QrCode.encode_segments(QrSegment.make_segments(text), ecl, **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def encode_binary(data: bytes | bytearray | Sequence[int], ecl: EccLevel, **kwargs: int | bool) -> QrCode:
        if not isinstance(data, (bytes, bytearray, list, tuple, np.ndarray)):
            raise TypeError("Byte string/list expected")
        return QrCode.encode_segments([QrSegment.make_bytes(data)], ecl, **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def encode_segments(
        segs: Sequence[QrSegment],
        ecl: EccLevel,
        minversion: int = 1,
        maxversion: int = 40,
        mask: int = -1,
        boostecl: bool = True,
    ) -> QrCode:
        """Kleinste passende Version im Bereich waehlen und den QR-Code bauen."""
        if not (QrCode.MIN_VERSION <= minversion <= maxversion <= QrCode.MAX_VERSION) or not (
            -1 <= mask <= 7
        ):
            raise ValueError("Invalid value")

        for version in range(minversion, maxversion + 1):
            capacity = _tables.num_data_codewords(version, ecl.ordinal) * 8
            used = QrSegment.get_total_bits(segs, version)
            if used is not None and used <= capacity:
                break
            if version >= maxversion:
                msg = "Segment too long"
                if used is not None:
                    msg = f"Data length = {used} bits, Max capacity = {capacity} bits"
                raise DataTooLongError(msg)
        assert used is not None

        for newecl in (EccLevel.MEDIUM, EccLevel.QUARTILE, EccLevel.HIGH):
            if boostecl and used <= _tables.num_data_codewords(version, newecl.ordinal) * 8:
                ecl = newecl

        parts: list[np.ndarray] = []
        for seg in segs:
            mode = seg.get_mode()
            parts.append(int_to_bits(mode.get_mode_bits(), 4))
            parts.append(int_to_bits(seg.get_num_chars(), mode.num_char_count_bits(version)))
            parts.append(seg.bits)
        capacity = _tables.num_data_codewords(version, ecl.ordinal) * 8
        terminator = min(4, capacity - used)
        parts.append(np.zeros(terminator + (-(used + terminator) % 8), dtype=np.uint8))
        packed = np.packbits(np.concatenate(parts))
        datacodewords = np.concatenate((packed, np.resize(_PAD_BYTES, capacity // 8 - packed.size)))
        return QrCode(version, ecl, datacodewords, mask)

    # ---- Konstruktor ----

    def __init__(
        self, version: int, errcorlvl: EccLevel, datacodewords: bytes | Sequence[int] | np.ndarray, mask: int
    ) -> None:
        if not (QrCode.MIN_VERSION <= version <= QrCode.MAX_VERSION):
            raise ValueError("Version value out of range")
        if not (-1 <= mask <= 7):
            raise ValueError("Mask value out of range")
        if not isinstance(errcorlvl, EccLevel):
            raise TypeError("QrCode.Ecc expected")
        data = (
            np.frombuffer(bytes(datacodewords), dtype=np.uint8)
            if isinstance(datacodewords, (bytes, bytearray))
            else np.asarray(datacodewords, dtype=np.uint8)
        )
        if data.size != _tables.num_data_codewords(version, errcorlvl.ordinal):
            raise ValueError("Wrong number of data codewords")

        self._version = version
        self._size = version * 4 + 17
        self._errcorlvl = errcorlvl

        bits = np.unpackbits(self._add_ecc_and_interleave(data))
        positions = version_layout(version).data_positions[: bits.size]
        if mask == -1:
            mask = self._choose_mask(bits, positions)
        modules = masked_template(version, errcorlvl.formatbits, mask).copy()
        modules.reshape(-1)[positions] ^= bits.view(bool)
        modules.setflags(write=False)
        self._modules = modules
        self._mask = mask

    def _add_ecc_and_interleave(self, data: np.ndarray) -> np.ndarray:
        ordinal = self._errcorlvl.ordinal
        blockecclen = _tables.ECC_CODEWORDS_PER_BLOCK[ordinal][self._version]
        return ecc_and_interleave(
            data,
            _tables.NUM_ERROR_CORRECTION_BLOCKS[ordinal][self._version],
            blockecclen,
            _tables.num_raw_data_modules(self._version) // 8,
            _tables.reed_solomon_divisor(blockecclen),
            _tables.MULTIPLY_TABLE,
        )

    def _choose_mask(self, bits: np.ndarray, positions: np.ndarray) -> int:
        best_mask, best_penalty = 0, 1 << 32
        for candidate in range(8):
            modules = masked_template(self._version, self._errcorlvl.formatbits, candidate).copy()
            modules.reshape(-1)[positions] ^= bits.view(bool)
            penalty = penalty_score(modules)
            if penalty < best_penalty:
                best_mask, best_penalty = candidate, penalty
        return best_mask

    # ---- Zugriff ----

    def get_version(self) -> int:
        return self._version

    def get_size(self) -> int:
        return self._size

    def get_error_correction_level(self) -> EccLevel:
        return self._errcorlvl

    def get_mask(self) -> int:
        return self._mask

    @property
    def modules(self) -> np.ndarray:
        """Module als schreibgeschuetztes bool-Array (size, size), True = dunkel, Index [y, x]."""
        return self._modules

    def get_module(self, x: int, y: int) -> bool:
        return bool(0 <= x < self._size and 0 <= y < self._size and self._modules[y, x])

    def get_module_as_numpy(self, border: int) -> np.ndarray:
        """Module mit hellem Rand der Breite `border` (Thesis-Aenderung 2)."""
        if border < 0:
            raise ValueError("Border must be non-negative")
        return np.pad(self._modules, border, constant_values=False)

    def to_image(self, scale: int = 2, border: int = 2) -> np.ndarray:
        """Graustufenbild uint8 (dunkel = 0, hell = 255), jedes Modul als scale x scale Pixel."""
        if scale < 1:
            raise ValueError("Scale must be positive")
        small = (~self.get_module_as_numpy(border)).view(np.uint8) * np.uint8(255)
        n = small.shape[0]
        # Ein einziger Kopiervorgang statt zweimal np.repeat (Thesis: Kronecker, dann repeat)
        return np.broadcast_to(small[:, None, :, None], (n, scale, n, scale)).reshape(n * scale, n * scale)

    def to_svg_str(self, border: int) -> str:
        if border < 0:
            raise ValueError("Border must be non-negative")
        ys, xs = np.nonzero(self._modules)
        path = " ".join(
            f"M{x + border},{y + border}h1v1h-1z" for y, x in zip(ys.tolist(), xs.tolist(), strict=True)
        )
        dim = self._size + border * 2
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
            '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'viewBox="0 0 {dim} {dim}" stroke="none">\n'
            '\t<rect width="100%" height="100%" fill="#FFFFFF"/>\n'
            f'\t<path d="{path}" fill="#000000"/>\n'
            "</svg>\n"
        )
