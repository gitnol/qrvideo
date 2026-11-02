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
from .i18n import N_, SUPPORTED, _, format_number, resolve_language, set_language
from .paths import safe_filename
from .videoio import VideoSettings, outdated_ffmpeg_warning

if TYPE_CHECKING:
    from .crypto import Crypto

ECC_CHOICES = {"L": q.Ecc.LOW, "M": q.Ecc.MEDIUM, "Q": q.Ecc.QUARTILE, "H": q.Ecc.HIGH}
MAX_PARITY_PERCENT = 50  # mehr Paritaet als Daten lohnt nicht; dann ist ECC Q/H je QR billiger
PASSPHRASE_ENV = "QRVIDEO_PASSPHRASE"  # optional; ohne Variable fragt gpg-agent/pinentry

# Texte von argparse selbst (Kopf der Hilfe, Fehlermeldungen); argparse ruft sein Modul-`_` bei jedem
# Gebrauch auf, deshalb genuegt es, dieses durch unser `_` zu ersetzen. Fehlt ein Text (andere
# Python-Version), bleibt er englisch.
ARGPARSE_TEXTS = (
    N_("usage: "),
    N_("positional arguments"),
    N_("options"),
    N_("show this help message and exit"),
    N_("the following arguments are required: %s"),
    N_("%(prog)s: error: %(message)s\n"),
    N_("unrecognized arguments: %s"),
    N_("argument %(argument_name)s: %(message)s"),
    N_("invalid choice: %(value)r (choose from %(choices)s)"),
    N_("invalid %(type)s value: %(value)r"),
    N_("expected one argument"),
)


def _passphrase() -> str | None:
    return os.environ.get(PASSPHRASE_ENV) or None


def _report(report: DecodeReport) -> None:
    text = _(
        "{frames} frames, {qr} QR codes read, {blank} empty, {corrected} bytes corrected by Reed-Solomon, "
        "{failed} unreadable"
    )
    counts = (
        report.frames,
        report.qr_codes,
        report.blank_slots,
        report.corrected_bytes,
        len(report.failures),
    )
    names = ("frames", "qr", "blank", "corrected", "failed")
    print(text.format(**{n: format_number(c) for n, c in zip(names, counts, strict=True)}), file=sys.stderr)


def _crypto(args: argparse.Namespace) -> Crypto:
    """Import erst bei Bedarf: python-gnupg gehoert zum Extra `crypto`."""
    from .crypto import Crypto

    return Crypto(homedir=args.gnupghome)


def _check_target(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(_("{path} already exists (--force to overwrite)").format(path=path))


def _parity(args: argparse.Namespace) -> int | None:
    return parity_symbols(args.parity)


def _percent(text: str) -> int:
    value = int(text)
    if not 0 <= value <= MAX_PARITY_PERCENT:
        raise argparse.ArgumentTypeError(_("0..{max} expected").format(max=MAX_PARITY_PERCENT))
    return value


def cmd_encode(args: argparse.Namespace) -> None:
    _check_target(args.output, args.force)
    settings = VideoSettings(crf=args.crf, preset=args.preset)
    ecl = ECC_CHOICES[args.ecc]
    frames = encode_file(args.input, args.output, ecl, args.workers, settings, parity=_parity(args))
    _print_video(args.output, frames, settings)


def _print_video(path: Path, frames: int, settings: VideoSettings) -> None:
    text = _("{path}: {frames} frames ({seconds} s)")
    seconds = format_number(frames / settings.fps, 1)
    print(text.format(path=path, frames=format_number(frames), seconds=seconds))


def _warn_ffmpeg() -> None:
    warning = outdated_ffmpeg_warning()
    if warning:
        print(warning, file=sys.stderr)


def cmd_decode(args: argparse.Namespace) -> None:
    _warn_ffmpeg()
    data, report = decode_video(args.input, legacy=args.legacy)
    _report(report)
    args.output.write_bytes(data)
    print(_("{path}: {size} bytes").format(path=args.output, size=format_number(len(data))))


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
    _print_video(args.output, frames, settings)


def cmd_receive(args: argparse.Namespace) -> None:
    _warn_ffmpeg()
    data, report = decode_video(args.input)
    _report(report)
    plain, signer, name = _crypto(args).decrypt_with_name(data, _passphrase())
    # Name kam verschluesselt mit (Threat T1); Rueckfall fuer Videos vor I27a: Name des Videos
    target = args.output / safe_filename(name or args.input.stem) if args.output.is_dir() else args.output
    if target.exists() and not args.force:
        raise FileExistsError(_("{path} already exists (--force to overwrite)").format(path=target))
    target.write_bytes(plain)
    text = _("{path}: {size} bytes, signed by {name} ({fingerprint})")
    size = format_number(len(plain))
    print(text.format(path=target, size=size, name=signer.username, fingerprint=signer.signer_fingerprint))


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
        print(_("Note: {notice}").format(notice=published.notice), file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qrvideo", description=_("Transfer files as a QR code video"))
    parser.add_argument("--gnupghome", type=Path, help=_("own GnuPG keyring (default: the user's)"))
    add_lang_option(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    def video_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--ecc",
            choices=ECC_CHOICES,
            default=DEFAULT_ECC.name[0],
            help=_("error correction per QR code (default L)"),
        )
        p.add_argument("--crf", type=int, default=12, help=_("x264 quality, 0 = lossless (default 12)"))
        p.add_argument("--preset", default="medium")
        p.add_argument("--workers", type=int, help=_("processes for rendering (default: all cores)"))
        p.add_argument("--force", action="store_true", help=_("overwrite an existing target video"))
        p.add_argument(
            "--parity",
            type=_percent,
            default=DEFAULT_PARITY_PERCENT,
            help=_("percent parity QR codes per 10 frames (default 10, format v3); 0 = format v2"),
        )

    p = sub.add_parser("encode", help=_("encode a file (e.g. .gpg) as a video"))
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    video_options(p)
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("decode", help=_("turn a video back into the file"))
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--legacy", action="store_true", help=_("video in the 2019 thesis format"))
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("send", help=_("encrypt, sign and encode as a video"))
    p.add_argument("input", type=Path)
    p.add_argument(
        "-r", "--recipient", action="append", required=True, help=_("key ID/fingerprint, may be repeated")
    )
    p.add_argument("--sign", required=True, help=_("your own signing key"))
    p.add_argument("-o", "--output", type=Path, required=True)
    video_options(p)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("receive", help=_("decode a video, decrypt, check the signature"))
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, default=Path("."))
    p.add_argument("--force", action="store_true", help=_("overwrite an existing target file"))
    p.set_defaults(func=cmd_receive)

    sub.add_parser("keys", help=_("show trusted keys")).set_defaults(func=cmd_keys)

    add_handshake_parsers(sub, _crypto, _passphrase)

    def channel_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--channel", choices=CHANNEL_NAMES, default="youtube", help=_("channel (default youtube)")
        )
        p.add_argument("--folder", type=Path, help=_("shared folder for --channel folder"))

    p = sub.add_parser("download", help=_("fetch a video from the channel (YouTube via yt-dlp, or folder)"))
    p.add_argument("video", help=_("YouTube URL or video ID, or file name in the channel folder"))
    p.add_argument("-d", "--directory", type=Path, default=Path("."))
    channel_options(p)
    p.add_argument(
        "--cookies-from-browser",
        type=_browser,
        metavar=_("BROWSER[:PROFILE]"),
        help=_("use the browser's sign-in, e.g. for private videos (YouTube only, locally via yt-dlp)"),
    )
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("upload", help=_("publish a video (YouTube unlisted, or folder)"))
    p.add_argument("input", type=Path)
    p.add_argument(
        "--client-secrets", type=Path, help=_("OAuth client from the Google Cloud Console (YouTube only)")
    )
    p.add_argument("--title", help=_("YouTube title (default: random)"))
    channel_options(p)
    p.set_defaults(func=cmd_upload)
    return parser


def add_lang_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lang",
        choices=SUPPORTED,
        help=_("language of the output (default: QRVIDEO_LANG, otherwise the system language)"),
    )


def apply_language(argv: Sequence[str] | None) -> None:
    """Sprache vor dem Aufbau des Parsers setzen: auch `--help` und argparse-Fehler sind dann uebersetzt."""
    early = argparse.ArgumentParser(add_help=False)
    early.add_argument("--lang")
    explicit = early.parse_known_args(argv)[0].lang
    set_language(resolve_language(explicit))
    setattr(argparse, "_", _)  # noqa: B010 - Modul-`_` von argparse, siehe ARGPARSE_TEXTS


def main(argv: Sequence[str] | None = None) -> int:
    apply_language(argv)
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ContainerError, ValueError, OSError, RuntimeError) as exc:
        print(_("Error: {error}").format(error=exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(_("Cancelled"), file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
