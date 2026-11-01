"""Einzelne QR-Codes als PNG schreiben und lesen (Handshake-Nachrichten der Thesis).

Ohne Bildbibliothek: PNG ueber zlib (8 Bit Grau, RGB, RGBA; alle Filtertypen). Gelesen werden nur pixelgenaue
QR-Bilder (gerendert, nicht abfotografiert): Die Modulgroesse ergibt sich aus dem Finder-Muster oben links
(7 Module), danach liest qrcodegenmod.reader die Matrix.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import numpy.typing as npt

import qrcodegenmod as q
from qrcodegenmod._jit import jit
from qrcodegenmod.reader import QrDecodeError, decode_modules

SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 6: 4}


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_png(path: Path, image: npt.NDArray[np.uint8]) -> None:
    """8-Bit-Graustufen-PNG ohne Filter."""
    height, width = image.shape
    rows = np.hstack((np.zeros((height, 1), np.uint8), image.astype(np.uint8)))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows.tobytes(), 9))
        + _chunk(b"IEND", b"")
    )


MAX_SIDE = 2048  # ein V40-QR mit Skalierung 8 braucht ca. 1500 px; Schutz vor PNG-Bomben (Code-Review #3)


@jit
def _unfilter_kernel(data: npt.NDArray[np.uint8], bpp: int) -> npt.NDArray[np.uint8]:
    """PNG-Filter rueckgaengig machen; -1 im ersten Feld einer Zeile = unbekannter Filter."""
    height, width = data.shape[0], data.shape[1] - 1
    out = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        kind = data[y, 0]
        if kind > 4:
            return out[:0]  # leeres Ergebnis signalisiert unbekannten Filter
        for x in range(width):
            raw = int(data[y, x + 1])
            left = int(out[y, x - bpp]) if x >= bpp else 0
            up = int(out[y - 1, x]) if y > 0 else 0
            upleft = int(out[y - 1, x - bpp]) if (y > 0 and x >= bpp) else 0
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
                pred = left if (pa <= pb and pa <= pc) else (up if pb <= pc else upleft)
            out[y, x] = (raw + pred) & 0xFF
    return out


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> npt.NDArray[np.uint8]:
    data = np.frombuffer(raw, dtype=np.uint8).reshape(height, width * bpp + 1)
    out = _unfilter_kernel(data, bpp)
    if out.shape[0] != height:
        raise ValueError("Unbekannter PNG-Filter")
    return out


def _chunks(data: bytes) -> dict[bytes, bytes]:
    """IHDR und zusammengefuegte IDAT-Daten; Laenge und CRC jedes Chunks werden geprueft."""
    pos, found, idat = len(SIGNATURE), {}, bytearray()
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("PNG abgeschnitten")
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("PNG abgeschnitten")
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[end - 4 : end])
        if zlib.crc32(kind + body) != crc:
            raise ValueError(f"PNG-Chunk {kind!r}: CRC falsch")
        if kind == b"IDAT":
            idat += body
        elif kind == b"IHDR":
            found[kind] = body
        pos = end
    found[b"IDAT"] = bytes(idat)
    return found


def read_png(path: Path) -> npt.NDArray[np.uint8]:
    """PNG (8 Bit, Grau/RGB/RGBA, ohne Interlacing, hoechstens MAX_SIDE x MAX_SIDE) als Graustufenbild."""
    data = path.read_bytes()
    if not data.startswith(SIGNATURE):
        raise ValueError(f"{path} ist keine PNG-Datei")
    found = _chunks(data)
    if len(found.get(b"IHDR", b"")) != 13:
        raise ValueError("PNG ohne gueltigen IHDR")
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", found[b"IHDR"])
    if depth != 8 or color not in _CHANNELS or interlace:
        raise ValueError("Nur 8-Bit-PNG in Grau, RGB oder RGBA ohne Interlacing")
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        raise ValueError(f"PNG zu gross oder leer: {width}x{height} (hoechstens {MAX_SIDE}x{MAX_SIDE})")
    channels = _CHANNELS[color]
    expected = height * (width * channels + 1)
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(found[b"IDAT"], expected + 1)  # nie mehr als noetig entpacken
    except zlib.error as exc:
        raise ValueError(f"PNG-Daten defekt: {exc}") from exc
    if len(raw) != expected or inflater.unconsumed_tail:
        raise ValueError(f"Bilddaten passen nicht zur Groesse {width}x{height}")
    pixels = _unfilter(raw, width, height, channels).reshape(height, width, channels)
    if channels == 1:
        gray: npt.NDArray[np.uint8] = pixels[:, :, 0]
        return gray
    luma = pixels[:, :, :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    result: npt.NDArray[np.uint8] = np.round(luma).astype(np.uint8)
    return result


def write_qr_png(path: Path, data: bytes, scale: int = 4, border: int = 4) -> None:
    """Nachricht als QR-Code (ECC MEDIUM, kleinste Version) in eine PNG-Datei."""
    write_png(path, q.QrCode.encode_binary(data, q.Ecc.MEDIUM).to_image(scale=scale, border=border))


def read_qr_png(path: Path) -> bytes:
    """Liest einen pixelgenau gerenderten QR-Code aus einer PNG-Datei."""
    image = read_png(path)
    dark = image < 128
    ys, xs = np.nonzero(dark)
    if ys.size == 0:
        raise QrDecodeError("Kein dunkles Modul im Bild")
    top, left = int(np.min(ys)), int(np.min(xs))
    side = int(max(np.max(ys) - top, np.max(xs) - left)) + 1
    run = int(np.argmin(dark[top, left:])) if not dark[top, left:].all() else side
    scale = run // 7
    if scale < 1 or run % 7 or side % scale:
        raise QrDecodeError("Finder-Muster oben links nicht erkennbar")
    n = side // scale
    centers = np.arange(n) * scale + scale // 2
    return decode_modules(dark[top + centers][:, left + centers]).data
