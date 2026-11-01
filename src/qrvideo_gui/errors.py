"""Ausnahmen aus qrvideo, GnuPG, ffmpeg und yt-dlp als verstaendliche Saetze (keine Tracebacks in der GUI).

Die Kernmodule melden mit festen Textanfaengen (z. B. `GpgError("gpg nicht gefunden: ...")`); diese stehen
hier als Konstanten, damit eine Aenderung im Kern an genau einer Stelle auffaellt (tests/test_gui_errors.py).
"""

from __future__ import annotations

from qrvideo.container import ContainerError
from qrvideo.crypto import GpgError, UntrustedSignatureError
from qrvideo.handshake import HandshakeError

from .jobs import Cancelled

GPG_MISSING = "gpg nicht gefunden"
DECRYPT_FAILED = "Entschluesseln fehlgeschlagen"
ENCRYPT_FAILED = "Verschluesseln fehlgeschlagen"
RECIPIENTS_UNTRUSTED = "Empfaenger fehlen"
LOG_HINT = "Technische Details stehen im Konsolenfenster."


def _gpg_message(exc: GpgError) -> str:
    text = str(exc)
    if text.startswith(GPG_MISSING):
        return (
            "GnuPG ist nicht installiert. Bitte Gpg4win installieren (https://gpg4win.org) und neu starten."
        )
    if text.startswith(DECRYPT_FAILED):
        return (
            "Entschlüsseln war nicht möglich. Ist Ihr privater Schlüssel vorhanden und die Passphrase "
            "richtig? Ist die Nachricht überhaupt an Sie gerichtet?"
        )
    if text.startswith(ENCRYPT_FAILED):
        return (
            "Verschlüsseln oder Signieren war nicht möglich. Gehört der gewählte Signaturschlüssel Ihnen "
            "(privater Schlüssel vorhanden) und wurde die Passphrase eingegeben?"
        )
    if text.startswith(RECIPIENTS_UNTRUSTED):
        return "Bitte mindestens einen Empfänger ankreuzen, dessen Schlüssel Sie voll vertrauen."
    return f"GnuPG meldet einen Fehler: {text}"


def _os_message(exc: OSError) -> str:
    where = f": {exc.filename}" if exc.filename else ""
    if isinstance(exc, FileNotFoundError):
        return f"Datei nicht gefunden{where}"
    if isinstance(exc, FileExistsError):
        return f"Die Datei gibt es schon{where}"
    if isinstance(exc, PermissionError):
        return f"Kein Zugriff{where}. Ist die Datei in einem anderen Programm geöffnet?"
    return f"Datei- oder Systemfehler{where}: {exc.strerror or exc}"


def friendly_message(exc: BaseException) -> str:
    """Ein bis zwei Saetze fuer den Nutzer; unbekannte Ausnahmen verraten keine Interna."""
    if isinstance(exc, Cancelled):
        return "Abgebrochen."
    if isinstance(exc, UntrustedSignatureError):
        return (
            "Die Daten stammen nicht von einem vertrauten Absender oder die Signatur ist ungültig. "
            f"Nichts wurde gespeichert. Details: {exc}"
        )
    if isinstance(exc, GpgError):
        return _gpg_message(exc)
    if isinstance(exc, HandshakeError):
        return f"Die Datei ist keine gültige Handshake-Nachricht ({exc})."
    if isinstance(exc, ContainerError):
        return (
            f"Im Video wurden keine vollständigen Daten gefunden ({exc}). "
            "Ist es ein mit qrvideo erzeugtes Video in 1080p?"
        )
    if isinstance(exc, OSError):
        return _os_message(exc)
    if isinstance(exc, ValueError):
        return str(exc)
    if type(exc).__module__.startswith("yt_dlp"):
        return f"Download von YouTube fehlgeschlagen: {exc}"
    return f"Unerwarteter Fehler. {LOG_HINT}"
