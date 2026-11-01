"""Lesen von Modul-Matrizen inkl. Reed-Solomon-Fehlerkorrektur."""

from __future__ import annotations

import random

import numpy as np
import pytest
from conftest import armored_chunk

import qrcodegenmod as mod
from qrcodegenmod import _tables
from qrcodegenmod._rs_decode import ReedSolomonError, correct_block
from qrcodegenmod.reader import QrDecodeError, decode_modules


def _encoded_block(rnd: random.Random, ndata: int, nsym: int) -> np.ndarray:
    from qrcodegenmod._kernels import _ecc_interleave_numpy

    data = np.array([rnd.randrange(256) for _ in range(ndata)], dtype=np.uint8)
    # ein Block: rawcodewords = ndata + nsym
    return _ecc_interleave_numpy(
        data, 1, nsym, ndata + nsym, _tables.reed_solomon_divisor(nsym), _tables.MULTIPLY_TABLE
    )


@pytest.mark.parametrize("nsym", [7, 10, 22, 30])
def test_rs_corrects_up_to_capacity(nsym: int) -> None:
    rnd = random.Random(nsym)
    for errors in range(nsym // 2 + 1):
        clean = _encoded_block(rnd, 100, nsym)
        noisy = clean.copy()
        for pos in rnd.sample(range(noisy.size), errors):
            noisy[pos] ^= rnd.randrange(1, 256)
        assert correct_block(noisy, nsym) == errors
        np.testing.assert_array_equal(noisy, clean)


def test_rs_rejects_too_many_errors() -> None:
    rnd = random.Random(3)
    rejected = 0
    for _ in range(20):
        noisy = _encoded_block(rnd, 50, 10)
        for pos in rnd.sample(range(noisy.size), 9):
            noisy[pos] ^= rnd.randrange(1, 256)
        try:
            correct_block(noisy, 10)
        except ReedSolomonError:
            rejected += 1
    assert rejected >= 18  # Fehlkorrekturen jenseits der Kapazitaet sind theoretisch moeglich, aber selten


def test_rs_requires_uint8() -> None:
    with pytest.raises(TypeError):
        correct_block(np.zeros(10, dtype=np.int64), 4)


TEXTS = ["", "12345678901", "HELLO WORLD 42", "gemischter Text mit Umlauten äöü", "x" * 1000]


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("ecl", list(mod.Ecc))
def test_roundtrip_clean(text: str, ecl: mod.Ecc) -> None:
    qr = mod.QrCode.encode_text(text, ecl)
    result = decode_modules(qr.modules)
    assert result.data == text.encode("utf-8")
    assert (result.version, result.mask, result.ecl) == (
        qr.get_version(),
        qr.get_mask(),
        qr.get_error_correction_level(),
    )
    assert result.corrected_bytes == 0


def test_roundtrip_eci_segment() -> None:
    segs = [mod.QrSegment.make_eci(26), mod.QrSegment.make_bytes(b"\x00\xffbin")]
    qr = mod.QrCode.encode_segments(segs, mod.Ecc.MEDIUM)
    assert decode_modules(qr.modules).data == b"\x00\xffbin"
    big_eci = mod.QrCode.encode_segments(
        [mod.QrSegment.make_eci(20000), mod.QrSegment.make_bytes(b"A")], mod.Ecc.LOW
    )
    assert decode_modules(big_eci.modules).data == b"A"


def test_thesis_chunk_with_module_errors(rng: random.Random) -> None:
    """Wie nach YouTube: ca. 0,1 % falsch binarisierte Module (Thesis: ~30 von 31.329)."""
    text = armored_chunk(rng)
    qr = mod.QrCode.encode_text(text, mod.Ecc.LOW, **mod.THESIS_PARAMS)
    noisy = qr.modules.copy()
    positions = qr.modules.size
    for flat in rng.sample(range(positions), 35):
        y, x = divmod(flat, qr.get_size())
        if 10 < y < 160 and 10 < x < 160:  # Formatbereich unangetastet lassen
            noisy[y, x] ^= True
    result = decode_modules(noisy)
    assert result.data == text.encode()
    assert result.corrected_bytes > 0


def test_format_survives_bit_errors() -> None:
    qr = mod.QrCode.encode_text("FORMAT", mod.Ecc.QUARTILE, mask=5)
    noisy = qr.modules.copy()
    noisy[8, 0] ^= True
    noisy[8, 1] ^= True
    assert decode_modules(noisy).mask == 5


@pytest.mark.parametrize("shape", [(20, 20), (21, 22), (181, 181)])
def test_invalid_shapes(shape: tuple[int, int]) -> None:
    with pytest.raises(QrDecodeError):
        decode_modules(np.zeros(shape, dtype=bool))


def test_garbage_is_rejected() -> None:
    with pytest.raises(QrDecodeError):
        decode_modules(np.zeros((177, 177), dtype=bool))
    rnd = np.random.default_rng(1)
    qr = mod.QrCode.encode_text("A" * 50, mod.Ecc.LOW, mask=0)
    noisy = qr.modules.copy()
    noisy[9:, 9:] = rnd.integers(0, 2, size=noisy[9:, 9:].shape).astype(bool)
    with pytest.raises(QrDecodeError):
        decode_modules(noisy)
