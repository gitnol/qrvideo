"""Live gegen YouTube (nur mit QRVIDEO_LIVE=1): das Thesis-Video von 2019 erneut laden und dekodieren.

Belegt, dass der Rueckweg des Kanals (yt-dlp, 1080p/30 fps, Legacy-Decoder) mit YouTube heute funktioniert.
Erster Lauf 2026-10-26: Video noch online, 90 Frames, 0 unlesbare QR-Codes, bytegenau zur Thesis-PGP.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from test_qrvideo_video import THESIS_VIDEO

from qrvideo import decode_video
from qrvideo.youtube import download, parse_browser_spec

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("QRVIDEO_LIVE") != "1", reason="nur mit QRVIDEO_LIVE=1 (Netz)"),
]


@pytest.mark.skipif(
    not os.environ.get("QRVIDEO_LIVE_THESIS_VIDEO"), reason="QRVIDEO_LIVE_THESIS_VIDEO (Video-ID) fehlt"
)
def test_thesis_video_still_decodes_from_youtube(tmp_path: Path) -> None:
    """Die Video-ID steht bewusst nicht im Repo (verweist auf den Kanal)."""
    path = download(os.environ["QRVIDEO_LIVE_THESIS_VIDEO"], tmp_path)
    data, report = decode_video(path, legacy=True)
    assert report.frames == 90
    assert report.failures == []
    expected = THESIS_VIDEO.with_suffix(".pgp")
    if expected.is_file():
        assert data.replace(b"\n", b"\r\n") == expected.read_bytes()
    else:
        assert data.startswith(b"-----BEGIN PGP MESSAGE-----")


V2_PAYLOAD_SHA256 = "2a91be1f4c6a6949ff9f1c8de50b7a30fe0ce6a1e0da3eb8a51457324fb4682b"


@pytest.mark.skipif(
    not os.environ.get("QRVIDEO_LIVE_V2_VIDEO"), reason="QRVIDEO_LIVE_V2_VIDEO (Video-ID) fehlt"
)
def test_v2_video_survives_youtube(tmp_path: Path) -> None:
    """I9b: v2-Testvideo (1,5 MB Zufallsdaten, ECC M), per YouTube Studio nicht gelistet hochgeladen.

    Die Video-ID steht bewusst nicht im Repo (verweist auf den Kanal). Erster Lauf 2026-10-26: 46 Frames,
    690 QR-Codes, 0 unlesbar, 4258 Bytes per Reed-Solomon korrigiert.
    """
    path = download(os.environ["QRVIDEO_LIVE_V2_VIDEO"], tmp_path)
    data, report = decode_video(path)
    assert hashlib.sha256(data).hexdigest() == V2_PAYLOAD_SHA256
    assert report.failures == []


@pytest.mark.skipif(
    not os.environ.get("QRVIDEO_LIVE_V3_VIDEO"), reason="QRVIDEO_LIVE_V3_VIDEO (Video-ID) fehlt"
)
def test_v3_parity_video_survives_youtube(tmp_path: Path) -> None:
    """I17e: dieselbe Nutzlast wie I9b, Format v3 mit ECC L und 10 % Paritaet, per YouTube Studio hochgeladen.

    Erster Lauf 2026-10-27: 45 Frames (inkl. 3 Nachlauf), 659 QR-Codes, 0 unlesbar, 3581 Bytes korrigiert.
    """
    path = download(os.environ["QRVIDEO_LIVE_V3_VIDEO"], tmp_path)
    data, report = decode_video(path)
    assert hashlib.sha256(data).hexdigest() == V2_PAYLOAD_SHA256
    assert report.frames == 45
    assert report.failures == []


@pytest.mark.skipif(
    not os.environ.get("QRVIDEO_LIVE_API_VIDEO"), reason="QRVIDEO_LIVE_API_VIDEO (Video-ID) fehlt"
)
def test_api_upload_survives_youtube(tmp_path: Path) -> None:
    """I30b2: dasselbe Video wie I17e, diesmal vom Nutzer per `qrvideo upload` (YouTube Data API) hochgeladen.

    Ist es „privat“ gelandet (nicht verifiziertes API-Projekt), holt es nur ein berechtigtes Konto ab:
    `QRVIDEO_LIVE_COOKIES=BROWSER[:PROFIL]`. Ablauf: `docs/testing/INTEGRATION_TESTS.md`, Abschnitt 1a.
    """
    cookies = os.environ.get("QRVIDEO_LIVE_COOKIES")
    browser = parse_browser_spec(cookies) if cookies else None
    path = download(os.environ["QRVIDEO_LIVE_API_VIDEO"], tmp_path, cookies_from_browser=browser)
    data, report = decode_video(path)
    assert hashlib.sha256(data).hexdigest() == V2_PAYLOAD_SHA256
    assert report.frames == 45
