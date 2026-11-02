"""Regressionstests aus dem Code-Review 2026-10-26: manipulierte Eingaben aus fremden Videos und QR-Codes."""

from __future__ import annotations

import hashlib
import time

import pytest

import qrcodegenmod as q
from qrcodegenmod.reader import QrDecodeError, decode_modules
from qrcodegenmod.segment import int_to_bits
from qrvideo.container import ContainerError, FrameHeader
from qrvideo.decoder import decode_frames
from qrvideo.encoder import render_tile
from qrvideo.layout import THESIS_LAYOUT

DIGEST = hashlib.sha256(b"x").digest()


def _frame_with_header(length: int, chunk: int, ecc: int = 1, frames: int = 1) -> object:
    """Frame mit beliebigem (auch unsinnigem) Kopf in Slot 0 und einem echten Daten-QR in Slot 1."""
    header = FrameHeader(0, frames, length, chunk, ecc, DIGEST)
    return THESIS_LAYOUT.compose([render_tile(header.pack(), q.Ecc.MEDIUM), render_tile(b"x", q.Ecc.MEDIUM)])


@pytest.mark.parametrize(
    ("length", "chunk", "ecc"),
    [
        (1, 0, 1),  # Review #2a: ZeroDivisionError
        (1, 1000, 1),  # Chunkgroesse passt zu keiner ECC-Stufe
        (1, 2331, 7),  # ECC-Ordinal ausserhalb 0..3
        (2331 * 14 + 1, 2331, 1),  # Laenge braucht mehr Chunks, als ein Frame Slots hat
    ],
)
def test_hostile_header_is_rejected(length: int, chunk: int, ecc: int) -> None:
    """Der Kopf selbst wird abgelehnt (Meldung im Bericht), nicht erst spaeter beim Zusammensetzen."""
    with pytest.raises(ContainerError, match="Kein lesbarer Kopf"):
        decode_frames([_frame_with_header(length, chunk, ecc)])  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("frames", "length", "reason"),
    [(2_000_000, 2331, "Limit"), (1, 2331 * 14 + 1, "passt nicht in 1 Frames")],
)
def test_header_limits_have_clear_reasons(frames: int, length: int, reason: str) -> None:
    header = FrameHeader(0, frames, length, 2331, 1, DIGEST)
    with pytest.raises(ContainerError, match=reason):
        FrameHeader.unpack(header.pack())


def test_huge_claimed_length_fails_fast() -> None:
    """Review #2b: Laenge 2**63 liess assemble praktisch endlos laufen."""
    frame = _frame_with_header(2**63, 2331, frames=2**32 - 1)
    start = time.perf_counter()
    with pytest.raises(ContainerError):
        decode_frames([frame])  # type: ignore[list-item]
    assert time.perf_counter() - start < 5


@pytest.mark.parametrize(
    ("segment", "reason"),
    [
        (q.QrSegment(q.Mode.ALPHANUMERIC, 2, [1] * 11), "Alphanumeric"),  # 2047 > 2024
        (q.QrSegment(q.Mode.ALPHANUMERIC, 1, [1] * 6), "Alphanumeric"),  # 63 > 44
        (q.QrSegment(q.Mode.NUMERIC, 3, int_to_bits(1023, 10)), "Numeric"),  # 1023 > 999
        (q.QrSegment(q.Mode.NUMERIC, 2, int_to_bits(127, 7)), "Numeric"),  # 127 > 99
    ],
)
def test_out_of_range_segment_values(segment: q.QrSegment, reason: str) -> None:
    """Review #5: IndexError bzw. stille Fehlinterpretation statt QrDecodeError."""
    qr = q.QrCode.encode_segments([segment], q.Ecc.MEDIUM)
    with pytest.raises(QrDecodeError, match=reason):
        decode_modules(qr.modules)


# ---- I12: PNG-Leser (Review #3, #8) ----

import struct  # noqa: E402
import zlib  # noqa: E402
from pathlib import Path  # noqa: E402

from qrvideo.qrpng import SIGNATURE, _chunk, read_png  # noqa: E402


def _png_bytes(width: int, height: int, raw: bytes, color: int = 0) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def test_png_bomb_is_rejected_quickly(tmp_path: Path) -> None:
    """Review #3: 439 KB PNG mit 20000x20000 Pixeln belegte 2,3 GiB RAM."""
    path = tmp_path / "bombe.png"
    path.write_bytes(_png_bytes(20000, 20000, bytes(20001) * 2000))  # Daten bewusst zu kurz
    start = time.perf_counter()
    with pytest.raises(ValueError, match="groß"):
        read_png(path)
    assert time.perf_counter() - start < 1


def test_png_data_must_match_size(tmp_path: Path) -> None:
    path = tmp_path / "kurz.png"
    path.write_bytes(_png_bytes(100, 100, bytes(101) * 50))
    with pytest.raises(ValueError, match="Bilddaten"):
        read_png(path)


@pytest.mark.parametrize("cut", [10, 20, 40])
def test_truncated_png_raises_value_error(tmp_path: Path, cut: int) -> None:
    """Review #8: struct.error statt ValueError bei abgeschnittener Datei."""
    data = _png_bytes(4, 4, bytes(5) * 4)
    path = tmp_path / "abgeschnitten.png"
    path.write_bytes(data[: len(SIGNATURE) + cut])
    with pytest.raises(ValueError):
        read_png(path)


def test_png_crc_is_checked(tmp_path: Path) -> None:
    data = bytearray(_png_bytes(4, 4, bytes(5) * 4))
    data[len(SIGNATURE) + 8] ^= 0xFF  # erstes Byte der IHDR-Daten kippen
    path = tmp_path / "crc.png"
    path.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="CRC"):
        read_png(path)


@pytest.mark.skipif(
    not q.HAVE_NUMBA, reason="ohne Numba laeuft der Unfilter in Python (begrenzt durch MAX_SIDE)"
)
def test_large_filtered_png_is_fast(tmp_path: Path) -> None:
    """Review #3: Filter Sub/Average/Paeth liefen als Python-Schleife pro Byte (2000x2000: 1,2 s)."""
    width = height = 2000
    raw = b"".join(bytes([kind]) + bytes(width) for kind in (1, 3, 4, 2) * (height // 4))
    path = tmp_path / "gross.png"
    path.write_bytes(_png_bytes(width, height, raw))
    read_png(path)  # Aufwaermen (JIT)
    start = time.perf_counter()
    assert read_png(path).shape == (height, width)
    assert time.perf_counter() - start < 0.5


# ---- I13: send ueberschreibt keine Eingabe, Dateinamen (Review #4, #14) ----


class _FakeCrypto:
    def encrypt(
        self,
        data: bytes,
        recipients: list[str],
        signer: str,
        passphrase: str | None,
        filename: str | None = None,
    ) -> bytes:
        return b"CIPHERTEXT"


@pytest.mark.integration
def test_send_keeps_gpg_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review #4: `send daten.gpg -o daten.mp4` ersetzte daten.gpg durch das Chiffrat."""
    import qrvideo.cli as cli

    monkeypatch.setattr(cli, "_crypto", lambda args: _FakeCrypto())
    source = tmp_path / "daten.gpg"
    source.write_bytes(b"ORIGINAL")
    args = [
        "send",
        str(source),
        "-r",
        "X",
        "--sign",
        "X",
        "-o",
        str(tmp_path / "daten.mp4"),
        "--workers",
        "1",
    ]
    assert cli.main(args) == 0
    assert source.read_bytes() == b"ORIGINAL"


def test_send_refuses_existing_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import qrvideo.cli as cli

    monkeypatch.setattr(cli, "_crypto", lambda args: _FakeCrypto())
    source, target = tmp_path / "a.xlsx", tmp_path / "a.mp4"
    source.write_bytes(b"x")
    target.write_bytes(b"altes Video")
    assert cli.main(["send", str(source), "-r", "X", "--sign", "X", "-o", str(target)]) == 1
    assert target.read_bytes() == b"altes Video"


def test_truncated_filename_does_not_end_with_dot() -> None:
    """Review #14: strip vor dem Kuerzen liess Namen auf '.' enden; Windows legt dann eine andere Datei an."""
    from qrvideo.paths import safe_filename

    name = safe_filename("a" * 199 + ". x")
    assert len(name) <= 200 and not name.endswith((".", " "))


# ---- I14: Encoder mit begrenztem Fenster, Worker-Grenze, atomares Schreiben (Review #1, #9, #13) ----

import os  # noqa: E402
from collections.abc import Callable, Iterable, Iterator  # noqa: E402
from concurrent.futures import Future  # noqa: E402

import numpy as np  # noqa: E402
import numpy.typing as npt  # noqa: E402


class _CountingExecutor:
    """Synchroner Ersatz fuer ProcessPoolExecutor; zaehlt, wie viele Frames in Auftrag gegeben wurden."""

    submitted = 0

    def __init__(self, max_workers: int) -> None:
        _CountingExecutor.submitted = 0

    def __enter__(self) -> _CountingExecutor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def submit(self, fn: Callable[..., object], *args: object) -> Future[object]:
        _CountingExecutor.submitted += 1
        future: Future[object] = Future()
        future.set_result(fn(*args))
        return future

    def map(self, fn: Callable[..., object], items: Iterable[object], chunksize: int = 1) -> Iterator[object]:
        todo = list(items)
        _CountingExecutor.submitted += len(todo)
        return iter([fn(item) for item in todo])


def test_encoder_keeps_a_bounded_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review #1 (HIGH): pool.map reichte alle Frames sofort ein; fertige Frames stauten sich im RAM."""
    import qrvideo.encoder as encoder

    monkeypatch.setattr(encoder, "ProcessPoolExecutor", _CountingExecutor)
    frames = encoder.iter_frames(os.urandom(2331 * 14 * 20), workers=2)  # 20 Frames
    next(frames)
    assert _CountingExecutor.submitted <= 2 * 2 + 1


def test_worker_count_is_capped_on_windows() -> None:
    """Review #9: ProcessPoolExecutor erlaubt unter Windows hoechstens 61 Worker."""
    from qrvideo.encoder import worker_count

    assert worker_count(100, 1000, windows=True) == 61
    assert worker_count(100, 1000, windows=False) == 100
    assert worker_count(None, 3, windows=True) <= 3


@pytest.mark.integration
def test_failed_encoding_leaves_no_video(tmp_path: Path) -> None:
    """Review #13: Abbruch waehrend des Schreibens hinterliess ein halbes, scheinbar gueltiges MP4."""
    from qrvideo.encoder import iter_frames
    from qrvideo.videoio import write_video

    def broken() -> Iterator[npt.NDArray[np.uint8]]:
        frames = iter_frames(os.urandom(2331 * 14 * 3), workers=1)
        yield next(frames)
        raise RuntimeError("Abbruch beim Rendern")

    target = tmp_path / "video.mp4"
    with pytest.raises(RuntimeError):
        write_video(target, broken())
    assert list(tmp_path.iterdir()) == []


# ---- I16: kleinere Haertungen (Review #10, #11, #12) ----

import sys  # noqa: E402
from types import ModuleType, SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402


@pytest.mark.integration
def test_video_file_cannot_redirect_to_other_files(tmp_path: Path) -> None:
    """Review #10: ein ffconcat-Skript namens boese.mp4 liess ffmpeg eine andere lokale Datei lesen."""
    from qrvideo.encoder import iter_frames
    from qrvideo.videoio import read_video, write_video

    write_video(tmp_path / "geheim.mp4", iter_frames(os.urandom(5000), workers=1))
    evil = tmp_path / "boese.mp4"
    evil.write_text("ffconcat version 1.0\nfile 'geheim.mp4'\n", encoding="ascii")
    with pytest.raises(OSError):
        next(read_video(evil))


def test_download_target_dir_is_not_a_template(tmp_path: Path) -> None:
    """Review #11: der Zielordner landete im outtmpl; ein '%' im Pfad wird dort als Platzhalter gelesen."""
    from qrvideo import youtube

    seen: dict[str, object] = {}

    class FakeYdl:
        def __init__(self, options: dict[str, object]) -> None:
            seen.update(options)

        def __enter__(self) -> FakeYdl:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def extract_info(self, url: str, download: bool) -> dict[str, str]:
            return {"id": "AbCdEfGhIjK", "ext": "mp4"}

        def prepare_filename(self, info: dict[str, str]) -> str:
            paths = seen.get("paths", {})
            home = paths.get("home", "") if isinstance(paths, dict) else ""
            target = Path(str(home)) / str(seen["outtmpl"]).replace("%(id)s", info["id"]).replace(
                "%(ext)s", "mp4"
            )
            target.write_bytes(b"video")
            return str(target)

    folder = tmp_path / "100%ordner"
    path = youtube.download("AbCdEfGhIjK", folder, ydl_class=FakeYdl)
    assert seen["outtmpl"] == "%(id)s.%(ext)s"
    assert seen["paths"] == {"home": str(folder)}
    assert path == folder / "AbCdEfGhIjK.mp4"


class _RefreshError(Exception):
    pass


def _fake_google(
    monkeypatch: pytest.MonkeyPatch, refresh_fails: bool, response: dict[str, Any] | None = None
) -> dict[str, int]:
    """Attrappen der Google-Module, damit `upload` ohne Netz und OAuth-Client laeuft."""
    calls = {"refresh": 0, "flow": 0}

    class Creds:
        def __init__(self, label: str, valid: bool) -> None:
            self.label, self.valid, self.expired, self.refresh_token = label, valid, not valid, "r"

        @classmethod
        def from_authorized_user_file(cls, path: str, scopes: list[str]) -> Creds:
            return cls("alt", valid=False)

        def refresh(self, request: object) -> None:
            calls["refresh"] += 1
            if refresh_fails:
                raise _RefreshError("Token widerrufen")
            self.valid, self.expired, self.label = True, False, "aufgefrischt"

        def to_json(self) -> str:
            return self.label

    class Flow:
        @classmethod
        def from_client_secrets_file(cls, path: str, scopes: list[str]) -> Flow:
            return cls()

        def run_local_server(self, port: int) -> Creds:
            calls["flow"] += 1
            return Creds("neu", valid=True)

    answer = response or {"id": "VID"}
    request = SimpleNamespace(next_chunk=lambda num_retries: (None, answer))
    service = SimpleNamespace(videos=lambda: SimpleNamespace(insert=lambda **kw: request))
    modules = {
        "google.auth.transport.requests": SimpleNamespace(Request=object),
        "google.auth.exceptions": SimpleNamespace(RefreshError=_RefreshError),
        "google.oauth2.credentials": SimpleNamespace(Credentials=Creds),
        "google_auth_oauthlib.flow": SimpleNamespace(InstalledAppFlow=Flow),
        "googleapiclient.discovery": SimpleNamespace(build=lambda *a, **kw: service),
        "googleapiclient.http": SimpleNamespace(MediaFileUpload=lambda *a, **kw: None),
    }
    for name, module in modules.items():
        fake = ModuleType(name)
        fake.__dict__.update(vars(module))
        monkeypatch.setitem(sys.modules, name, fake)
    return calls


@pytest.mark.parametrize(("refresh_fails", "saved", "flows"), [(False, "aufgefrischt", 0), (True, "neu", 1)])
def test_upload_token_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refresh_fails: bool, saved: str, flows: int
) -> None:
    """Review #12: aufgefrischtes Token wurde nicht gespeichert, RefreshError endete als Traceback."""
    from qrvideo import youtube

    calls = _fake_google(monkeypatch, refresh_fails)
    token = tmp_path / "token.json"
    token.write_text("alt", encoding="utf-8")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    uploaded = youtube.upload(video, "Test", tmp_path / "client.json", token_path=token)
    assert (uploaded.video_id, uploaded.privacy) == (
        "VID",
        None,
    )  # Antwort ohne Status: unbekannt, nicht geraten
    assert token.read_text(encoding="utf-8") == saved
    assert calls == {"refresh": 1, "flow": flows}


@pytest.mark.parametrize("privacy", ["private", "unlisted"])
def test_upload_reports_the_visibility_youtube_chose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, privacy: str
) -> None:
    """I30b1: nicht verifizierte API-Projekte landen auf „privat“, obwohl „nicht gelistet“ verlangt war."""
    from qrvideo import youtube

    _fake_google(monkeypatch, False, {"id": "VID", "status": {"privacyStatus": privacy}})
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    token = tmp_path / "token.json"
    token.write_text("alt", encoding="utf-8")
    uploaded = youtube.upload(video, "Test", tmp_path / "client.json", token_path=token)
    assert (uploaded.video_id, uploaded.privacy) == ("VID", privacy)
