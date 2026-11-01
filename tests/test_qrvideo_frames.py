"""Frame-Geometrie, Containerformat und Roundtrip ohne Videodatei."""

from __future__ import annotations

import os
import random

import numpy as np
import pytest
from conftest import armored_chunk

import qrcodegenmod as q
from qrvideo import (
    THESIS_LAYOUT,
    ContainerError,
    FrameHeader,
    decode_frames,
    decode_frames_legacy,
    iter_frames,
)
from qrvideo.container import CHUNK_BYTES, assemble, plan_frames
from qrvideo.encoder import render_tile


def thesis_compose(tiles: list[np.ndarray]) -> np.ndarray:
    """Nachbau von POC.py erstelle_gesamtframe_v2 + process_verarbeitung (Orakel fuer die Geometrie)."""
    row = np.hstack(tiles)
    parts = np.split(row, 3, axis=1)
    frame = np.vstack(parts)[3:-3, 3:-3]
    frame = np.vstack((frame, np.full((1080 - frame.shape[0], frame.shape[1]), 255, np.uint8)))
    return np.hstack((frame, np.full((1080, 1920 - frame.shape[1]), 255, np.uint8)))


def test_compose_matches_thesis(rng: random.Random) -> None:
    tiles = [render_tile(armored_chunk(rng, 300).encode(), q.Ecc.LOW) for _ in range(13)]
    tiles += [np.full((362, 362), 255, np.uint8)] * 2  # leere Slots am Ende wie in der Thesis
    ours = THESIS_LAYOUT.compose([*tiles[:13], None, None])
    np.testing.assert_array_equal(ours, thesis_compose(tiles))


def test_module_origins_match_analyze_video() -> None:
    # analyze_video.py: Zeilen 1, 363, 725; Spalten 1, 363, 725, 1087, 1449
    assert [THESIS_LAYOUT.module_origin(i) for i in (0, 6, 14)] == [(1, 1), (363, 363), (725, 1449)]


def test_sample_recovers_modules(rng: random.Random) -> None:
    codes = [
        q.QrCode.encode_binary(
            bytes(rng.randrange(256) for _ in range(500)), q.Ecc.MEDIUM, mask=1, minversion=40
        )
        for _ in range(15)
    ]
    frame = THESIS_LAYOUT.compose([c.to_image(2, 2) for c in codes])
    modules, brightness = THESIS_LAYOUT.sample(frame)
    for slot, code in enumerate(codes):
        np.testing.assert_array_equal(modules[slot], code.modules)
    assert float(np.max(brightness)) < 220


def test_layout_validation() -> None:
    with pytest.raises(ValueError):
        THESIS_LAYOUT.compose([None] * 16)
    with pytest.raises(ValueError):
        THESIS_LAYOUT.compose([np.zeros((10, 10), np.uint8)])
    with pytest.raises(ValueError):
        THESIS_LAYOUT.sample(np.zeros((720, 1280), np.uint8))


def test_chunk_sizes_fill_version_40() -> None:
    for ecl, size in CHUNK_BYTES.items():
        qr = q.QrCode.encode_binary(bytes(size), ecl, minversion=40, boostecl=False)
        assert qr.get_version() == 40
        with pytest.raises(q.DataTooLongError):
            q.QrCode.encode_binary(bytes(size + 1), ecl, minversion=40, boostecl=False)


def test_header_roundtrip_and_validation() -> None:
    header = FrameHeader(3, 7, 123456, 2331, 1, bytes(range(32)))
    assert FrameHeader.unpack(header.pack()) == header
    with pytest.raises(ContainerError):
        FrameHeader.unpack(b"QRV1" + header.pack()[4:])
    with pytest.raises(ContainerError):
        FrameHeader.unpack(FrameHeader(7, 7, 1, 1, 1, bytes(32)).pack())


def test_plan_and_assemble_errors() -> None:
    payload = os.urandom(2331 * 20 + 5)
    plans = plan_frames(payload)
    assert [len(p.chunks) for p in plans] == [14, 7]
    chunks = {i: c for i, c in enumerate(c for p in plans for c in p.chunks)}
    assert assemble(plans[0].header, chunks) == payload
    with pytest.raises(ContainerError, match="fehlen"):
        assemble(plans[0].header, {k: v for k, v in chunks.items() if k != 5})
    with pytest.raises(ContainerError, match="SHA-256"):
        assemble(plans[0].header, {**chunks, 0: bytes(2331)})
    with pytest.raises(ContainerError, match="Laenge"):
        assemble(plans[0].header, {**chunks, 20: b"\x00"})


@pytest.mark.parametrize("size", [0, 1, 2331 * 14, 100_000])
def test_roundtrip_in_memory(size: int) -> None:
    payload = os.urandom(size)
    data, report = decode_frames(iter_frames(payload, workers=1))
    assert data == payload
    assert report.failures == [] and report.corrected_bytes == 0


def test_roundtrip_survives_noise_shuffle_and_duplicates() -> None:
    """Wie nach YouTube: verrauschte Grauwerte, ein doppelter Frame, vertauschte Reihenfolge.

    Feste Nutzlast: Bei sigma 100 liest der Leser fuer etwa 0,7 % der Zufallsnutzlasten einen QR-Code nicht,
    und v2 hat keine Paritaet — mit `os.urandom` scheiterte der Test daher selten und zufaellig (I28).
    Diese Grenze deckt v3 ab.
    """
    payload = random.Random(108).randbytes(60_000)
    frames = list(iter_frames(payload, workers=1))
    noise = np.random.default_rng(1)
    noisy = [
        np.clip(f.astype(np.int16) + noise.normal(0, 100, f.shape), 0, 255).astype(np.uint8) for f in frames
    ]
    noisy = [noisy[1], noisy[0], noisy[1], *noisy[2:]]
    data, report = decode_frames(noisy)
    assert data == payload
    assert report.corrected_bytes > 0


def test_missing_frame_is_reported() -> None:
    frames = list(iter_frames(os.urandom(80_000), workers=1))
    with pytest.raises(ContainerError, match="fehlen"):
        decode_frames(frames[1:])


def test_no_header_at_all() -> None:
    with pytest.raises(ContainerError, match="Kopf"):
        decode_frames([np.full((1080, 1920), 255, np.uint8)])


def test_parallel_rendering_matches_serial() -> None:
    payload = os.urandom(2331 * 30)
    serial = list(iter_frames(payload, workers=1))
    parallel = list(iter_frames(payload, workers=2))
    assert len(serial) == len(parallel) == 3
    for a, b in zip(serial, parallel, strict=True):
        np.testing.assert_array_equal(a, b)


def test_legacy_frames(rng: random.Random) -> None:
    """Thesis-Format: Slot 0 Status, danach Armor-Text-Chunks a 2100 Zeichen ueber encode_text."""
    chunks = [armored_chunk(rng) for _ in range(20)]
    tiles = [q.QrCode.encode_text(c, q.Ecc.LOW, **q.THESIS_PARAMS).to_image() for c in chunks]
    status = q.QrCode.encode_text("verschluesselter Status", q.Ecc.LOW, **q.THESIS_PARAMS).to_image()
    frames = [THESIS_LAYOUT.compose([status, *tiles[:14]]), THESIS_LAYOUT.compose([status, *tiles[14:]])]
    data, report = decode_frames_legacy(frames)
    assert data == "".join(chunks).encode()
    assert report.blank_slots == 8

    broken = frames[0].copy()
    broken[400:700, 400:700] = 0
    with pytest.raises(ContainerError, match="unlesbar"):
        decode_frames_legacy([broken])


def test_header_wire_format_is_big_endian() -> None:
    """Golden-Bytes: das Format ist spezifiziert, nicht nur symmetrisch (ADR-001)."""
    packed = FrameHeader(1, 2, 3, 2331, 1, bytes(32)).pack()
    assert (
        packed[:23]
        == b"QRV2" + b"\x00\x00\x00\x01" + b"\x00\x00\x00\x02" + bytes(7) + b"\x03" + b"\x09\x1b\x01"
    )
    assert len(packed) == 55


def test_tiles_use_thesis_version_and_mask() -> None:
    from qrcodegenmod.reader import decode_modules

    frame = THESIS_LAYOUT.compose(
        [render_tile(b"Kopf", q.Ecc.MEDIUM), render_tile(b"x" * 2331, q.Ecc.MEDIUM)]
    )
    modules, _ = THESIS_LAYOUT.sample(frame)
    for slot in (0, 1):
        decoded = decode_modules(modules[slot])
        assert (decoded.version, decoded.mask) == (40, 1)
