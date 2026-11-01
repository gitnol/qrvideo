"""Handshake der Thesis: Server Challenge (Angebot) und Client Response (Auswahl), verschluesselt + signiert.

Thesis (POC.py QRCodeManagement): Statusfelder per Position aus zeilengetrenntem Text gelesen, dabei um eine
Position versetzt (KNOWN_ISSUES K10). Hier: versioniertes JSON mit Feldnamen, Typpruefung, sichere Dateinamen.
Version 2 (seit I29c1, ADR-005) nennt Videos als `<kanal>:<verweis>`; Version 1 (nackte YouTube-IDs) bleibt
lesbar.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .channel import channel_ref, parse_channel_ref
from .crypto import Crypto, SignatureInfo
from .paths import safe_filename
from .youtube import parse_video_id

FORMAT_VERSION = 2
READABLE_VERSIONS = (1, 2)
MAX_ENTRIES = 200  # eine Challenge muss in einen QR-Code passen


class HandshakeError(ValueError):
    """Nachricht ist kein gueltiger Handshake."""


@dataclass(frozen=True)
class Challenge:
    """Angebot des Servers: verfuegbare Dateien und bereits hochgeladene Videos."""

    files: tuple[str, ...]
    videos: tuple[str, ...] = field(default=())  # `<kanal>:<verweis>`; beim Schreiben auch YouTube-Link/-ID
    kind: str = "challenge"


@dataclass(frozen=True)
class Response:
    """Antwort des Clients: genau eine gewaehlte Datei oder ein Video (`<kanal>:<verweis>`)."""

    selection: str
    kind: str = "response"


def _encode(message: Challenge | Response) -> bytes:
    fields = asdict(message)
    if isinstance(message, Challenge):
        # ungueltige Eingaben scheitern beim Absender (ValueError), nicht erst beim Empfaenger
        fields["videos"] = [channel_ref(v) for v in message.videos]
    return json.dumps({"v": FORMAT_VERSION, **fields}, ensure_ascii=False).encode("utf-8")


def _str_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_ENTRIES or not all(isinstance(v, str) for v in value):
        raise HandshakeError(f"Feld {name!r} muss eine Liste von Texten sein (hoechstens {MAX_ENTRIES})")
    return value


def _video(value: str, version: int) -> str:
    if version == 1:
        return f"youtube:{parse_video_id(value)}"
    try:
        return "{}:{}".format(*parse_channel_ref(value))
    except ValueError as exc:
        raise HandshakeError(f"Ungueltiges Video {value!r}: {exc}") from exc


def _selection(value: str, version: int) -> str:
    """Datei (Basisname) oder in Version 2 ein Video; kein sicherer Dateiname enthaelt einen Doppelpunkt."""
    if version == 1 or ":" not in value:
        return safe_filename(value)
    try:
        return "{}:{}".format(*parse_channel_ref(value))
    except ValueError as exc:
        raise HandshakeError(f"Ungueltige Auswahl {value!r}: {exc}") from exc


def parse(data: bytes) -> Challenge | Response:
    """Prueft und liest eine entschluesselte Nachricht; Dateinamen werden entschaerft, Video-IDs validiert."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandshakeError("Kein JSON") from exc
    version = raw.get("v") if isinstance(raw, dict) else None
    if not isinstance(raw, dict) or version not in READABLE_VERSIONS:
        raise HandshakeError(f"Unbekannte Formatversion: {version!r}")
    if raw.get("kind") == "challenge":
        files = tuple(safe_filename(f) for f in _str_list(raw.get("files"), "files"))
        videos = tuple(_video(v, version) for v in _str_list(raw.get("videos", []), "videos"))
        return Challenge(files, videos)
    if raw.get("kind") == "response":
        selection = raw.get("selection")
        if not isinstance(selection, str) or not selection:
            raise HandshakeError("Feld 'selection' fehlt")
        return Response(_selection(selection, version))
    raise HandshakeError(f"Unbekannte Nachrichtenart: {raw.get('kind')!r}")


def seal(
    crypto: Crypto,
    message: Challenge | Response,
    recipients: list[str],
    signer: str,
    passphrase: str | None = None,
) -> bytes:
    """Verschluesselt und signiert; ASCII-Armor, damit die Nachricht auch per Copy & Paste reist."""
    return crypto.encrypt(_encode(message), recipients, signer, passphrase, armor=True)


def open_sealed(
    crypto: Crypto, data: bytes, passphrase: str | None = None
) -> tuple[Challenge | Response, SignatureInfo]:
    """Entschluesseln (nur mit vertrauter Signatur, siehe Crypto.decrypt) und pruefen."""
    plain, signer = crypto.decrypt(data, passphrase)
    return parse(plain), signer
