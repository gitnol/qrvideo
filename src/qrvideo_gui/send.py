"""Reiter „Senden“ ohne Tk: pruefen, verschluesseln + signieren, Frames rendern, Video schreiben.

Wie `qrvideo send` (keine Zwischendatei, gleicher Standard: Format v3, ECC L, 10 % Paritaet), aber mit
zaehlendem Wrapper um `iter_frames`, damit die Oberflaeche „Frame n von N“ zeigen und abbrechen kann. Die
Gesamtzahl liefert `frame_count`. Bei Abbruch entfernt `write_video` die halbe Datei; der Frame-Generator
wird geschlossen, damit der Prozess-Pool endet.
"""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

import qrcodegenmod as q
from qrvideo.encoder import DEFAULT_ECC, DEFAULT_PARITY_PERCENT, frame_count, iter_frames, parity_symbols
from qrvideo.i18n import N_, _
from qrvideo.videoio import DEFAULT_SETTINGS, VideoSettings, write_video

from .jobs import Progress
from .keys import KeyService

Frame = npt.NDArray[np.uint8]
FrameSource = Callable[[bytes, q.Ecc, int | None, int, int], Iterator[Frame]]  # ..., Version, Paritaet
VideoWriter = Callable[[Path, Iterable[Frame], VideoSettings], int]

VIDEO_SUFFIX = ".mp4"
FRAME_TEXT = N_("Frame")  # Fortschritt „Frame n von N“; uebersetzt beim Gebrauch
YOUTUBE_HINT = N_(
    "Now upload the video in YouTube Studio (studio.youtube.com) and set its visibility to “Unlisted”. "
    "Send the link to the recipient by another route."
)


@dataclass(frozen=True)
class SendRequest:
    source: Path
    recipients: tuple[str, ...]
    signer: str
    target: Path
    ecc: q.Ecc = DEFAULT_ECC
    parity: int | None = parity_symbols(DEFAULT_PARITY_PERCENT)  # None = Format v2


@dataclass(frozen=True)
class SendResult:
    target: Path
    frames: int
    seconds: float  # Laenge des Videos
    elapsed: float  # Dauer des Vorgangs


def suggest_target(source: Path) -> Path:
    """Zielvideo neben der Datei mit neutralem, zufaelligem Namen (Threat T1, seit I27b2).

    Der Videoname landet als Datei- und oft als Titelname im Netz; den Originalnamen erhaelt der Empfaenger
    verschluesselt (`Crypto.encrypt(filename=...)`).
    """
    return source.with_name(f"qrvideo-{secrets.token_hex(4)}{VIDEO_SUFFIX}")


def validate(request: SendRequest) -> list[str]:
    """Verstaendliche Saetze fuer alles, was vor dem Start fehlt; leer = bereit."""
    problems = []
    if not request.source.is_file():
        problems.append(_("Please choose an existing file to send."))
    if not request.recipients:
        problems.append(_("Please tick at least one recipient."))
    if not request.signer:
        problems.append(_("Please choose your own signing key."))
    if request.target.suffix.lower() != VIDEO_SUFFIX:
        problems.append(_("The target video must end in {suffix}.").format(suffix=VIDEO_SUFFIX))
    elif request.source.is_file() and request.target.resolve() == request.source.resolve():
        problems.append(_("The target video must not be the source file."))
    return problems


def _workers() -> int:
    """Einen Kern fuer Oberflaeche und Betriebssystem freilassen."""
    return max(1, (os.cpu_count() or 2) - 1)


class SendPresenter:
    def __init__(
        self,
        keys: KeyService,
        frames: FrameSource = iter_frames,
        writer: VideoWriter = write_video,
        settings: VideoSettings = DEFAULT_SETTINGS,
    ) -> None:
        self._keys, self._frames, self._writer, self._settings = keys, frames, writer, settings

    def needs_overwrite(self, request: SendRequest) -> bool:
        return request.target.exists()

    def run(self, request: SendRequest, progress: Progress, overwrite: bool = False) -> SendResult:
        """Laeuft im Hintergrund-Thread. Passphrase: None -> gpg-agent/pinentry fragt selbst."""
        problems = validate(request)
        if problems:
            raise ValueError(" ".join(problems))
        if request.target.exists() and not overwrite:
            raise FileExistsError(17, _("Target video exists"), str(request.target))
        started = time.monotonic()
        progress.report(0, None, _("Encrypting and signing …"))
        encrypted = self._keys.crypto().encrypt(
            request.source.read_bytes(),
            list(request.recipients),
            request.signer,
            None,
            filename=request.source.name,
        )
        total = frame_count(encrypted, request.ecc, request.parity)
        version = 2 if request.parity is None else 3
        source = self._frames(encrypted, request.ecc, _workers(), version, request.parity or 0)
        try:
            frames = progress.count(source, total, _(FRAME_TEXT))
            count = self._writer(request.target, frames, self._settings)
        finally:
            close = getattr(source, "close", None)  # Generator: beendet den Prozess-Pool auch bei Abbruch
            if close is not None:
                close()
        return SendResult(request.target, count, count / self._settings.fps, time.monotonic() - started)
