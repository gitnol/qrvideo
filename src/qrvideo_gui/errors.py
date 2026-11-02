"""Ausnahmen aus qrvideo, GnuPG, ffmpeg und yt-dlp als verstaendliche Saetze (keine Tracebacks in der GUI).

Zuordnung nur ueber Ausnahme-Klassen, nie ueber den Wortlaut des Kerns: der ist uebersetzbar (ADR-006, I33b).
"""

from __future__ import annotations

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
from qrvideo.i18n import N_, _

from .jobs import Cancelled

LOG_HINT = N_("Technical details are in the console window.")


def _gpg_message(exc: GpgError) -> str:
    if isinstance(exc, GpgNotFoundError):
        return _("GnuPG is not installed. Please install Gpg4win (https://gpg4win.org) and restart.")
    if isinstance(exc, DecryptError):
        return _(
            "Decryption was not possible. Is your private key present and the passphrase correct? Is the "
            "message addressed to you at all?"
        )
    if isinstance(exc, EncryptError):
        return _(
            "Encrypting or signing was not possible. Does the chosen signing key belong to you (private key "
            "present) and was the passphrase entered?"
        )
    if isinstance(exc, RecipientsError):
        return _("Please tick at least one recipient whose key you fully trust.")
    return _("GnuPG reports an error: {error}").format(error=exc)


def _os_message(exc: OSError) -> str:
    name = exc.filename
    if not name:
        return _os_message_without_name(exc)
    if isinstance(exc, FileNotFoundError):
        return _("File not found: {name}").format(name=name)
    if isinstance(exc, FileExistsError):
        return _("The file already exists: {name}").format(name=name)
    if isinstance(exc, PermissionError):
        return _("No access: {name}. Is the file open in another program?").format(name=name)
    return _("File or system error: {name}: {detail}").format(name=name, detail=exc.strerror or exc)


def _os_message_without_name(exc: OSError) -> str:
    if isinstance(exc, FileNotFoundError):
        return _("File not found")
    if isinstance(exc, FileExistsError):
        return _("The file already exists")
    if isinstance(exc, PermissionError):
        return _("No access. Is the file open in another program?")
    return _("File or system error: {detail}").format(detail=exc.strerror or exc)


def friendly_message(exc: BaseException) -> str:
    """Ein bis zwei Saetze fuer den Nutzer; unbekannte Ausnahmen verraten keine Interna."""
    if isinstance(exc, Cancelled):
        return _("Cancelled.")
    if isinstance(exc, UntrustedSignatureError):
        return _(
            "The data does not come from a trusted sender or the signature is invalid. Nothing was saved. "
            "Details: {error}"
        ).format(error=exc)
    if isinstance(exc, GpgError):
        return _gpg_message(exc)
    if isinstance(exc, HandshakeError):
        return _("The file is not a valid handshake message ({error}).").format(error=exc)
    if isinstance(exc, ContainerError):
        return _(
            "No complete data was found in the video ({error}). Is it a 1080p video made with qrvideo?"
        ).format(error=exc)
    if isinstance(exc, OSError):
        return _os_message(exc)
    if isinstance(exc, ValueError):
        return str(exc)
    if type(exc).__module__.startswith("yt_dlp"):
        return _("Download from YouTube failed: {error}").format(error=exc)
    return _("Unexpected error. {hint}").format(hint=_(LOG_HINT))
