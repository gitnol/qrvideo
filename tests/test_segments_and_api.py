"""Segmente, Fehlerfaelle und Ausgabeformate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pytest
import qrcodegen as ref

import qrcodegenmod as mod


@pytest.mark.parametrize("digits", ["", "7", "42", "123", "1234", "0123456789012"])
def test_numeric_bits(digits: str) -> None:
    assert mod.QrSegment.make_numeric(digits).get_data() == ref.QrSegment.make_numeric(digits).get_data()


@pytest.mark.parametrize("text", ["", "A", "AB", "ABC", "HELLO WORLD", "$%*+-./: 09"])
def test_alphanumeric_bits(text: str) -> None:
    assert (
        mod.QrSegment.make_alphanumeric(text).get_data() == ref.QrSegment.make_alphanumeric(text).get_data()
    )


@pytest.mark.parametrize("value", [0, 127, 128, 16383, 16384, 999_999])
def test_eci_bits(value: int) -> None:
    assert mod.QrSegment.make_eci(value).get_data() == ref.QrSegment.make_eci(value).get_data()


def test_segment_metadata() -> None:
    seg = mod.QrSegment.make_bytes(b"\x00\xff")
    assert seg.get_mode() is mod.Mode.BYTE
    assert seg.get_num_chars() == 2
    assert seg.get_data() == [0] * 8 + [1] * 8
    assert not seg.bits.flags.writeable
    assert mod.QrSegment.Mode.BYTE.get_mode_bits() == 4


@pytest.mark.parametrize(
    ("factory", "arg"),
    [
        (mod.QrSegment.make_numeric, "12a"),
        (mod.QrSegment.make_alphanumeric, "abc"),
        (mod.QrSegment.make_eci, -1),
        (mod.QrSegment.make_eci, 1_000_000),
        (mod.QrSegment.make_bytes, [256]),
    ],
)
def test_segment_errors(factory: Callable[[Any], object], arg: object) -> None:
    with pytest.raises(ValueError):
        factory(arg)


def test_segment_type_errors() -> None:
    with pytest.raises(TypeError):
        mod.QrSegment.make_bytes("text")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        mod.QrSegment.make_segments(b"bytes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        mod.QrCode.encode_binary("text", mod.Ecc.LOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        mod.QrSegment(mod.Mode.BYTE, -1, [])
    with pytest.raises(ValueError):
        mod.QrSegment(mod.Mode.BYTE, 1, [2])


def test_too_long() -> None:
    with pytest.raises(mod.DataTooLongError, match="Data length"):
        mod.QrCode.encode_binary(bytes(3000), mod.Ecc.LOW)
    with pytest.raises(mod.DataTooLongError):
        mod.QrCode.encode_text("A" * 30, mod.Ecc.HIGH, maxversion=1)


def test_char_count_overflow_reports_segment_too_long() -> None:
    seg = mod.QrSegment(mod.Mode.BYTE, 300, [0] * 2400)  # 300 Zeichen passen nicht in 8 Zaehlerbits
    with pytest.raises(mod.DataTooLongError, match="Segment too long"):
        mod.QrCode.encode_segments([seg], mod.Ecc.LOW, 1, 9)


@pytest.mark.parametrize(
    "kwargs", [{"minversion": 0}, {"maxversion": 41}, {"minversion": 5, "maxversion": 4}, {"mask": 8}]
)
def test_invalid_parameters(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        mod.QrCode.encode_text("x", mod.Ecc.LOW, **kwargs)


def test_constructor_validation() -> None:
    with pytest.raises(ValueError):
        mod.QrCode(41, mod.Ecc.LOW, b"", 0)
    with pytest.raises(ValueError):
        mod.QrCode(1, mod.Ecc.LOW, b"", 9)
    with pytest.raises(TypeError):
        mod.QrCode(1, "LOW", b"", 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        mod.QrCode(1, mod.Ecc.LOW, b"\x00", 0)


def test_accessors_and_rendering() -> None:
    qr = mod.QrCode.encode_text("Thesis 2019", mod.Ecc.MEDIUM)
    assert qr.get_size() == qr.get_version() * 4 + 17
    assert qr.get_module(0, 0) is True  # Finder-Muster oben links
    assert qr.get_module(-1, 0) is False
    assert not qr.modules.flags.writeable

    framed = qr.get_module_as_numpy(2)
    assert framed.shape == (qr.get_size() + 4,) * 2
    assert not framed[:2].any()

    img = qr.to_image(scale=2, border=2)
    assert img.dtype == np.uint8
    assert img.shape == ((qr.get_size() + 4) * 2,) * 2
    assert img[0, 0] == 255 and img[4, 4] == 0

    svg = qr.to_svg_str(4)
    assert svg.count("M") == int(qr.modules.sum()) and 'viewBox="0 0 33 33"' in svg.replace(
        str(qr.get_size() + 8), "33"
    )


def test_rendering_errors() -> None:
    qr = mod.QrCode.encode_text("x", mod.Ecc.LOW)
    for call in (lambda: qr.get_module_as_numpy(-1), lambda: qr.to_image(scale=0), lambda: qr.to_svg_str(-1)):
        with pytest.raises(ValueError):
            call()
