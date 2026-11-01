"""Rechenkerne: Reed-Solomon mit Interleaving und Masken-Strafpunkte.

Thesis-Aenderungen 8, 9 und 18 haben nur den RS-Rest in Numba gerechnet und pro Block
zwischen Liste und Array konvertiert. Hier laeuft Fehlerkorrektur *und* Interleaving
fuer alle Bloecke in einem einzigen Kernel-Aufruf.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from ._jit import HAVE_NUMBA, jit

U8 = npt.NDArray[np.uint8]
I64 = npt.NDArray[np.int64]

PENALTY_N1 = 3
PENALTY_N2 = 3
PENALTY_N3 = 40
PENALTY_N4 = 10


@jit
def _ecc_interleave_loop(
    data: U8, numblocks: int, blockecclen: int, rawcodewords: int, divisor: U8, mul: U8
) -> U8:
    numshort = numblocks - rawcodewords % numblocks
    shortdata = rawcodewords // numblocks - blockecclen
    numlong = numblocks - numshort
    ecc_base = shortdata * numblocks + numlong
    out = np.empty(rawcodewords, dtype=np.uint8)
    ecc = np.zeros(blockecclen, dtype=np.uint8)
    k = 0
    for i in range(numblocks):
        datlen = shortdata if i < numshort else shortdata + 1
        ecc[:] = 0
        for b in range(datlen):
            value = data[k + b]
            factor = value ^ ecc[0]
            for j in range(blockecclen - 1):
                ecc[j] = ecc[j + 1] ^ mul[divisor[j], factor]
            ecc[blockecclen - 1] = mul[divisor[blockecclen - 1], factor]
            if b < shortdata:
                out[b * numblocks + i] = value
            else:
                out[shortdata * numblocks + (i - numshort)] = value
        for j in range(blockecclen):
            out[ecc_base + j * numblocks + i] = ecc[j]
        k += datlen
    return out


def _ecc_interleave_numpy(
    data: U8, numblocks: int, blockecclen: int, rawcodewords: int, divisor: U8, mul: U8
) -> U8:
    """Vektorisierte Variante ohne Numba: alle Bloecke gleichzeitig, Schleife nur ueber Byte-Positionen."""
    numshort = numblocks - rawcodewords % numblocks
    shortdata = rawcodewords // numblocks - blockecclen
    numlong = numblocks - numshort
    width = shortdata + (1 if numlong else 0)
    blocks = np.zeros((numblocks, width), dtype=np.uint8)
    blocks[:numshort, :shortdata] = data[: numshort * shortdata].reshape(numshort, shortdata)
    if numlong:
        blocks[numshort:, :] = data[numshort * shortdata :].reshape(numlong, shortdata + 1)
    ecc = np.zeros((numblocks, blockecclen), dtype=np.uint8)
    div = divisor.astype(np.intp)
    for b in range(width):
        rows = slice(None) if b < shortdata else slice(numshort, None)
        factor = blocks[rows, b] ^ ecc[rows, 0]
        shifted = np.zeros_like(ecc[rows])
        shifted[:, :-1] = ecc[rows, 1:]
        ecc[rows] = shifted ^ mul[div[None, :], factor[:, None]]
    out = np.empty(rawcodewords, dtype=np.uint8)
    out[: shortdata * numblocks] = blocks[:, :shortdata].T.reshape(-1)
    if numlong:
        out[shortdata * numblocks : shortdata * numblocks + numlong] = blocks[numshort:, shortdata]
    out[shortdata * numblocks + numlong :] = ecc.T.reshape(-1)
    return out


ecc_and_interleave: Callable[[U8, int, int, int, U8, U8], U8] = (
    _ecc_interleave_loop if HAVE_NUMBA else _ecc_interleave_numpy
)


@jit
def _add_history(run: int, hist: I64, size: int) -> None:
    if hist[0] == 0:
        run += size  # heller Rand vor dem ersten Lauf
    for i in range(6, 0, -1):
        hist[i] = hist[i - 1]
    hist[0] = run


@jit
def _count_patterns(hist: I64) -> int:
    n = hist[1]
    core = n > 0 and hist[2] == n and hist[4] == n and hist[5] == n and hist[3] == n * 3
    count = 0
    if core and hist[0] >= n * 4 and hist[6] >= n:
        count += 1
    if core and hist[6] >= n * 4 and hist[0] >= n:
        count += 1
    return count


@jit
def _line_penalty(modules: npt.NDArray[np.bool_]) -> int:
    """Regeln N1 (Laeufe gleicher Farbe) und N3 (Finder-aehnliche Muster) fuer Zeilen und Spalten."""
    size = modules.shape[0]
    result = 0
    hist = np.zeros(7, dtype=np.int64)
    for axis in range(2):
        for a in range(size):
            runcolor = False
            run = 0
            hist[:] = 0
            for b in range(size):
                color = modules[a, b] if axis == 0 else modules[b, a]
                if color == runcolor:
                    run += 1
                    if run == 5:
                        result += PENALTY_N1
                    elif run > 5:
                        result += 1
                else:
                    _add_history(run, hist, size)
                    if not runcolor:
                        result += _count_patterns(hist) * PENALTY_N3
                    runcolor = color
                    run = 1
            if runcolor:
                _add_history(run, hist, size)
                run = 0
            _add_history(run + size, hist, size)
            result += _count_patterns(hist) * PENALTY_N3
    return result


def penalty_score(modules: np.ndarray) -> int:
    """Strafpunkte nach ISO/IEC 18004 wie bei nayuki; kleiner ist besser."""
    result = int(_line_penalty(modules))
    m = modules
    same = (m[:-1, :-1] == m[:-1, 1:]) & (m[:-1, :-1] == m[1:, :-1]) & (m[:-1, :-1] == m[1:, 1:])
    result += PENALTY_N2 * int(np.count_nonzero(same))
    dark = int(np.count_nonzero(m))
    total = m.size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    return result + k * PENALTY_N4
