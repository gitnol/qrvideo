"""Kanaele fuer das fertige Video (ADR-005): bereitstellen, abholen, Verweis erkennen und anzeigen.

YouTube ist der Standardkanal (`qrvideo.youtube`); der Ordner-Kanal legt Videos in einem gemeinsamen Ordner
ab, z. B. einem Sync-Ordner, den Sender und Empfaenger teilen. CLI und GUI kennen nur das Protokoll `Channel`.
"""

from __future__ import annotations

import os
import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import youtube
from .i18n import N_, _
from .paths import safe_filename

CHANNEL_NAMES = ("youtube", "folder")
PART_SUFFIX = ".part"
NAME_TRIES = 16


@dataclass(frozen=True)
class Published:
    """Ergebnis von `publish`: Verweis und ein Hinweis nur zu genau diesem Bereitstellen (seit I31)."""

    ref: str
    notice: str | None = None  # z. B. abweichende Sichtbarkeit bei YouTube


class Channel(Protocol):
    name: str

    def parse_ref(self, text: str) -> str:
        """Verweis auf ein Video in diesem Kanal; ValueError, wenn der Text keiner ist."""
        ...

    def fetch(self, ref: str, target_dir: Path) -> Path:
        """Holt das Video nach target_dir und gibt den Pfad zurueck."""
        ...

    def publish(self, video: Path, title: str) -> Published:
        """Stellt das Video bereit; das Ergebnis traegt den Verweis und ggf. einen Hinweis."""
        ...

    def display(self, ref: str) -> str:
        """Verweis so, wie ihn der Empfaenger eingibt."""
        ...


class YouTubeChannel:
    """Standardkanal: Verweis = Video-ID. Upload nur mit OAuth-Client, sonst per Hand in YouTube Studio."""

    name = "youtube"

    def __init__(
        self,
        client_secrets: Path | None = None,
        ydl_class: Any = None,
        cookies_from_browser: tuple[str, ...] | None = None,
    ) -> None:
        self._client_secrets, self._ydl_class = client_secrets, ydl_class
        self._cookies = cookies_from_browser

    def parse_ref(self, text: str) -> str:
        return youtube.parse_video_id(text)

    def fetch(self, ref: str, target_dir: Path) -> Path:
        return youtube.download(
            ref, target_dir, ydl_class=self._ydl_class, cookies_from_browser=self._cookies
        )

    def publish(self, video: Path, title: str) -> Published:
        if self._client_secrets is None:
            raise ValueError(_("Uploading to YouTube needs --client-secrets (OAuth client, Google Cloud)"))
        uploaded = youtube.upload(video, title, self._client_secrets)
        return Published(uploaded.video_id, _visibility_notice(uploaded))

    def display(self, ref: str) -> str:
        return f"https://youtu.be/{ref}"


class FolderChannel:
    """Gemeinsamer Ordner: Verweis = Dateiname in `root`, nie ein Pfad (Threat T5); Namen neutral (T1)."""

    name = "folder"

    def __init__(self, root: Path) -> None:
        self.root = root

    def parse_ref(self, text: str) -> str:
        return _folder_name(text)

    def fetch(self, ref: str, target_dir: Path) -> Path:
        source = self.root / self.parse_ref(ref)
        if not source.is_file():
            raise FileNotFoundError(_("Not in the channel folder: {path}").format(path=source))
        target = target_dir / source.name
        if target.exists() and target.resolve() == source.resolve():
            return target
        if target.exists():
            raise FileExistsError(_("{path} already exists").format(path=target))
        target_dir.mkdir(parents=True, exist_ok=True)
        _copy_atomic(source, target)
        return target

    def publish(self, video: Path, title: str) -> Published:
        """Der Titel bleibt unbenutzt: ein Ordner kennt nur Dateinamen, und die sind zufaellig."""
        if not self.root.is_dir():
            raise ValueError(_("Channel folder missing: {path}").format(path=self.root))
        for _attempt in range(NAME_TRIES):  # begrenzt: nie endlos, auch wenn der Ordner sonderbar antwortet
            target = self.root / f"qrvideo-{secrets.token_hex(4)}.mp4"
            if not target.exists():
                _copy_atomic(video, target)
                return Published(target.name)
        raise FileExistsError(_("No free name in the channel folder {path}").format(path=self.root))

    def display(self, ref: str) -> str:
        return ref


def _visibility_notice(uploaded: youtube.Uploaded) -> str | None:
    """Nur wenn YouTube sicher anders entschieden hat; ohne Status in der Antwort kein geratener Hinweis."""
    if uploaded.privacy in (None, youtube.WANTED_PRIVACY):
        return None
    text = _(
        'YouTube saved the video as "{privacy}" (usual for unverified API projects). Release it in '
        "YouTube Studio or fetch it with an authorised account: "
        "qrvideo download <ID> --cookies-from-browser <browser>"
    )
    privacy = uploaded.privacy
    return text.format(privacy=_(_PRIVACY_TEXT[privacy]) if privacy in _PRIVACY_TEXT else privacy)


_PRIVACY_TEXT = {"private": N_("private"), "public": N_("public")}


def _copy_atomic(source: Path, target: Path) -> None:
    """Erst `.part`, dann umbenennen: ein abgebrochener Kopiervorgang hinterlaesst nie ein halbes Video."""
    partial = target.with_name(target.name + PART_SUFFIX)
    try:
        shutil.copyfile(source, partial)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def make_channel(
    name: str,
    *,
    folder: Path | None = None,
    client_secrets: Path | None = None,
    cookies_from_browser: tuple[str, ...] | None = None,
) -> Channel:
    """Kanal nach Namen (`CHANNEL_NAMES`), wie ihn CLI-Option `--channel` liefert."""
    if name == "youtube":
        return YouTubeChannel(client_secrets, cookies_from_browser=cookies_from_browser)
    if cookies_from_browser:
        raise ValueError(_("--cookies-from-browser only applies to YouTube"))
    if name == "folder":
        if folder is None:
            raise ValueError(_("The folder channel needs --folder"))
        return FolderChannel(folder)
    text = _("Unknown channel {name!r} (allowed: {names})")
    raise ValueError(text.format(name=name, names=", ".join(CHANNEL_NAMES)))


def _folder_name(text: str) -> str:
    name = text.strip()
    if not name or safe_filename(name) != name:
        raise ValueError(_("Not a file name in the channel folder: {text!r}").format(text=text))
    return name


# Verweise pruefen, ohne einen Kanal zu oeffnen (Handshake: der Kanal-Ordner des Absenders ist hier unbekannt)
_REF_PARSERS: dict[str, Callable[[str], str]] = {"youtube": youtube.parse_video_id, "folder": _folder_name}


def parse_channel_ref(text: str) -> tuple[str, str]:
    """Streng, fuer empfangene Nachrichten: `<kanal>:<verweis>`; den Verweis prueft der genannte Kanal."""
    name, sep, ref = text.strip().partition(":")
    parser = _REF_PARSERS.get(name) if sep else None
    if parser is None:
        names = ", ".join(CHANNEL_NAMES)
        message = _("Not a reference of the form <channel>:<reference> (channel: {names}): {text!r}")
        raise ValueError(message.format(names=names, text=text))
    return name, parser(ref)


def channel_ref(text: str) -> str:
    """Nutzereingabe: `<kanal>:<verweis>` oder wie bis I29b ein YouTube-Link bzw. eine Video-ID."""
    if text.strip().partition(":")[0] in _REF_PARSERS:
        name, ref = parse_channel_ref(text)
    else:
        name, ref = "youtube", youtube.parse_video_id(text)
    return f"{name}:{ref}"
