"""Reiter „Empfangen“ ohne Tk: Video/Kanal-Verweis -> Frames -> dekodieren -> entschluesseln -> speichern.

Wie `qrvideo receive`: Klartext erst nach bestandener Signaturpruefung und atomar schreiben. Der Name kommt
seit I27b1 aus dem verschluesselten Paket (`decrypt_with_name`, Threat T1), sonst aus dem Videonamen, beides
ueber `safe_filename`. Weil er erst nach dem Entschluesseln feststeht, wird nie ueberschrieben: ist der Name
belegt, heisst die Datei `name (2).endung`. Ein Verweis (Standard: YouTube-Link) wird ueber den Kanal
(ADR-005, `qrvideo.channel`) in den Ausgabeordner geholt; das Video heisst dann wie im Kanal (YouTube:
Video-ID). Seit I32a traegt die Anfrage Kanal, Kanal-Ordner und Browser-Anmeldung; der Presenter baut den
Kanal erst, wenn er gebraucht wird (eine lokale Datei braucht keinen).
"""

from __future__ import annotations

import itertools
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from qrvideo.channel import Channel, make_channel
from qrvideo.decoder import DecodeReport, decode_frames
from qrvideo.paths import safe_filename
from qrvideo.videoio import outdated_ffmpeg_warning, read_video
from qrvideo.youtube import BROWSERS, parse_browser_spec

from .jobs import Progress
from .keys import KeyService

Frame = npt.NDArray[np.uint8]
Reader = Callable[[Path], Iterator[Frame]]
Decoder = Callable[[Iterable[Frame]], tuple[bytes, DecodeReport]]

PART_SUFFIX = ".part"
# Wie der Kanal im Satz heisst und was ihn verlangt; unbekannte Kanaele fallen auf den Namen zurueck
CHANNEL_LABELS = {"youtube": "YouTube", "folder": "dem Kanal-Ordner"}
SOURCE_ERRORS = {
    "youtube": "Bitte eine Videodatei wählen oder einen YouTube-Link einfügen.",
    "folder": "Bitte eine Videodatei wählen oder einen Dateinamen aus dem Kanal-Ordner eingeben.",
}
FRAME_TEXT = "Frames gelesen:"
BROWSER_ERROR = "Unbekannter Browser „{}“. Erlaubt: {}, optional mit „:Profil“."


@dataclass(frozen=True)
class ReceiveRequest:
    source: str  # Pfad einer Videodatei oder Verweis im Kanal (YouTube-Link/Video-ID, Dateiname im Ordner)
    output_dir: Path
    channel: str = "youtube"  # Name aus `CHANNEL_NAMES` (I32a)
    folder: Path | None = None  # Kanal-Ordner, nur beim Ordner-Kanal
    browser: str = ""  # optional `BROWSER[:PROFIL]` fuer die YouTube-Anmeldung, leer = ohne


@dataclass(frozen=True)
class ReceiveResult:
    target: Path
    size: int
    signer_name: str
    signer_fingerprint: str
    frames: int
    qr_codes: int
    unreadable: int
    downloaded: Path | None = None  # aus dem Kanal geholtes Video
    warning: str | None = None  # z. B. veraltetes gebuendeltes FFmpeg


def _decode(frames: Iterable[Frame]) -> tuple[bytes, DecodeReport]:
    return decode_frames(frames)


def channel_for(request: ReceiveRequest) -> Channel:
    """Kanal aus den Angaben im Reiter; Fehler als deutsche Meldung (die CLI meldet ueber argparse)."""
    cookies = None
    if request.browser.strip():
        try:
            cookies = parse_browser_spec(request.browser)
        except ValueError:
            raise ValueError(BROWSER_ERROR.format(request.browser.strip(), ", ".join(BROWSERS))) from None
    if request.channel == "folder":
        if cookies:
            raise ValueError("Die Browser-Anmeldung gilt nur für YouTube.")
        if request.folder is None or not request.folder.is_dir():
            raise ValueError("Bitte einen vorhandenen Kanal-Ordner wählen.")
    try:
        return make_channel(request.channel, folder=request.folder, cookies_from_browser=cookies)
    except ValueError:
        raise ValueError(f"Unbekannter Kanal „{request.channel}“.") from None


def free_name(target: Path) -> Path:
    """`target` oder, falls belegt, `stem (n).suffix` mit dem kleinsten freien n >= 2."""
    if not target.exists():
        return target
    candidates = (target.with_name(f"{target.stem} ({n}){target.suffix}") for n in itertools.count(2))
    return next(c for c in candidates if not c.exists())


class ReceivePresenter:
    def __init__(
        self,
        keys: KeyService,
        channel: Channel | None = None,
        reader: Reader = read_video,
        decode: Decoder = _decode,
        warning: Callable[[], str | None] = outdated_ffmpeg_warning,
    ) -> None:
        self._keys, self._reader = keys, reader
        self._channel = channel  # fest vorgegeben (Tests); sonst aus der Anfrage
        self._decode, self._warning = decode, warning

    def _source(self, request: ReceiveRequest) -> tuple[Path | str, Channel | None]:
        """Vorhandene Datei oder Verweis im Kanal (mit dem Kanal); sonst ein verstaendlicher Fehler."""
        text = request.source.strip()
        if text and Path(text).is_file():
            return Path(text), None
        channel = self._channel or channel_for(request)
        try:
            return channel.parse_ref(text), channel
        except ValueError:
            fallback = f"Kein gültiger Verweis für den Kanal {channel.name}."
            raise ValueError(SOURCE_ERRORS.get(channel.name, fallback)) from None

    def target_for(self, request: ReceiveRequest) -> Path:
        """Rueckfallname aus dem Video (ohne eingebetteten Namen); prueft zugleich die Eingabe."""
        source, _ = self._source(request)
        stem = Path(source).stem  # Verweis im Ordner-Kanal traegt `.mp4`, eine YouTube-ID nie einen Punkt
        return request.output_dir / safe_filename(stem)

    def run(self, request: ReceiveRequest, progress: Progress) -> ReceiveResult:
        """Laeuft im Hintergrund-Thread. Passphrase: None -> gpg-agent/pinentry fragt selbst."""
        if not request.output_dir.is_dir():
            raise ValueError("Bitte einen vorhandenen Ausgabeordner wählen.")
        source, channel = self._source(request)
        fallback = self.target_for(request)
        warning = self._warning()
        video, downloaded = Path(source), None
        if channel is not None:
            label = CHANNEL_LABELS.get(channel.name, channel.name)
            progress.report(0, None, f"Video wird von {label} geladen …")
            video = downloaded = channel.fetch(str(source), request.output_dir)
        progress.report(0, None, "Frames werden gelesen …")
        data, report = self._decode(progress.count(self._reader(video), None, FRAME_TEXT))
        progress.report(0, None, "Entschlüsseln und Signatur prüfen …")
        plain, signer, name = self._keys.crypto().decrypt_with_name(data, None)
        progress.check()
        # Der eingebettete Name stammt vom Absender: fremde Eingabe, nur als Basisname (Threat T5)
        target = free_name(request.output_dir / safe_filename(name) if name else fallback)
        partial = target.with_name(target.name + PART_SUFFIX)
        partial.write_bytes(plain)
        os.replace(partial, target)
        return ReceiveResult(
            target=target,
            size=len(plain),
            signer_name=signer.username,
            signer_fingerprint=signer.signer_fingerprint,
            frames=report.frames,
            qr_codes=report.qr_codes,
            unreadable=len(report.failures),
            downloaded=downloaded,
            warning=warning,
        )
