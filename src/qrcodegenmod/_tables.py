"""Konstante Tabellen des QR-Standards und Galois-Feld-Arithmetik GF(2^8/0x11D).

Thesis-Aenderungen 4 und 5 (Lookup-Tabellen fuer Multiplikation und Generatorpolynome)
werden hier beim Import berechnet statt aus .npy-Dateien geladen.
"""

from __future__ import annotations

from functools import cache

import numpy as np

MIN_VERSION = 1
MAX_VERSION = 40

# Index 0 ist Fuellwert; Zeilen: LOW, MEDIUM, QUARTILE, HIGH
ECC_CODEWORDS_PER_BLOCK: tuple[tuple[int, ...], ...] = (
    (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),  # noqa: E501
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),  # noqa: E501
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),  # noqa: E501
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),  # noqa: E501
)

NUM_ERROR_CORRECTION_BLOCKS: tuple[tuple[int, ...], ...] = (
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),  # noqa: E501
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),  # noqa: E501
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),  # noqa: E501
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),  # noqa: E501
)


def check_version(ver: int) -> None:
    if not (MIN_VERSION <= ver <= MAX_VERSION):
        raise ValueError("Version number out of range")


def num_raw_data_modules(ver: int) -> int:
    """Anzahl Datenbits einer Version nach Abzug aller Funktionsmodule (inkl. Restbits)."""
    check_version(ver)
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        numalign = ver // 7 + 2
        result -= (25 * numalign - 10) * numalign - 55
        if ver >= 7:
            result -= 36
    return result


def num_data_codewords(ver: int, ecl_ordinal: int) -> int:
    """Anzahl 8-Bit-Datencodewoerter (ohne Fehlerkorrektur) fuer Version und ECC-Stufe."""
    return (
        num_raw_data_modules(ver) // 8
        - ECC_CODEWORDS_PER_BLOCK[ecl_ordinal][ver] * NUM_ERROR_CORRECTION_BLOCKS[ecl_ordinal][ver]
    )


def _gf_multiply(x: int, y: int) -> int:
    """Produkt zweier Feldelemente modulo GF(2^8/0x11D) (Russian peasant multiplication)."""
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _build_multiply_table() -> np.ndarray:
    """256x256-Tabelle aller Produkte (Thesis-Aenderung 4), per Log/Antilog in Millisekunden."""
    exp = np.zeros(512, dtype=np.int64)
    log = np.zeros(256, dtype=np.int64)
    value = 1
    for i in range(255):
        exp[i] = value
        log[value] = i
        value = _gf_multiply(value, 2)
    exp[255:510] = exp[0:255]
    table: np.ndarray = exp[log[:, None] + log[None, :]].astype(np.uint8)
    table[0, :] = 0
    table[:, 0] = 0
    table.setflags(write=False)
    return table


MULTIPLY_TABLE: np.ndarray = _build_multiply_table()


@cache
def reed_solomon_divisor(degree: int) -> np.ndarray:
    """Generatorpolynom vom Grad `degree` ohne fuehrende 1 (Thesis-Aenderung 5)."""
    if not (1 <= degree <= 255):
        raise ValueError("Degree out of range")
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = int(MULTIPLY_TABLE[result[j], root])
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = int(MULTIPLY_TABLE[root, 2])
    divisor = np.array(result, dtype=np.uint8)
    divisor.setflags(write=False)
    return divisor
