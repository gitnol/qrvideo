"""Fehlertexte der GUI: verständliches Deutsch statt Ausnahme-Klassen und Tracebacks."""

from __future__ import annotations

import pytest

from qrvideo.container import ContainerError
from qrvideo.crypto import (
    DecryptError,
    EncryptError,
    GpgError,
    GpgNotFoundError,
    RecipientsError,
    UntrustedSignatureError,
)
from qrvideo.handshake import HandshakeError
from qrvideo_gui.errors import friendly_message
from qrvideo_gui.jobs import Cancelled


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (Cancelled(), "Abgebrochen"),
        (FileNotFoundError(2, "No such file", "bericht.mp4"), "nicht gefunden: bericht.mp4"),
        (PermissionError(13, "Access denied", "ziel.mp4"), "anderen Programm geöffnet"),
        (UntrustedSignatureError("Signaturschluessel ABC ist nicht voll vertraut"), "vertrauten Absender"),
        # Zuordnung per Klasse, nicht per Wortlaut des Kerns (I33b): der Text ist hier absichtlich fremd
        (GpgNotFoundError("gpg not found"), "Gpg4win"),
        (DecryptError("decryption failed"), "privater Schlüssel"),
        (EncryptError("invalid recipient"), "Signaturschlüssel"),
        (RecipientsError("none given"), "Empfänger"),
        (GpgError("gpg nicht gefunden: alter Wortlaut zählt nicht mehr"), "GnuPG meldet einen Fehler"),
        (ContainerError("Kein lesbarer v2-Kopf im Video"), "keine vollständigen Daten"),
        (HandshakeError("Kein JSON"), "keine gültige Handshake-Nachricht"),
        (ValueError("Keine YouTube-Video-ID erkannt: 'x'"), "Keine YouTube-Video-ID"),
        (OSError(28, "No space left on device"), "No space left"),
    ],
)
def test_known_errors_get_german_hint(exc: BaseException, expected: str) -> None:
    message = friendly_message(exc)
    assert expected in message
    assert type(exc).__name__ not in message


def test_core_detail_is_kept_for_signature_problems() -> None:
    message = friendly_message(UntrustedSignatureError("Signaturschluessel ABC ist nicht voll vertraut"))
    assert "nicht voll vertraut" in message


def test_download_errors_from_yt_dlp_are_recognised() -> None:
    error_type = type("DownloadError", (Exception,), {"__module__": "yt_dlp.utils"})
    message = friendly_message(error_type("HTTP Error 404"))
    assert "YouTube" in message
    assert "HTTP Error 404" in message


def test_unexpected_error_points_to_log_without_internals() -> None:
    message = friendly_message(ZeroDivisionError("division by zero"))
    assert "Unerwarteter Fehler" in message
    assert "Konsolenfenster" in message
    assert "division by zero" not in message
