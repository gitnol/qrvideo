"""Aeusserer Erasure-Code ueber Daten-QR (ADR-003): systematischer Cauchy-Reed-Solomon ueber GF(256).

Eine Gruppe besteht aus k Datensymbolen d_i und m Paritaetssymbolen p_j gleicher Laenge; byteweise gilt
p_j = Summe_i d_i / (y_j + x_i) mit den Stuetzstellen y_j = j und x_i = m + i. Jede quadratische Teilmatrix
einer Cauchy-Matrix ist invertierbar, also genuegen beliebige k der k + m Symbole (MDS). Die Positionen der
fehlenden Symbole sind bekannt (Symbolindex, CRC32), deshalb reicht ein Gleichungssystem nur ueber die
fehlenden Datensymbole - kein Berlekamp-Massey. Da die Stuetzstellen nur von m abhaengen, nutzt eine kuerzere
letzte Gruppe eine Teilmatrix derselben Matrix.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from qrcodegenmod._tables import MULTIPLY_TABLE

from .errors import ContainerError

U8 = npt.NDArray[np.uint8]
FIELD = 256
_INVERSE = np.array([0, *(int(np.argmax(MULTIPLY_TABLE[a] == 1)) for a in range(1, FIELD))], dtype=np.uint8)


def _coefficients(rows: Sequence[int], columns: Sequence[int], m: int) -> U8:
    """Cauchy-Koeffizienten 1 / (y_j + x_i) fuer Paritaetszeilen `rows` und Datenspalten `columns`."""
    y = np.asarray(rows, dtype=np.uint8)[:, None]
    x = (np.asarray(columns, dtype=np.int64) + m).astype(np.uint8)[None, :]
    coefficients: U8 = _INVERSE[y ^ x]
    return coefficients


def _symbol_arrays(symbols: Sequence[bytes]) -> list[U8]:
    if len({len(s) for s in symbols}) > 1:
        raise ValueError("Symbole einer Gruppe muessen gleich lang sein")
    return [np.frombuffer(s, dtype=np.uint8) for s in symbols]


def _combine(coefficients: U8, vectors: Sequence[U8], size: int) -> U8:
    """Zeilen r: XOR ueber c von coefficients[r, c] * vectors[c] (byteweise ueber GF(256))."""
    out = np.zeros((coefficients.shape[0], size), dtype=np.uint8)
    for column, vector in enumerate(vectors):
        out ^= MULTIPLY_TABLE[coefficients[:, column][:, None], vector[None, :]]
    return out


def _check_group(k: int, m: int) -> None:
    if k < 1 or m < 0 or k + m > FIELD:
        raise ValueError(f"Gruppe k={k}, m={m}: noetig k >= 1, m >= 0, k + m <= {FIELD}")


def encode_parity(data: Sequence[bytes], m: int) -> list[bytes]:
    """m Paritaetssymbole zu k gleich langen Datensymbolen."""
    _check_group(len(data), m)
    vectors = _symbol_arrays(data)
    if m == 0:
        return []
    parity = _combine(_coefficients(range(m), range(len(data)), m), vectors, vectors[0].size)
    return [row.tobytes() for row in parity]


def _invert(matrix: U8) -> U8:
    """Gauss-Jordan ueber GF(256) ohne Pivotsuche.

    Jede fuehrende Hauptminore einer Cauchy-Matrix ist wieder eine Cauchy-Matrix und damit regulaer; ein Pivot
    wird deshalb nie null (Mutationspruefung I17c: Pivotsuche war ein aequivalenter Mutant).
    """
    size = matrix.shape[0]
    work = np.concatenate([matrix, np.eye(size, dtype=np.uint8)], axis=1)
    for col in range(size):
        work[col] = MULTIPLY_TABLE[_INVERSE[work[col, col]], work[col]]
        for row in range(size):
            if row != col and work[row, col]:
                work[row] ^= MULTIPLY_TABLE[work[row, col], work[col]]
    return work[:, size:]


def recover(symbols: dict[int, bytes], k: int, m: int) -> list[bytes]:
    """Die k Datensymbole aus den vorhandenen Symbolen (Position 0..k-1 Daten, k..k+m-1 Paritaet)."""
    _check_group(k, m)
    received = {p: v for p, v in zip(symbols, _symbol_arrays(list(symbols.values())), strict=True)}
    missing = [i for i in range(k) if i not in received]
    if not missing:
        return [received[i].tobytes() for i in range(k)]
    parity_rows = [j for j in range(m) if k + j in received]
    if len(parity_rows) < len(missing):
        raise ContainerError(
            f"{len(missing)} Datensymbole fehlen, nur {len(parity_rows)} Paritaetssymbole vorhanden"
        )
    rows = parity_rows[: len(missing)]
    known = [i for i in range(k) if i in received]
    size = received[k + rows[0]].size
    # Syndrom: Paritaet minus Beitrag der vorhandenen Daten, dann das e x e-System der fehlenden Daten loesen
    syndrome = np.stack([received[k + j] for j in rows]) ^ _combine(
        _coefficients(rows, known, m), [received[i] for i in known], size
    )
    solved = _combine(_invert(_coefficients(rows, missing, m)), list(syndrome), size)
    restored = dict(zip(missing, solved, strict=True))
    return [(received[i] if i in received else restored[i]).tobytes() for i in range(k)]
