"""Reed-Solomon-Dekodierung fuer QR-Codes: GF(2^8/0x11D), Generator 2, erste Nullstelle alpha^0.

Berlekamp-Massey findet das Fehlerortungspolynom, die Chien-Suche die Positionen,
Forney die Fehlerwerte. Korrigiert bis zu floor(nsym / 2) fehlerhafte Bytes pro Block.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from ._jit import jit
from ._tables import MULTIPLY_TABLE


def _build_exp_log() -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    exp = np.zeros(512, dtype=np.int64)
    log = np.zeros(256, dtype=np.int64)
    value = 1
    for i in range(255):
        exp[i] = value
        log[value] = i
        value = int(MULTIPLY_TABLE[value, 2])
    exp[255:510] = exp[:255]
    return exp, log


EXP, LOG = _build_exp_log()


class ReedSolomonError(ValueError):
    """Block hat mehr Fehler, als die Fehlerkorrektur beheben kann."""


@jit
def _correct_block(
    block: npt.NDArray[np.uint8], nsym: int, exp: npt.NDArray[np.int64], log: npt.NDArray[np.int64]
) -> int:
    """Korrigiert block (Daten + ECC) in place; Rueckgabe Anzahl Korrekturen, -1 = nicht korrigierbar."""
    n = block.shape[0]
    synd = np.zeros(nsym, dtype=np.int64)
    any_error = False
    for j in range(nsym):  # Syndrome S_j = r(alpha^j), Horner-Schema
        acc = 0
        for i in range(n):
            acc = block[i] ^ (exp[log[acc] + j] if acc != 0 else 0)
        synd[j] = acc
        if acc != 0:
            any_error = True
    if not any_error:
        return 0

    # Berlekamp-Massey: Lambda(x) = 1 + L1 x + ...
    lam = np.zeros(nsym + 1, dtype=np.int64)
    prev = np.zeros(nsym + 1, dtype=np.int64)
    lam[0] = 1
    prev[0] = 1
    length = 0
    shift = 1
    prev_disc = 1
    for k in range(nsym):
        disc = synd[k]
        for i in range(1, length + 1):
            if lam[i] != 0 and synd[k - i] != 0:
                disc ^= exp[log[lam[i]] + log[synd[k - i]]]
        if disc == 0:
            shift += 1
            continue
        coef_log = (log[disc] - log[prev_disc]) % 255
        if 2 * length <= k:
            saved = lam.copy()
            for i in range(nsym + 1 - shift):
                if prev[i] != 0:
                    lam[i + shift] ^= exp[log[prev[i]] + coef_log]
            length = k + 1 - length
            prev = saved
            prev_disc = disc
            shift = 1
        else:
            for i in range(nsym + 1 - shift):
                if prev[i] != 0:
                    lam[i + shift] ^= exp[log[prev[i]] + coef_log]
            shift += 1
    if 2 * length > nsym:
        return -1

    # Chien-Suche: Fehler an Index i (Potenz p = n-1-i), wenn Lambda(alpha^-p) == 0
    positions = np.zeros(length, dtype=np.int64)
    found = 0
    for i in range(n):
        p = n - 1 - i
        inv = (255 - p) % 255
        acc = 0
        for d in range(length + 1):
            if lam[d] != 0:
                acc ^= exp[(log[lam[d]] + inv * d) % 255]
        if acc == 0:
            if found == length:
                return -1
            positions[found] = i
            found += 1
    if found != length:
        return -1

    # Forney (fcr = 0): e = X * Omega(X^-1) / Lambda'(X^-1), Omega = S(x) Lambda(x) mod x^nsym
    omega = np.zeros(nsym, dtype=np.int64)
    for i in range(nsym):
        acc = 0
        for d in range(min(i, length) + 1):
            if lam[d] != 0 and synd[i - d] != 0:
                acc ^= exp[log[lam[d]] + log[synd[i - d]]]
        omega[i] = acc
    for e in range(length):
        i = positions[e]
        p = n - 1 - i
        xinv = (255 - p) % 255  # log von X^-1
        num = 0
        for d in range(nsym):
            if omega[d] != 0:
                num ^= exp[(log[omega[d]] + xinv * d) % 255]
        den = 0
        for d in range(1, length + 1, 2):  # formale Ableitung: nur ungerade Potenzen
            if lam[d] != 0:
                den ^= exp[(log[lam[d]] + xinv * (d - 1)) % 255]
        if den == 0:
            return -1
        if num != 0:
            block[i] ^= exp[(p + log[num] - log[den]) % 255]
    return length


def correct_block(block: np.ndarray, nsym: int) -> int:
    """Korrigiert einen Block (Daten + nsym ECC-Bytes) in place und gibt die Zahl der Korrekturen zurueck."""
    if block.dtype != np.uint8:
        raise TypeError("uint8 block expected")
    fixed = int(_correct_block(block, nsym, EXP, LOG))
    if fixed < 0:
        raise ReedSolomonError(f"Block nicht korrigierbar (mehr als {nsym // 2} Fehler)")
    return fixed
