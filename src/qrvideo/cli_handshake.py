"""Unterbefehle `challenge`, `respond` und `inspect` des Handshakes (ausgelagert aus `cli.py` in I26).

Schluesselbund (`--gnupghome`) und Passphrase gehoeren zur Haupt-CLI; sie kommen als Funktionen herein,
damit dieses Modul `cli` nicht importieren muss.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from .i18n import _

if TYPE_CHECKING:
    from .crypto import Crypto

CryptoFactory = Callable[[argparse.Namespace], "Crypto"]
Passphrase = Callable[[], "str | None"]


def _read_message(path: Path) -> bytes:
    """Handshake-Nachricht aus Text (.asc) oder QR-PNG lesen."""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG"):
        from .qrpng import read_qr_png

        return read_qr_png(path)
    return data


def _write_message(path: Path, sealed: bytes, png: Path | None) -> None:
    path.write_bytes(sealed)
    if png is not None:
        from .qrpng import write_qr_png

        write_qr_png(png, sealed)
        print(_("{path}: QR code").format(path=png))


def cmd_challenge(args: argparse.Namespace, crypto: CryptoFactory, passphrase: Passphrase) -> None:
    from .handshake import Challenge, seal

    files = tuple(sorted(f.name for f in args.directory.iterdir() if f.is_file()))
    message = Challenge(files, tuple(args.video or ()))
    _write_message(
        args.output, seal(crypto(args), message, args.recipient, args.sign, passphrase()), args.png
    )
    text = _("{path}: challenge with {files} files and {videos} videos")
    print(text.format(path=args.output, files=len(files), videos=len(message.videos)))


def cmd_respond(args: argparse.Namespace, crypto: CryptoFactory, passphrase: Passphrase) -> None:
    from .handshake import Challenge, Response, open_sealed, seal

    session = crypto(args)
    message, signer = open_sealed(session, _read_message(args.challenge), passphrase())
    if not isinstance(message, Challenge):
        raise ValueError(_("The file does not contain a challenge"))
    choices = [*message.files, *message.videos]
    if not 0 <= args.select < len(choices):
        text = _("Selection {number} outside 0..{last}")
        raise ValueError(text.format(number=args.select, last=len(choices) - 1))
    recipients = args.recipient or [signer.signer_fingerprint]
    sealed = seal(session, Response(choices[args.select]), recipients, args.sign, passphrase())
    _write_message(args.output, sealed, args.png)
    text = _("{path}: response to {name}: {choice}")
    print(text.format(path=args.output, name=signer.username, choice=choices[args.select]))


def cmd_inspect(args: argparse.Namespace, crypto: CryptoFactory, passphrase: Passphrase) -> None:
    from .handshake import Challenge, open_sealed

    message, signer = open_sealed(crypto(args), _read_message(args.input), passphrase())
    text = _("Signed by {name} ({fingerprint})")
    print(text.format(name=signer.username, fingerprint=signer.signer_fingerprint))
    if isinstance(message, Challenge):
        for number, entry in enumerate([*message.files, *message.videos]):
            print(f"{number:3d}  {entry}")
    else:
        print(_("Selection: {selection}").format(selection=message.selection))


def add_handshake_parsers(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], crypto: CryptoFactory, passphrase: Passphrase
) -> None:
    p = sub.add_parser("challenge", help=_("server challenge: offer of files, encrypted for recipients"))
    p.add_argument("directory", type=Path, help=_("folder with the offered files"))
    p.add_argument("-r", "--recipient", action="append", required=True)
    p.add_argument("--sign", required=True)
    p.add_argument(
        "--video",
        action="append",
        help=_(
            "published video: <channel>:<reference> (e.g. folder:<file>) or YouTube link, may be repeated"
        ),
    )
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--png", type=Path, help=_("also save as a QR code image"))
    p.set_defaults(func=partial(cmd_challenge, crypto=crypto, passphrase=passphrase))

    p = sub.add_parser("respond", help=_("client response: choose an entry from a challenge"))
    p.add_argument("challenge", type=Path)
    p.add_argument("--select", type=int, required=True, help=_("number from 'qrvideo inspect'"))
    p.add_argument("--sign", required=True)
    p.add_argument("-r", "--recipient", action="append", help=_("default: sender of the challenge"))
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--png", type=Path, help=_("also save as a QR code image"))
    p.set_defaults(func=partial(cmd_respond, crypto=crypto, passphrase=passphrase))

    p = sub.add_parser("inspect", help=_("decrypt and show a challenge or response (.asc or QR PNG)"))
    p.add_argument("input", type=Path)
    p.set_defaults(func=partial(cmd_inspect, crypto=crypto, passphrase=passphrase))
