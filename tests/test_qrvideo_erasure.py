"""Aeusserer Erasure-Code (ADR-003): systematischer Cauchy-Reed-Solomon ueber GF(256).

Orakel ist die Originalnutzlast: Aus beliebigen k von k + m Symbolen muss sie bytegenau zurueckkommen.
"""

from __future__ import annotations

import itertools
import random

import pytest

from qrvideo import ContainerError
from qrvideo.erasure import encode_parity, recover


def gf_mul(a: int, b: int) -> int:
    """Unabhaengige Referenz: Bauernmultiplikation modulo x^8 + x^4 + x^3 + x^2 + 1 (0x11D, QR-Norm)."""
    out = 0
    while b:
        if b & 1:
            out ^= a
        a = (a << 1) ^ (0x11D if a & 0x80 else 0)
        b >>= 1
    return out


def gf_inv(a: int) -> int:
    return next(b for b in range(1, 256) if gf_mul(a, b) == 1)


def symbols(rng: random.Random, k: int, size: int) -> list[bytes]:
    return [rng.randbytes(size) for _ in range(k)]


def test_parity_matches_cauchy_formula() -> None:
    """Paritaet j = Summe_i d_i / (y_j + x_i), y_j = j, x_i = m + i - nachgerechnet ohne Modultabellen."""
    rng = random.Random(1)
    k, m, size = 3, 2, 16
    data = symbols(rng, k, size)
    parity = encode_parity(data, m)
    for j in range(m):
        expected = bytearray(size)
        for i, chunk in enumerate(data):
            c = gf_inv(j ^ (m + i))
            for pos in range(size):
                expected[pos] ^= gf_mul(c, chunk[pos])
        assert parity[j] == bytes(expected)


def test_all_erasure_patterns_up_to_m_are_recovered() -> None:
    """MDS-Eigenschaft vollstaendig fuer k = 5, m = 3: jede Auswahl von k Symbolen genuegt."""
    rng = random.Random(2)
    k, m = 5, 3
    data = symbols(rng, k, 32)
    everything = dict(enumerate([*data, *encode_parity(data, m)]))
    for kept in itertools.combinations(range(k + m), k):
        assert recover({p: everything[p] for p in kept}, k, m) == data


@pytest.mark.parametrize("seed", range(20))
def test_random_erasures_in_a_full_group(seed: int) -> None:
    """Standardgruppe 126 + 14: bis zu m Symbole weg, zufaellig oder als ganzer Frame (14 am Stueck)."""
    rng = random.Random(seed)
    k, m = 126, 14
    data = symbols(rng, k, 64)
    everything = dict(enumerate([*data, *encode_parity(data, m)]))
    if seed % 2:
        start = rng.randrange(k + m - 13)
        lost = set(range(start, start + 14))
    else:
        lost = set(rng.sample(range(k + m), rng.randint(1, m)))
    assert recover({p: s for p, s in everything.items() if p not in lost}, k, m) == data


def test_full_size_symbols() -> None:
    rng = random.Random(3)
    data = symbols(rng, 20, 2945)
    everything = dict(enumerate([*data, *encode_parity(data, 4)]))
    for lost in ((0, 1, 2, 3), (5, 19, 20, 23)):
        assert recover({p: s for p, s in everything.items() if p not in lost}, 20, 4) == data


def test_more_than_m_erasures_is_a_clear_error() -> None:
    rng = random.Random(4)
    data = symbols(rng, 10, 8)
    everything = dict(enumerate([*data, *encode_parity(data, 3)]))
    survivors = {p: s for p, s in everything.items() if p not in (0, 1, 2, 12)}  # 4 > m = 3 Ausloeschungen
    with pytest.raises(ContainerError, match="3 Datensymbole fehlen, nur 2 Paritätssymbole"):
        recover(survivors, 10, 3)


def test_nothing_missing_needs_no_parity() -> None:
    data = symbols(random.Random(5), 4, 8)
    assert recover(dict(enumerate(data)), 4, 2) == data


def test_parameter_validation() -> None:
    assert encode_parity([b"ab"], 0) == []
    with pytest.raises(ValueError, match="same length"):
        encode_parity([b"ab", b"c"], 1)
    with pytest.raises(ValueError, match="256"):
        encode_parity([b"x"] * 250, 7)
    with pytest.raises(ValueError, match="same length"):
        recover({0: b"ab", 2: b"c"}, 2, 1)
