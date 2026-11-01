"""Format v3 mit Paritaet (ADR-003): Gruppen aus k Daten + m Paritaetssymbolen, an Framegrenzen.

Orakel ist die Originalnutzlast; `assemble` prueft zusaetzlich Laenge und SHA-256 aus dem Kopf.
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

import qrcodegenmod as q
from qrvideo import THESIS_LAYOUT, ContainerError, decode_frames, iter_frames
from qrvideo.container import CHUNK_BYTES, DATA_SLOTS, SYMBOL_PREFIX, plan_frames_v3, unpack_symbol
from qrvideo.encoder import TAIL_FRAMES

L = q.Ecc.LOW
CHUNK = CHUNK_BYTES[L] - SYMBOL_PREFIX
Frame = npt.NDArray[np.uint8]


def blank_symbol(frames: list[Frame], index: int) -> None:
    """Daten-QR mit globalem Symbolindex `index` weiss uebermalen (Slot 1..14 seines Frames)."""
    frame, slot = divmod(index, DATA_SLOTS)
    y, x = THESIS_LAYOUT.module_origin(slot + 1)
    size = THESIS_LAYOUT.modules * THESIS_LAYOUT.scale
    frames[frame][y : y + size, x : x + size] = 255


@pytest.fixture(scope="module")
def payload() -> bytes:
    """Drei Gruppen: 126 + 126 + 48 Chunks, der letzte Chunk kurz."""
    return random.Random(17).randbytes(CHUNK * 299 + 1234)


@pytest.fixture(scope="module")
def frames(payload: bytes) -> list[Frame]:
    return list(iter_frames(payload, L, workers=1, version=3, parity=14))


def test_plan_places_parity_after_each_group(payload: bytes) -> None:
    plans = plan_frames_v3(payload, L, parity=14)
    indices = [unpack_symbol(s)[0] for p in plans for s in p.chunks]
    assert indices == list(range(140 + 140 + 48 + 14))
    assert len(plans) == -(-342 // DATA_SLOTS) == 25
    header = plans[0].header
    assert (header.version, header.group_data, header.group_parity) == (3, 126, 14)


def test_one_lost_frame_per_group_is_recovered(payload: bytes, frames: list[Frame]) -> None:
    survivors = [f for i, f in enumerate(frames) if i not in (3, 12, 22)]
    data, _ = decode_frames(survivors)
    assert data == payload


def test_tail_repeats_the_last_frames(frames: list[Frame]) -> None:
    """Messung I17d: eine bitratenbegrenzte Zweitkodierung zerstoerte 2-3 Frames kurz vor dem Videoende."""
    assert len(frames) == 25 + TAIL_FRAMES
    for original, copy in zip(frames[-2 * TAIL_FRAMES : -TAIL_FRAMES], frames[-TAIL_FRAMES:], strict=True):
        np.testing.assert_array_equal(original, copy)


def test_last_frames_lost_before_the_tail_are_recovered(payload: bytes, frames: list[Frame]) -> None:
    survivors = [f for i, f in enumerate(frames) if i not in (22, 23, 24)]  # 3 Frames > m in Gruppe 2
    data, _ = decode_frames(survivors)
    assert data == payload


@pytest.mark.parametrize("seed", range(4))
def test_random_qr_losses_up_to_m_per_group(seed: int, payload: bytes, frames: list[Frame]) -> None:
    rng = random.Random(seed)
    damaged = [f.copy() for f in frames]
    for start, size in ((0, 140), (140, 140), (280, 62)):
        for index in rng.sample(range(start, start + size), 14):
            blank_symbol(damaged, index)
    data, report = decode_frames(damaged)
    assert data == payload
    assert report.blank_slots >= 3 * 14


def test_short_last_chunk_is_recovered_and_trimmed(payload: bytes, frames: list[Frame]) -> None:
    damaged = [f.copy() for f in frames]
    blank_symbol(damaged, 280 + 47)  # letzter Datenchunk (1234 Bytes) der letzten Gruppe
    data, _ = decode_frames(damaged)
    assert data == payload


def test_more_than_m_losses_in_a_group_is_a_clear_error(frames: list[Frame]) -> None:
    damaged = [f.copy() for f in frames]
    for index in range(140, 155):  # 15 > m = 14 in Gruppe 1
        blank_symbol(damaged, index)
    with pytest.raises(ContainerError, match="Gruppe 1: 15 Datensymbole fehlen, nur 14"):
        decode_frames(damaged)


def test_parity_must_leave_data_in_a_group() -> None:
    with pytest.raises(ValueError, match="Paritaet"):
        plan_frames_v3(b"x", L, parity=140)


def test_cli_default_is_v3_with_ecc_l_and_10_percent_parity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from qrvideo import cli

    calls: list[dict[str, Any]] = []

    def fake_encode(source: Path, target: Path, ecl: q.Ecc, *args: Any, **kwargs: Any) -> int:
        calls.append({"ecl": ecl, **kwargs})
        return 1

    monkeypatch.setattr(cli, "encode_file", fake_encode)
    source = tmp_path / "a.bin"
    source.write_bytes(b"x")
    for extra in ([], ["--parity", "0", "--ecc", "M"], ["--parity", "20"]):
        assert cli.main(["encode", str(source), "-o", str(tmp_path / "a.mp4"), "--force", *extra]) == 0
    assert (calls[0]["ecl"], calls[0]["parity"]) == (L, 14)  # Standard seit I18 (Live-Messung I17e)
    assert (calls[1]["ecl"], calls[1]["parity"]) == (q.Ecc.MEDIUM, None)  # Format v2 bleibt waehlbar
    assert (calls[2]["ecl"], calls[2]["parity"]) == (L, 28)


@pytest.mark.parametrize(("version", "parity"), [(2, 0), (3, 14), (3, 0)])
def test_frame_count_matches_rendered_frames(version: int, parity: int) -> None:
    from qrvideo.encoder import frame_count

    payload = os.urandom(CHUNK * 20 + 7)
    rendered = sum(1 for _ in iter_frames(payload, L, 1, version, parity))
    assert frame_count(payload, L, parity if version == 3 else None) == rendered


@pytest.mark.parametrize("value", ["-1", "60", "zehn"])
def test_cli_rejects_bad_parity(value: str, tmp_path: Path) -> None:
    from qrvideo import cli

    with pytest.raises(SystemExit):
        cli.main(["encode", str(tmp_path / "a"), "-o", str(tmp_path / "b.mp4"), "--parity", value])


@pytest.mark.integration
def test_parity_video_survives_h264_and_a_lost_frame(tmp_path: Path) -> None:
    from qrvideo.encoder import encode_bytes
    from qrvideo.videoio import VideoSettings, read_video

    payload = os.urandom(CHUNK * 30)
    video = tmp_path / "v3.mp4"
    assert encode_bytes(payload, video, L, workers=1, settings=VideoSettings(crf=23), parity=14) == 4 + 3
    survivors = [f for i, f in enumerate(read_video(video)) if i != 1]
    data, report = decode_frames(survivors)
    assert data == payload
    assert report.failures == []
