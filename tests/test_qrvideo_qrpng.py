"""QR-PNG fuer den Handshake: Schreiben, Lesen, Filtertypen, fremde PNG-Varianten."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from qrcodegenmod.reader import QrDecodeError
from qrvideo.qrpng import SIGNATURE, _chunk, read_png, read_qr_png, write_png, write_qr_png


def _png(path: Path, pixels: np.ndarray, color: int, filters: list[int]) -> None:
    """Hilfs-PNG mit vorgegebenen Filtertypen je Zeile (Encoder fuer Sub/Up/Average/Paeth)."""
    height, width = pixels.shape[:2]
    bpp = 1 if pixels.ndim == 2 else pixels.shape[2]
    flat = pixels.reshape(height, width * bpp).astype(np.int32)
    raw = bytearray()
    for y in range(height):
        kind = filters[y % len(filters)]
        prev = flat[y - 1] if y else np.zeros(width * bpp, np.int32)
        row = []
        for x in range(width * bpp):
            left = flat[y, x - bpp] if x >= bpp else 0
            upleft = prev[x - bpp] if x >= bpp else 0
            up = prev[x]
            if kind == 0:
                pred = 0
            elif kind == 1:
                pred = left
            elif kind == 2:
                pred = up
            elif kind == 3:
                pred = (left + up) // 2
            else:
                p = left + up - upleft
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                pred = left if pa <= pb and pa <= pc else (up if pb <= pc else upleft)
            row.append((flat[y, x] - pred) & 0xFF)
        raw += bytes([kind, *row])
    header = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    path.write_bytes(
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )


def test_png_roundtrip(tmp_path: Path) -> None:
    image = np.random.default_rng(1).integers(0, 256, (17, 23), dtype=np.uint8)
    write_png(tmp_path / "a.png", image)
    np.testing.assert_array_equal(read_png(tmp_path / "a.png"), image)


def test_all_filters_and_color_types(tmp_path: Path) -> None:
    rng = np.random.default_rng(2)
    gray = rng.integers(0, 256, (9, 11), dtype=np.uint8)
    _png(tmp_path / "g.png", gray, 0, [0, 1, 2, 3, 4])
    np.testing.assert_array_equal(read_png(tmp_path / "g.png"), gray)
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    _png(tmp_path / "rgb.png", rgb, 2, [4, 3, 1])
    np.testing.assert_array_equal(read_png(tmp_path / "rgb.png"), gray)
    rgba = np.concatenate((rgb, np.full((9, 11, 1), 255, np.uint8)), axis=2)
    _png(tmp_path / "rgba.png", rgba, 6, [2, 4])
    np.testing.assert_array_equal(read_png(tmp_path / "rgba.png"), gray)


def test_png_errors(tmp_path: Path) -> None:
    (tmp_path / "x.png").write_bytes(b"GIF89a")
    with pytest.raises(ValueError, match="keine PNG"):
        read_png(tmp_path / "x.png")
    (tmp_path / "leer.png").write_bytes(SIGNATURE + _chunk(b"IEND", b""))
    with pytest.raises(ValueError, match="IHDR"):
        read_png(tmp_path / "leer.png")
    header = struct.pack(">IIBBBBB", 1, 1, 16, 0, 0, 0, 0)
    (tmp_path / "16bit.png").write_bytes(SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IEND", b""))
    with pytest.raises(ValueError, match="8-Bit"):
        read_png(tmp_path / "16bit.png")
    raw = bytes([7, 0])
    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    (tmp_path / "f.png").write_bytes(
        SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")
    )
    with pytest.raises(ValueError, match="Filter"):
        read_png(tmp_path / "f.png")


@pytest.mark.parametrize(("size", "scale", "border"), [(10, 1, 0), (1500, 4, 4), (2331, 2, 2)])
def test_qr_png_roundtrip(tmp_path: Path, size: int, scale: int, border: int) -> None:
    message = os.urandom(size)
    write_qr_png(tmp_path / "qr.png", message, scale=scale, border=border)
    assert read_qr_png(tmp_path / "qr.png") == message


def test_qr_png_rejects_non_qr(tmp_path: Path) -> None:
    write_png(tmp_path / "weiss.png", np.full((50, 50), 255, np.uint8))
    with pytest.raises(QrDecodeError, match="dunkles"):
        read_qr_png(tmp_path / "weiss.png")
    blob = np.full((50, 50), 255, np.uint8)
    blob[10:20, 10:15] = 0
    write_png(tmp_path / "fleck.png", blob)
    with pytest.raises(QrDecodeError, match="Finder"):
        read_qr_png(tmp_path / "fleck.png")


def test_rgb_uses_luma_weights(tmp_path: Path) -> None:
    pixels = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)
    _png(tmp_path / "farben.png", pixels, 2, [0])
    np.testing.assert_array_equal(read_png(tmp_path / "farben.png"), [[76, 150, 29]])


@pytest.mark.parametrize("scale", [6, 7, 9])
def test_qr_png_large_scales(tmp_path: Path, scale: int) -> None:
    write_qr_png(tmp_path / "gross.png", b"Thesis 2019", scale=scale, border=1)
    assert read_qr_png(tmp_path / "gross.png") == b"Thesis 2019"


@pytest.mark.parametrize(("color", "interlace"), [(3, 0), (0, 1)])
def test_unsupported_png_variants(tmp_path: Path, color: int, interlace: int) -> None:
    header = struct.pack(">IIBBBBB", 2, 2, 8, color, 0, 0, interlace)
    body = zlib.compress(bytes(2 * 3))
    (tmp_path / "v.png").write_bytes(
        SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", body) + _chunk(b"IEND", b"")
    )
    with pytest.raises(ValueError, match="8-Bit"):
        read_png(tmp_path / "v.png")
