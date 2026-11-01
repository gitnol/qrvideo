"""Kommandozeile `qrvideo` - ersetzt das Konsolenmenue von POC.py durch skriptfaehige Unterbefehle.

Beispiele:
  qrvideo send bericht.xlsx -r <KeyID> --sign <KeyID> -o bericht.mp4
  qrvideo receive bericht.mp4 -o .
  qrvideo download https://youtu.be/<ID> -d eingang
  qrvideo upload bericht.mp4 --channel folder --folder //server/austausch
  qrvideo decode altes_thesis_video.mp4 -o alt.pgp --legacy
  qrvideo challenge angebot/ -r <KeyID> --sign <KeyID> -o challenge.asc
  qrvideo respond challenge.asc --select 0 --sign <KeyID> -o response.asc
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import qrcodegenmod as q

from .channel import CHANNEL_NAMES, Channel, make_channel
from .cli_handshake import add_handshake_parsers
from .decoder import DecodeReport, decode_video
from .encoder import DEFAULT_ECC, DEFAULT_PARITY_PERCENT, encode_bytes, encode_file, parity_symbols
from .errors import ContainerError
from .paths import safe_filename
from .videoio import VideoSettings, outdated_ffmpeg_warning

if TYPE_CHECKING:
    from .crypto import Crypto

ECC_CHOICES = {"L": q.Ecc.LOW, "M": q.Ecc.MEDIUM, "Q": q.Ecc.QUARTILE, "H": q.Ecc.HIGH}
MAX_PARITY_PERCENT = 50  # mehr Paritaet als Daten lohnt nicht; dann ist ECC Q/H je QR billiger
PASSPHRASE_ENV = "QRVIDEO_PASSPHRASE"  # optional; ohne Variable fragt gpg-agent/pinentry


def _passphrase() -> str | None:
    return os.environ.get(PASSPHRASE_ENV) or None


def _report(report: DecodeReport) -> None:
    print(
        f"{report.frames} Frames, {report.qr_codes} QR-Codes gelesen, {report.blank_slots} leer, "
        f"{report.corrected_bytes} Bytes per Reed-Solomon korrigiert, {len(report.failures)} unlesbar",
        file=sys.stderr,
    )


def _crypto(args: argparse.Namespace) -> Crypto:
    """Import erst bei Bedarf: python-gnupg gehoert zum Extra `crypto`."""
    from .crypto import Crypto

    return Crypto(homedir=args.gnupghome)


def _check_target(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} existiert bereits (--force zum Ueberschreiben)")


def _parity(args: argparse.Namespace) -> int | None:
    return parity_symbols(args.parity)


def _percent(text: str) -> int:
    value = int(text)
    if not 0 <= value <= MAX_PARITY_PERCENT:
        raise argparse.ArgumentTypeError(f"0..{MAX_PARITY_PERCENT} erwartet")
    return value


def cmd_encode(args: argparse.Namespace) -> None:
    _check_target(args.output, args.force)
    settings = VideoSettings(crf=args.crf, preset=args.preset)
    ecl = ECC_CHOICES[args.ecc]
    frames = encode_file(args.input, args.output, ecl, args.workers, settings, parity=_parity(args))
    print(f"{args.output}: {frames} Frames ({frames / settings.fps:.1f} s)")


def _warn_ffmpeg() -> None:
    warning = outdated_ffmpeg_warning()
    if warning:
        print(warning, file=sys.stderr)


def cmd_decode(args: argparse.Namespace) -> None:
    _warn_ffmpeg()
    data, report = decode_video(args.input, legacy=args.legacy)
    _report(report)
    args.output.write_bytes(data)
    print(f"{args.output}: {len(data)} Bytes")


def cmd_send(args: argparse.Namespace) -> None:
    """Verschluesseln und direkt kodieren - keine Zwischendatei, die eine Eingabe ueberschreiben koennte."""
    _check_target(args.output, args.force)
    encrypted = _crypto(args).encrypt(
        args.input.read_bytes(), args.recipient, args.sign, _passphrase(), filename=args.input.name
    )
    settings = VideoSettings(crf=args.crf, preset=args.preset)
    frames = encode_bytes(
        encrypted, args.output, ECC_CHOICES[args.ecc], args.workers, settings, parity=_parity(args)
    )
    print(f"{args.output}: {frames} Frames ({frames / settings.fps:.1f} s)")


def cmd_receive(args: argparse.Namespace) -> None:
    _warn_ffmpeg()
    data, report = decode_video(args.input)
    _report(report)
    plain, signer, name = _crypto(args).decrypt_with_name(data, _passphrase())
    # Name kam verschluesselt mit (Threat T1); Rueckfall fuer Videos vor I27a: Name des Videos
    target = args.output / safe_filename(name or args.input.stem) if args.output.is_dir() else args.output
    if target.exists() and not args.force:
        raise FileExistsError(f"{target} existiert bereits (--force zum Ueberschreiben)")
    target.write_bytes(plain)
    print(f"{target}: {len(plain)} Bytes, signiert von {signer.username} ({signer.signer_fingerprint})")


def cmd_keys(args: argparse.Namespace) -> None:
    for key in _crypto(args).trusted_keys():
        print(f"{key.keyid}  {key.fingerprint}  {key.ownertrust}  {'; '.join(key.uids)}")


def _browser(text: str) -> tuple[str, ...]:
    from .youtube import parse_browser_spec

    try:
        return parse_browser_spec(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _channel(args: argparse.Namespace) -> Channel:
    """Kanal aus `--channel`/`--folder`/`--client-secrets` (ADR-005)."""
    secrets_file = getattr(args, "client_secrets", None)  # nur `upload` kennt die Option
    cookies = getattr(args, "cookies_from_browser", None)  # nur `download`
    return make_channel(
        args.channel, folder=args.folder, client_secrets=secrets_file, cookies_from_browser=cookies
    )


def cmd_download(args: argparse.Namespace) -> None:
    channel = _channel(args)
    print(channel.fetch(channel.parse_ref(args.video), args.directory))


def cmd_upload(args: argparse.Namespace) -> None:
    # Threat T1: nie der Dateiname als Titel - ohne --title ein neutraler, zufaelliger Titel
    title = args.title or f"qrvideo {secrets.token_hex(4)}"
    channel = _channel(args)
    published = channel.publish(args.input, safe_filename(title))
    print(channel.display(published.ref))
    if published.notice:
        print(f"Hinweis: {published.notice}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qrvideo", description="Dateien als QR-Code-Video uebertragen")
    parser.add_argument(
        "--gnupghome", type=Path, help="eigener GnuPG-Schluesselbund (Standard: der des Nutzers)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def video_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--ecc",
            choices=ECC_CHOICES,
            default=DEFAULT_ECC.name[0],
            help="Fehlerkorrektur je QR-Code (Standard L)",
        )
        p.add_argument("--crf", type=int, default=12, help="x264-Qualitaet, 0 = verlustfrei (Standard 12)")
        p.add_argument("--preset", default="medium")
        p.add_argument("--workers", type=int, help="Prozesse fuer das Rendern (Standard: alle Kerne)")
        p.add_argument("--force", action="store_true", help="vorhandenes Zielvideo ueberschreiben")
        p.add_argument(
            "--parity",
            type=_percent,
            default=DEFAULT_PARITY_PERCENT,
            help="Prozent Paritaets-QR je 10 Frames (Standard 10, Format v3); 0 = Format v2 wie vor I18",
        )

    p = sub.add_parser("encode", help="Datei (z. B. .gpg) als Video kodieren")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    video_options(p)
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("decode", help="Video zur Datei zurueckwandeln")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--legacy", action="store_true", help="Video im Thesis-Format von 2019")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("send", help="verschluesseln, signieren und als Video kodieren")
    p.add_argument("input", type=Path)
    p.add_argument(
        "-r", "--recipient", action="append", required=True, help="KeyID/Fingerprint, mehrfach moeglich"
    )
    p.add_argument("--sign", required=True, help="eigener Signaturschluessel")
    p.add_argument("-o", "--output", type=Path, required=True)
    video_options(p)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("receive", help="Video dekodieren, entschluesseln, Signatur pruefen")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, default=Path("."))
    p.add_argument("--force", action="store_true", help="vorhandene Zieldatei ueberschreiben")
    p.set_defaults(func=cmd_receive)

    sub.add_parser("keys", help="vertraute Schluessel anzeigen").set_defaults(func=cmd_keys)

    add_handshake_parsers(sub, _crypto, _passphrase)

    def channel_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--channel", choices=CHANNEL_NAMES, default="youtube", help="Kanal (Standard youtube)")
        p.add_argument("--folder", type=Path, help="gemeinsamer Ordner fuer --channel folder")

    p = sub.add_parser("download", help="Video aus dem Kanal holen (YouTube per yt-dlp oder Ordner)")
    p.add_argument("video", help="YouTube-URL oder Video-ID bzw. Dateiname im Kanal-Ordner")
    p.add_argument("-d", "--directory", type=Path, default=Path("."))
    channel_options(p)
    p.add_argument(
        "--cookies-from-browser",
        type=_browser,
        metavar="BROWSER[:PROFIL]",
        help="Anmeldung des Browsers nutzen, z. B. fuer private Videos (nur YouTube, lokal per yt-dlp)",
    )
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("upload", help="Video bereitstellen (YouTube nicht gelistet oder Ordner)")
    p.add_argument("input", type=Path)
    p.add_argument("--client-secrets", type=Path, help="OAuth-Client der Google Cloud Console (nur YouTube)")
    p.add_argument("--title", help="YouTube-Titel (Standard: zufaellig)")
    channel_options(p)
    p.set_defaults(func=cmd_upload)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ContainerError, ValueError, OSError, RuntimeError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Abgebrochen", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
