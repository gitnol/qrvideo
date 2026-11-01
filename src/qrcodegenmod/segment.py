"""Datensegmente (Numeric, Alphanumeric, Byte, ECI) mit Bitfolgen als NumPy-Arrays.

Thesis-Aenderungen 6, 14, 15 und 17 ersetzten den listenbasierten _BitBuffer schrittweise
durch NumPy. Hier sind Bitfolgen durchgehend uint8-Arrays aus 0 und 1.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum

import numpy as np


def int_to_bits(value: int, width: int) -> np.ndarray:
    """Die `width` niederwertigen Bits von `value`, hoechstwertiges zuerst."""
    if width < 0 or value >> width != 0:
        raise ValueError("Value out of range")
    if width == 0:
        return np.zeros(0, dtype=np.uint8)
    return ((value >> np.arange(width - 1, -1, -1)) & 1).astype(np.uint8)


class SegmentMode(Enum):
    """Segment-Modus: Modus-Kennbits und Breite des Zeichenzaehlers fuer drei Versionsbereiche."""

    NUMERIC = (0x1, (10, 12, 14))
    ALPHANUMERIC = (0x2, (9, 11, 13))
    BYTE = (0x4, (8, 16, 16))
    KANJI = (0x8, (8, 10, 12))
    ECI = (0x7, (0, 0, 0))

    def get_mode_bits(self) -> int:
        return self.value[0]

    def num_char_count_bits(self, ver: int) -> int:
        return self.value[1][(ver + 7) // 17]


Mode = SegmentMode  # oeffentlicher Name, kompatibel zu QrSegment.Mode.BYTE

_NUMERIC_REGEX = re.compile(r"[0-9]*")
_ALPHANUMERIC_REGEX = re.compile(r"[A-Z0-9 $%*+./:-]*")
_ALPHANUMERIC_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
_ALPHANUMERIC_LUT = np.full(128, 255, dtype=np.uint8)
_ALPHANUMERIC_LUT[np.frombuffer(_ALPHANUMERIC_CHARSET.encode("ascii"), dtype=np.uint8)] = np.arange(45)


def _pack_groups(values: np.ndarray, width: int) -> np.ndarray:
    """Jeden Wert mit fester Bitbreite hintereinander schreiben (vektorisiert)."""
    shifts = np.arange(width - 1, -1, -1)
    return ((values.astype(np.int64)[:, None] >> shifts) & 1).astype(np.uint8).reshape(-1)


class QrSegment:
    """Ein Segment aus Zeichen-, Binaer- oder Steuerdaten. Unveraenderlich."""

    Mode = SegmentMode
    __slots__ = ("_bitdata", "_mode", "_numchars")

    def __init__(self, mode: SegmentMode, numch: int, bitdata: Sequence[int] | np.ndarray) -> None:
        if numch < 0:
            raise ValueError("Character count must be non-negative")
        bits = np.array(bitdata, dtype=np.uint8)  # defensive Kopie
        if bits.size and int(np.max(bits)) > 1:
            raise ValueError("Bit data must contain only 0 and 1")
        bits.setflags(write=False)
        self._mode = mode
        self._numchars = numch
        self._bitdata = bits

    # ---- Fabrikfunktionen ----

    @staticmethod
    def make_bytes(data: bytes | bytearray | memoryview | Sequence[int]) -> QrSegment:
        if isinstance(data, str):
            raise TypeError("Byte string/list expected")
        if isinstance(data, (bytes, bytearray, memoryview)):
            raw = np.frombuffer(data, dtype=np.uint8)
        else:
            values = np.asarray(data, dtype=np.int64)
            if values.size and (int(np.min(values)) < 0 or int(np.max(values)) > 255):
                raise ValueError("Byte out of range")
            raw = values.astype(np.uint8)
        return QrSegment(Mode.BYTE, raw.size, np.unpackbits(raw))

    @staticmethod
    def make_numeric(digits: str) -> QrSegment:
        if not QrSegment.is_numeric(digits):
            raise ValueError("String contains non-numeric characters")
        full = len(digits) // 3 * 3
        parts = []
        if full:
            groups = np.array([int(digits[i : i + 3]) for i in range(0, full, 3)], dtype=np.int64)
            parts.append(_pack_groups(groups, 10))
        rest = len(digits) - full
        if rest:
            parts.append(int_to_bits(int(digits[full:]), rest * 3 + 1))
        bits = np.concatenate(parts) if parts else np.zeros(0, dtype=np.uint8)
        return QrSegment(Mode.NUMERIC, len(digits), bits)

    @staticmethod
    def make_alphanumeric(text: str) -> QrSegment:
        if not QrSegment.is_alphanumeric(text):
            raise ValueError("String contains unencodable characters in alphanumeric mode")
        codes = _ALPHANUMERIC_LUT[np.frombuffer(text.encode("ascii"), dtype=np.uint8)].astype(np.int64)
        pairs = len(codes) // 2
        parts = [_pack_groups(codes[: pairs * 2 : 2] * 45 + codes[1 : pairs * 2 : 2], 11)]
        if len(codes) % 2:
            parts.append(int_to_bits(int(codes[-1]), 6))
        return QrSegment(Mode.ALPHANUMERIC, len(text), np.concatenate(parts))

    @staticmethod
    def make_segments(text: str) -> list[QrSegment]:
        if not isinstance(text, str):
            raise TypeError("Text string expected")
        if text == "":
            return []
        if QrSegment.is_numeric(text):
            return [QrSegment.make_numeric(text)]
        if QrSegment.is_alphanumeric(text):
            return [QrSegment.make_alphanumeric(text)]
        return [QrSegment.make_bytes(text.encode("utf-8"))]

    @staticmethod
    def make_eci(assignval: int) -> QrSegment:
        if assignval < 0:
            raise ValueError("ECI assignment value out of range")
        if assignval < (1 << 7):
            bits = int_to_bits(assignval, 8)
        elif assignval < (1 << 14):
            bits = np.concatenate((int_to_bits(0b10, 2), int_to_bits(assignval, 14)))
        elif assignval < 1_000_000:
            bits = np.concatenate((int_to_bits(0b110, 3), int_to_bits(assignval, 21)))
        else:
            raise ValueError("ECI assignment value out of range")
        return QrSegment(Mode.ECI, 0, bits)

    @staticmethod
    def is_numeric(text: str) -> bool:
        return _NUMERIC_REGEX.fullmatch(text) is not None

    @staticmethod
    def is_alphanumeric(text: str) -> bool:
        return _ALPHANUMERIC_REGEX.fullmatch(text) is not None

    # ---- Zugriff ----

    def get_mode(self) -> SegmentMode:
        return self._mode

    def get_num_chars(self) -> int:
        return self._numchars

    def get_data(self) -> list[int]:
        return [int(b) for b in self._bitdata]

    @property
    def bits(self) -> np.ndarray:
        """Bitfolge als schreibgeschuetztes uint8-Array."""
        return self._bitdata

    @staticmethod
    def get_total_bits(segs: Sequence[QrSegment], version: int) -> int | None:
        """Benoetigte Bits fuer die Segmente in dieser Version oder None, wenn ein Zaehler ueberlaeuft."""
        result = 0
        for seg in segs:
            ccbits = seg.get_mode().num_char_count_bits(version)
            if seg.get_num_chars() >= (1 << ccbits):
                return None
            result += 4 + ccbits + seg._bitdata.size
        return result
