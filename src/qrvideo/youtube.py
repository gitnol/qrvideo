"""YouTube als Kanal: Video-ID erkennen, Download per yt-dlp, Upload per YouTube Data API v3.

Thesis: youtube_dl (tot) mit Format 137 und oauth2client (veraltet) mit Token im Programmordner.
Sicherheit (DEPENDENCY_AUDIT 2026-10-26): yt-dlp >= 2026.7.4, keine Link-Dateien, kein aria2c, kein netrc_cmd.
Browser-Cookies (seit I30a) nur auf ausdruecklichen Wunsch: yt-dlp liest sie lokal fuer diesen einen Abruf,
`qrvideo` speichert sie nicht (Threat T7).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .i18n import _

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_URL_PATTERNS = (
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"[?&]v=([A-Za-z0-9_-]{11})"),
    re.compile(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})"),
)
# 1080p und 30 fps sind Pflicht, weil die Frame-Geometrie fest ist; avc1 wie Format 137 der Thesis bevorzugt
FORMAT = "bv*[height=1080][fps<=30][vcodec^=avc1]/bv*[height=1080][fps<=30]"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
WANTED_PRIVACY = "unlisted"  # Standard von `upload` (nicht gelistet)
# wie yt_dlp.cookies.SUPPORTED_BROWSERS (Test haelt beide gleich); hier ohne yt-dlp-Import pruefbar
BROWSERS = ("brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale")
_CONTROL = re.compile(r"[\x00-\x1f]")


def parse_browser_spec(text: str) -> tuple[str, ...]:
    """`BROWSER[:PROFIL]` -> Tupel fuer yt-dlps `cookiesfrombrowser`; das Profil darf ein Pfad sein."""
    browser, sep, profile = text.strip().partition(":")
    browser = browser.lower()
    if browser not in BROWSERS or (sep and not profile.strip()) or _CONTROL.search(profile):
        message = _("Unknown browser or invalid profile {text!r} (browsers: {names})")
        raise ValueError(message.format(text=text, names=", ".join(BROWSERS)))
    return (browser, profile.strip()) if sep else (browser,)


def parse_video_id(text: str) -> str:
    """YouTube-ID aus URL oder nackter ID; ValueError, wenn nichts Eindeutiges gefunden wird."""
    text = text.strip()
    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    if VIDEO_ID.fullmatch(text):
        return text
    raise ValueError(_("No YouTube video ID recognised: {text!r}").format(text=text))


def download(
    video: str, target_dir: Path, ydl_class: Any = None, cookies_from_browser: tuple[str, ...] | None = None
) -> Path:
    """Laedt nur die Videospur in 1080p nach target_dir/<id>.<ext> und gibt den Pfad zurueck."""
    if ydl_class is None:
        from yt_dlp import YoutubeDL

        ydl_class = YoutubeDL
    video_id = parse_video_id(video)
    target_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "format": FORMAT,
        "paths": {"home": str(target_dir)},  # nicht im Template: ein "%" im Pfad waere dort Platzhalter
        "outtmpl": "%(id)s.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
    }
    if cookies_from_browser:  # angemeldetes Konto, z. B. fuer private Videos (I30a)
        options["cookiesfrombrowser"] = cookies_from_browser
    with ydl_class(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.is_file():
        raise FileNotFoundError(_("The download produced no file: {path}").format(path=path))
    return path


@dataclass(frozen=True)
class Uploaded:
    """Ergebnis des Uploads; `privacy` ist, was YouTube gespeichert hat (None: Antwort ohne Status)."""

    video_id: str
    privacy: str | None


def default_token_path() -> Path:
    """OAuth-Token ausserhalb des Programmordners (Thesis: *-oauth2.json neben dem Code)."""
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "qrvideo" / "youtube-token.json"


def upload(
    video: Path,
    title: str,
    client_secrets: Path,
    description: str = "",
    privacy: str = WANTED_PRIVACY,
    token_path: Path | None = None,
) -> Uploaded:
    """Laedt das Video hoch (Standard: nicht gelistet); nicht verifizierte Projekte landen auf „privat“."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_path = token_path or default_token_path()
    creds = (
        Credentials.from_authorized_user_file(str(token_path), [UPLOAD_SCOPE])  # type: ignore[no-untyped-call]
        if token_path.is_file()
        else None
    )
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:  # widerrufen oder abgelaufen: neu anmelden (Code-Review #12)
            creds = None
    if not creds or not creds.valid:
        creds = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets), [UPLOAD_SCOPE]
        ).run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")  # auch nach einem Refresh speichern

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title, "description": description, "categoryId": "28"},
        "status": {"privacyStatus": privacy},
    }
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _progress, response = request.next_chunk(num_retries=5)
    status = response.get("status") or {}
    return Uploaded(str(response["id"]), status.get("privacyStatus"))
