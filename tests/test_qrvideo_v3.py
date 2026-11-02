"""Format v3 (ADR-003): selbstbeschreibende Daten-QR mit CRC32, Kopf-QR ohne statische Flaeche."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace

import pytest

import qrcodegenmod as q
from qrvideo import THESIS_LAYOUT, ContainerError, FrameHeader, decode_frames, iter_frames
from qrvideo.container import (
    CHUNK_BYTES,
    SYMBOL_PREFIX,
    header_payload,
    pack_symbol,
    plan_frames_v3,
    symbol_index,
    unpack_symbol,
)
from qrvideo.encoder import render_frame

L = q.Ecc.LOW
V3_CHUNK = CHUNK_BYTES[L] - SYMBOL_PREFIX


def v3_header(index: int = 3, k: int = 126, m: int = 14, chunk: int = V3_CHUNK) -> FrameHeader:
    return FrameHeader(index, 10, 100_000, chunk, L.ordinal, bytes(range(32)), 3, k, m)


def test_v3_header_roundtrip_through_qr_payload() -> None:
    header = v3_header()
    assert FrameHeader.unpack(header_payload(header)) == header


def test_v3_header_fills_the_qr_and_changes_every_frame() -> None:
    """Messung I17a: der fast statische Kopf-QR war auf YouTube das schwaechste Glied (13/14 je Block)."""
    first, second = header_payload(v3_header(0)), header_payload(v3_header(1))
    assert len(first) == len(second) == CHUNK_BYTES[q.Ecc.MEDIUM]
    differing = sum(a != b for a, b in zip(first, second, strict=True))
    assert differing > 0.9 * len(first)


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        (v3_header(k=0), "Gruppe"),
        (v3_header(k=200, m=56), "Gruppe"),
        (v3_header(chunk=CHUNK_BYTES[L]), "Chunkgröße"),
    ],
)
def test_v3_header_validation(header: FrameHeader, reason: str) -> None:
    with pytest.raises(ContainerError, match=reason):
        FrameHeader.unpack(header_payload(header))


def test_v3_length_check_counts_parity_symbols() -> None:
    """13 Chunks passen in einen Frame (14 Slots), mit 14 Paritaetssymbolen der Gruppe nicht mehr."""
    fits = FrameHeader(0, 1, 13 * V3_CHUNK, V3_CHUNK, L.ordinal, bytes(32), 3, 126, 0)
    assert FrameHeader.unpack(header_payload(fits)) == fits
    with pytest.raises(ContainerError, match="Länge"):
        FrameHeader.unpack(header_payload(replace(fits, group_parity=14)))


def test_symbol_index_skips_parity_of_previous_groups() -> None:
    assert [symbol_index(i, 126, 14) for i in (0, 125, 126, 130)] == [0, 125, 140, 144]


def test_v2_header_payload_is_unchanged() -> None:
    header = FrameHeader(1, 2, 3, 2331, 1, bytes(32))
    assert header_payload(header) == header.pack()
    assert FrameHeader.unpack(header.pack()) == header


def test_symbol_roundtrip_and_crc() -> None:
    data = os.urandom(V3_CHUNK)
    raw = pack_symbol(7, data)
    assert len(raw) == CHUNK_BYTES[L]
    assert unpack_symbol(raw) == (7, data)
    for position in (0, 5, 100, len(raw) - 1):
        broken = bytearray(raw)
        broken[position] ^= 0x01
        with pytest.raises(ContainerError, match="CRC"):
            unpack_symbol(bytes(broken))
    with pytest.raises(ContainerError, match="kurz"):
        unpack_symbol(raw[: SYMBOL_PREFIX - 1])


@pytest.mark.parametrize("size", [0, 1, V3_CHUNK * 14, 100_000])
def test_v3_roundtrip_in_memory(size: int) -> None:
    payload = os.urandom(size)
    data, report = decode_frames(iter_frames(payload, L, workers=1, version=3))
    assert data == payload
    assert report.failures == []


def test_v3_plan_uses_self_describing_symbols() -> None:
    payload = os.urandom(V3_CHUNK * 20 + 5)
    plans = plan_frames_v3(payload, L)
    assert [len(p.chunks) for p in plans] == [14, 7]
    indices = [unpack_symbol(c)[0] for p in plans for c in p.chunks]
    assert indices == list(range(21))
    assert plans[0].header.sha256 == hashlib.sha256(payload).digest()


def test_v3_data_survives_a_lost_header() -> None:
    """v2 verliert mit dem Kopf den ganzen Frame; v3-Daten-QR tragen ihren Index selbst."""
    payload = os.urandom(V3_CHUNK * 30)
    frames = list(iter_frames(payload, L, workers=1, version=3))
    frames[1][: THESIS_LAYOUT.tile - 3, : THESIS_LAYOUT.tile - 3] = 255  # Kopf-Slot weiss
    data, report = decode_frames(frames)
    assert data == payload
    assert report.blank_slots == 1 + 2 * (3 * 14 - 30)  # 3 Frames, alle als Nachlauf wiederholt


def test_v3_crc_mismatch_is_an_erasure_not_wrong_bytes() -> None:
    """Ein QR, den der innere Code 'erfolgreich' liest, dessen CRC aber nicht passt, zaehlt als fehlend."""
    payload = os.urandom(V3_CHUNK * 3)
    plan = plan_frames_v3(payload, L)[0]
    forged = bytearray(plan.chunks[1])
    forged[-1] ^= 0xFF
    frame = render_frame(replace(plan, chunks=(plan.chunks[0], bytes(forged), plan.chunks[2])))
    with pytest.raises(ContainerError, match="erster fehlender: 1"):
        decode_frames([frame])
