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
        print(f"{png}: QR-Code")


def cmd_challenge(args: argparse.Namespace, crypto: CryptoFactory, passphrase: Passphrase) -> None:
    from .handshake import Challenge, seal

    files = tuple(sorted(f.name for f in args.directory.iterdir() if f.is_file()))
    message = Challenge(files, tuple(args.video or ()))
    _write_message(
        args.output, seal(crypto(args), message, args.recipient, args.sign, passphrase()), args.png
    )
    print(f"{args.output}: Challenge mit {len(files)} Dateien und {len(message.videos)} Videos")


def cmd_respond(args: argparse.Namespace, crypto: CryptoFactory, passphrase: Passphrase) -> None:
    from .handshake import Challenge, Response, open_sealed, seal

    session = crypto(args)
    message, signer = open_sealed(session, _read_message(args.challenge), passphrase())
    if not isinstance(message, Challenge):
        raise ValueError("Die Datei enthaelt keine Challenge")
    choices = [*message.files, *message.videos]
    if not 0 <= args.select < len(choices):
        raise ValueError(f"Auswahl {args.select} ausserhalb von 0..{len(choices) - 1}")
    recipients = args.recipient or [signer.signer_fingerprint]
    sealed = seal(session, Response(choices[args.select]), recipients, args.sign, passphrase())
    _write_message(args.output, sealed, args.png)
    print(f"{args.output}: Antwort an {signer.username}: {choices[args.select]}")


def cmd_inspect(args: argparse.Namespace, crypto: CryptoFactory, passphrase: Passphrase) -> None:
    from .handshake import Challenge, open_sealed

    message, signer = open_sealed(crypto(args), _read_message(args.input), passphrase())
    print(f"Signiert von {signer.username} ({signer.signer_fingerprint})")
    if isinstance(message, Challenge):
        for number, entry in enumerate([*message.files, *message.videos]):
            print(f"{number:3d}  {entry}")
    else:
        print(f"Auswahl: {message.selection}")


def add_handshake_parsers(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], crypto: CryptoFactory, passphrase: Passphrase
) -> None:
    p = sub.add_parser("challenge", help="Server Challenge: Dateiangebot verschluesselt fuer Empfaenger")
    p.add_argument("directory", type=Path, help="Ordner mit den angebotenen Dateien")
    p.add_argument("-r", "--recipient", action="append", required=True)
    p.add_argument("--sign", required=True)
    p.add_argument(
        "--video",
        action="append",
        help="bereitgestelltes Video: <kanal>:<verweis> (z. B. folder:<Datei>) oder YouTube-Link, mehrfach",
    )
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--png", type=Path, help="zusaetzlich als QR-Code-Bild speichern")
    p.set_defaults(func=partial(cmd_challenge, crypto=crypto, passphrase=passphrase))

    p = sub.add_parser("respond", help="Client Response: Eintrag aus einer Challenge waehlen")
    p.add_argument("challenge", type=Path)
    p.add_argument("--select", type=int, required=True, help="Nummer aus 'qrvideo inspect'")
    p.add_argument("--sign", required=True)
    p.add_argument("-r", "--recipient", action="append", help="Standard: Absender der Challenge")
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--png", type=Path, help="zusaetzlich als QR-Code-Bild speichern")
    p.set_defaults(func=partial(cmd_respond, crypto=crypto, passphrase=passphrase))

    p = sub.add_parser(
        "inspect", help="Challenge oder Response (.asc oder QR-PNG) entschluesseln und anzeigen"
    )
    p.add_argument("input", type=Path)
    p.set_defaults(func=partial(cmd_inspect, crypto=crypto, passphrase=passphrase))
