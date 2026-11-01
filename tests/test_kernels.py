"""Numba-Kernel gegen NumPy-Fallback und Tabellen gegen die Rechenvorschrift."""

from __future__ import annotations

import random
from typing import Any

import numpy as np
import pytest
import qrcodegen as ref

from qrcodegenmod import _kernels, _tables
from qrcodegenmod._layout import version_layout


def test_multiply_table_matches_reference() -> None:
    for x in (0, 1, 2, 3, 0x53, 0xCA, 255):
        for y in range(256):
            assert _tables.MULTIPLY_TABLE[x, y] == ref.QrCode._reed_solomon_multiply(x, y)


@pytest.mark.parametrize("degree", [1, 7, 10, 30, 68])
def test_divisor_matches_reference(degree: int) -> None:
    assert bytes(_tables.reed_solomon_divisor(degree)) == bytes(
        ref.QrCode._reed_solomon_compute_divisor(degree)
    )


def test_divisor_range() -> None:
    with pytest.raises(ValueError):
        _tables.reed_solomon_divisor(0)


@pytest.mark.parametrize("version", [1, 5, 6, 13, 21, 40])
@pytest.mark.parametrize("ordinal", range(4))
def test_ecc_paths_agree(version: int, ordinal: int) -> None:
    rnd = random.Random(version * 10 + ordinal)
    data = np.array(
        [rnd.randrange(256) for _ in range(_tables.num_data_codewords(version, ordinal))], dtype=np.uint8
    )
    blockecc = _tables.ECC_CODEWORDS_PER_BLOCK[ordinal][version]
    args = (
        data,
        _tables.NUM_ERROR_CORRECTION_BLOCKS[ordinal][version],
        blockecc,
        _tables.num_raw_data_modules(version) // 8,
        _tables.reed_solomon_divisor(blockecc),
        _tables.MULTIPLY_TABLE,
    )
    loop = getattr(_kernels._ecc_interleave_loop, "py_func", _kernels._ecc_interleave_loop)
    np.testing.assert_array_equal(_kernels._ecc_interleave_numpy(*args), _kernels.ecc_and_interleave(*args))
    if version <= 6:  # reine Python-Schleife ist langsam
        np.testing.assert_array_equal(loop(*args), _kernels.ecc_and_interleave(*args))


def test_layout_is_cached_and_readonly() -> None:
    layout = version_layout(40)
    assert layout is version_layout(40)
    assert layout.size == 177
    assert not layout.base.flags.writeable
    assert layout.data_positions.size >= _tables.num_raw_data_modules(40) // 8 * 8


def test_check_version() -> None:
    with pytest.raises(ValueError):
        _tables.num_raw_data_modules(0)


def _py(fn: object) -> Any:
    """Reiner Python-Rumpf eines Numba-Kernels (fuer Coverage und Gleichheit beider Pfade)."""
    return getattr(fn, "py_func", fn)


@pytest.mark.parametrize("text", ["A", "Thesis 2019 " * 20])
def test_penalty_python_path_matches_kernel(text: str) -> None:
    import qrcodegenmod as mod

    qr = mod.QrCode.encode_text(text, mod.Ecc.LOW)
    assert _py(_kernels._line_penalty)(qr.modules) == _kernels._line_penalty(qr.modules)


def test_rs_python_path_matches_kernel() -> None:
    from qrcodegenmod import _rs_decode

    rnd = random.Random(7)
    data = np.array([rnd.randrange(256) for _ in range(40)], dtype=np.uint8)
    clean = _kernels._ecc_interleave_numpy(
        data, 1, 10, 50, _tables.reed_solomon_divisor(10), _tables.MULTIPLY_TABLE
    )
    for errors in (0, 3, 5, 6):
        noisy = clean.copy()
        for pos in rnd.sample(range(50), errors):
            noisy[pos] ^= rnd.randrange(1, 256)
        a, b = noisy.copy(), noisy.copy()
        result = _py(_rs_decode._correct_block)(a, 10, _rs_decode.EXP, _rs_decode.LOG)
        assert result == _rs_decode._correct_block(b, 10, _rs_decode.EXP, _rs_decode.LOG)
        np.testing.assert_array_equal(a, b)
        if errors <= 5:
            np.testing.assert_array_equal(a, clean)
