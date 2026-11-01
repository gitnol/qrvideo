"""Bit-Gleichheit mit der offiziellen Referenzimplementierung qrcodegen (nayuki)."""

from __future__ import annotations

import random

import pytest
import qrcodegen as ref
from conftest import ECC_PAIRS, armored_chunk, assert_same

import qrcodegenmod as mod

TEXTS = [
    "",
    "0",
    "0123456789" * 7,
    "HELLO WORLD",
    "THE QUICK BROWN FOX $%*+-./: 42",
    "Hallo Welt, äöü ß – 日本語 🙂",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
]


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize(("ecl", "ref_ecl"), ECC_PAIRS)
def test_encode_text_auto_mask(text: str, ecl: mod.Ecc, ref_ecl: ref.QrCode.Ecc) -> None:
    assert_same(mod.QrCode.encode_text(text, ecl), ref.QrCode.encode_text(text, ref_ecl))


@pytest.mark.parametrize("mask", range(8))
def test_fixed_masks(mask: int, rng: random.Random) -> None:
    text = armored_chunk(rng, 300)
    ours = mod.QrCode.encode_text(text, mod.Ecc.MEDIUM, mask=mask)
    theirs = ref.QrCode.encode_segments(ref.QrSegment.make_segments(text), ref.QrCode.Ecc.MEDIUM, mask=mask)
    assert_same(ours, theirs)


def test_thesis_parameters(rng: random.Random) -> None:
    """Thesis-Einstellung: 2100 Zeichen, Version 40, Maske 1, ECC LOW."""
    for _ in range(5):
        text = armored_chunk(rng)
        ours = mod.QrCode.encode_text(text, mod.Ecc.LOW, **mod.THESIS_PARAMS)
        theirs = ref.QrCode.encode_segments(ref.QrSegment.make_segments(text), ref.QrCode.Ecc.LOW, 40, 40, 1)
        assert_same(ours, theirs)
        assert ours.get_size() == 177


def test_encode_binary(rng: random.Random) -> None:
    data = bytes(rng.randrange(256) for _ in range(500))
    assert_same(
        mod.QrCode.encode_binary(data, mod.Ecc.QUARTILE),
        ref.QrCode.encode_binary(data, ref.QrCode.Ecc.QUARTILE),
    )
    as_list = list(data[:50])
    assert_same(
        mod.QrCode.encode_binary(as_list, mod.Ecc.LOW), ref.QrCode.encode_binary(as_list, ref.QrCode.Ecc.LOW)
    )


def test_boostecl_off(rng: random.Random) -> None:
    text = armored_chunk(rng, 20)
    ours = mod.QrCode.encode_text(text, mod.Ecc.LOW, boostecl=False)
    theirs = ref.QrCode.encode_segments(ref.QrSegment.make_segments(text), ref.QrCode.Ecc.LOW, boostecl=False)
    assert_same(ours, theirs)


def test_mixed_segments_with_eci() -> None:
    ours_segs = [
        mod.QrSegment.make_eci(26),
        mod.QrSegment.make_alphanumeric("ABC"),
        mod.QrSegment.make_numeric("12345"),
    ]
    ref_segs = [
        ref.QrSegment.make_eci(26),
        ref.QrSegment.make_alphanumeric("ABC"),
        ref.QrSegment.make_numeric("12345"),
    ]
    assert_same(
        mod.QrCode.encode_segments(ours_segs, mod.Ecc.HIGH),
        ref.QrCode.encode_segments(ref_segs, ref.QrCode.Ecc.HIGH),
    )


def test_low_level_constructor(rng: random.Random) -> None:
    data = bytes(
        rng.randrange(256) for _ in range(ref.QrCode._get_num_data_codewords(5, ref.QrCode.Ecc.MEDIUM))
    )
    assert_same(mod.QrCode(5, mod.Ecc.MEDIUM, data, 3), ref.QrCode(5, ref.QrCode.Ecc.MEDIUM, data, 3))


@pytest.mark.slow
@pytest.mark.parametrize("version", range(1, 41))
def test_all_versions_all_ecc(version: int, rng: random.Random) -> None:
    for ecl, ref_ecl in ECC_PAIRS:
        capacity = ref.QrCode._get_num_data_codewords(version, ref_ecl)
        data = bytes(rng.randrange(256) for _ in range(capacity - 3))
        mask = rng.randrange(-1, 8) if version > 10 else -1
        ours = mod.QrCode.encode_segments(
            [mod.QrSegment.make_bytes(data)], ecl, version, version, mask, False
        )
        theirs = ref.QrCode.encode_segments(
            [ref.QrSegment.make_bytes(data)], ref_ecl, version, version, mask, False
        )
        assert_same(ours, theirs)
