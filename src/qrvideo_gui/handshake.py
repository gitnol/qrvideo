"""Reiter „Handshake“ ohne Tk: Challenge erstellen, Nachricht oeffnen (.asc oder QR-PNG), Response speichern.

Gleiche Bausteine wie `qrvideo challenge/respond/inspect` (`qrvideo.handshake.seal/open_sealed`,
`qrvideo.qrpng`). Dateinamen und Video-Verweise aus fremden Nachrichten sind bereits in `handshake.parse`
entschaerft; Videos stehen dort als `<kanal>:<verweis>` (Format v2, ADR-005). Die Response geht an den
Absender der Challenge (wie die CLI ohne `-r`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from qrvideo.channel import channel_ref
from qrvideo.crypto import Crypto
from qrvideo.handshake import Challenge, Response, open_sealed, seal
from qrvideo.qrpng import read_qr_png, write_qr_png

from .jobs import Progress
from .keys import KeyService

MESSAGE_SUFFIX = ".asc"
PNG_SUFFIX = ".png"
PNG_MAGIC = b"\x89PNG"
CHALLENGE, RESPONSE = "challenge", "response"


@dataclass(frozen=True)
class ChallengeRequest:
    directory: Path  # Ordner mit den angebotenen Dateien (nur Namen werden uebertragen)
    videos: tuple[str, ...]  # bereitgestellte Videos: YouTube-Link/-ID oder `<kanal>:<verweis>`
    recipients: tuple[str, ...]
    signer: str
    target: Path  # .asc; mit png=True zusaetzlich <name>.png daneben
    png: bool


@dataclass(frozen=True)
class OpenedMessage:
    path: Path
    kind: str  # CHALLENGE oder RESPONSE
    signer_name: str
    signer_fingerprint: str
    entries: tuple[str, ...] = ()  # Challenge: Dateien, dann Videos
    selection: str | None = None  # Response: gewaehlter Eintrag


@dataclass(frozen=True)
class ResponseRequest:
    message: OpenedMessage
    index: int
    signer: str
    target: Path
    png: bool


@dataclass(frozen=True)
class SealedResult:
    target: Path
    png: Path | None
    summary: str


def _common_problems(recipients: tuple[str, ...], signer: str, target: Path) -> list[str]:
    problems = []
    if not recipients:
        problems.append("Bitte mindestens einen Empfänger ankreuzen.")
    if not signer:
        problems.append("Bitte Ihren eigenen Signaturschlüssel wählen.")
    if target.suffix.lower() != MESSAGE_SUFFIX:
        problems.append(f"Die Nachricht muss auf {MESSAGE_SUFFIX} enden.")
    return problems


def _video_refs(videos: tuple[str, ...]) -> tuple[str, ...]:
    refs = []
    for video in (v.strip() for v in videos):
        if not video:
            continue
        try:
            refs.append(channel_ref(video))
        except ValueError as exc:
            raise ValueError(
                f"„{video}“ ist weder ein YouTube-Link noch ein Verweis wie folder:<Dateiname>."
            ) from exc
    return tuple(refs)


def _read_message(path: Path) -> bytes:
    data = path.read_bytes()
    return read_qr_png(path) if data.startswith(PNG_MAGIC) else data


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


class HandshakePresenter:
    def __init__(self, keys: KeyService) -> None:
        self._keys = keys

    def existing(self, target: Path, png: bool) -> list[Path]:
        """Dateien, die beim Speichern ueberschrieben wuerden (fuer die Rueckfrage)."""
        paths = [target, target.with_suffix(PNG_SUFFIX)] if png else [target]
        return [p for p in paths if p.exists()]

    def _crypto(self) -> Crypto:
        # seal/open_sealed sind auf Crypto typisiert, nutzen aber nur encrypt/decrypt (= CryptoLike)
        return cast(Crypto, self._keys.crypto())

    def _write(self, sealed: bytes, target: Path, png: bool, overwrite: bool) -> Path | None:
        existing = self.existing(target, png)
        if existing and not overwrite:
            raise FileExistsError(17, "Datei existiert", str(existing[0]))
        png_path = target.with_suffix(PNG_SUFFIX) if png else None
        if png_path is not None:
            write_qr_png(
                png_path, sealed
            )  # zuerst: passt die Nachricht nicht in einen QR-Code, bleibt .asc weg
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(sealed)
        os.replace(partial, target)
        return png_path

    def create_challenge(
        self, request: ChallengeRequest, progress: Progress, overwrite: bool = False
    ) -> SealedResult:
        problems = _common_problems(request.recipients, request.signer, request.target)
        if not request.directory.is_dir():
            problems.insert(0, "Bitte den Ordner mit den angebotenen Dateien wählen.")
        if problems:
            raise ValueError(" ".join(problems))
        videos = _video_refs(request.videos)
        files = tuple(sorted(f.name for f in request.directory.iterdir() if f.is_file()))
        progress.report(0, None, "Verschlüsseln und signieren …")
        sealed = seal(
            self._crypto(), Challenge(files, videos), list(request.recipients), request.signer, None
        )
        png = self._write(sealed, request.target, request.png, overwrite)
        summary = (
            f"Gespeichert: {request.target.name}{f' und {png.name}' if png else ''} – Angebot mit "
            f"{_plural(len(files), 'Datei', 'Dateien')} und {_plural(len(videos), 'Video', 'Videos')}."
        )
        return SealedResult(request.target, png, summary)

    def open_message(self, path: Path, progress: Progress) -> OpenedMessage:
        """Entschluesseln nur mit voll vertrauter Signatur (Crypto.decrypt), Inhalt gepruefte Felder."""
        progress.report(0, None, "Entschlüsseln und Signatur prüfen …")
        message, signer = open_sealed(self._crypto(), _read_message(path), None)
        if isinstance(message, Challenge):
            entries = (*message.files, *message.videos)
            return OpenedMessage(path, CHALLENGE, signer.username, signer.signer_fingerprint, entries)
        return OpenedMessage(
            path, RESPONSE, signer.username, signer.signer_fingerprint, selection=message.selection
        )

    def create_response(
        self, request: ResponseRequest, progress: Progress, overwrite: bool = False
    ) -> SealedResult:
        opened = request.message
        if opened.kind != CHALLENGE:
            raise ValueError("Die geöffnete Nachricht ist keine Challenge – darauf gibt es keine Antwort.")
        if not 0 <= request.index < len(opened.entries):
            raise ValueError("Bitte einen Eintrag aus der Liste wählen.")
        problems = _common_problems((opened.signer_fingerprint,), request.signer, request.target)
        if problems:
            raise ValueError(" ".join(problems))
        choice = opened.entries[request.index]
        progress.report(0, None, "Verschlüsseln und signieren …")
        sealed = seal(self._crypto(), Response(choice), [opened.signer_fingerprint], request.signer, None)
        png = self._write(sealed, request.target, request.png, overwrite)
        summary = f"Gespeichert: {request.target.name} – Antwort „{choice}“ an {opened.signer_name}."
        return SealedResult(request.target, png, summary)
