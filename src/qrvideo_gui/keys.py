"""Vertraute Schluessel fuer die GUI: Anzeige, Vorbelegung des Signaturschluessels, ein Crypto je Sitzung.

Ohne Tk-Import (ADR-004). `Crypto` (Kernmodul) kennt keine Liste geheimer Schluessel; als eigener
Schluessel gilt deshalb ein ultimativ vertrauter (Ownertrust "u"); GnuPG setzt das fuer selbst erzeugte
Schluessel.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from qrvideo.crypto import KeyInfo, SignatureInfo

OWN_TRUST = "u"
TRUST_TEXT = {OWN_TRUST: "ultimativ (eigener Schlüssel)", "f": "voll"}
NO_NAME = "(ohne Namen)"


class CryptoLike(Protocol):
    """Die Teile von `qrvideo.crypto.Crypto`, die die GUI nutzt (Fakes in den Tests)."""

    def trusted_keys(self) -> list[KeyInfo]: ...

    def encrypt(
        self,
        data: bytes,
        recipients: list[str],
        signer: str,
        passphrase: str | None = None,
        armor: bool = False,
        filename: str | None = None,
    ) -> bytes: ...

    def decrypt(self, data: bytes, passphrase: str | None = None) -> tuple[bytes, SignatureInfo]: ...

    def decrypt_with_name(
        self, data: bytes, passphrase: str | None = None
    ) -> tuple[bytes, SignatureInfo, str | None]: ...


@dataclass(frozen=True)
class KeyRow:
    name: str
    keyid: str
    fingerprint: str
    trust: str
    own: bool


def _row(key: KeyInfo) -> KeyRow:
    return KeyRow(
        name=key.uids[0] if key.uids else NO_NAME,
        keyid=key.keyid,
        fingerprint=key.fingerprint,
        trust=TRUST_TEXT.get(key.ownertrust, key.ownertrust),
        own=key.ownertrust == OWN_TRUST,
    )


def format_fingerprint(fingerprint: str) -> str:
    """In Vierergruppen, wie Kleopatra ihn zeigt - so laesst er sich am Telefon vergleichen."""
    return " ".join(fingerprint[i : i + 4] for i in range(0, len(fingerprint), 4))


def default_signer(rows: list[KeyRow]) -> str | None:
    """Fingerprint des ersten eigenen Schluessels oder None."""
    return next((r.fingerprint for r in rows if r.own), None)


class KeyService:
    """Legt `Crypto` erst bei Bedarf an (gpg wird gesucht) und nur einmal; threadsicher."""

    def __init__(self, factory: Callable[[], CryptoLike]) -> None:
        self._factory = factory
        self._crypto: CryptoLike | None = None
        self._lock = threading.Lock()

    def crypto(self) -> CryptoLike:
        with self._lock:
            if self._crypto is None:
                self._crypto = self._factory()
            return self._crypto

    def rows(self) -> list[KeyRow]:
        """Eigene Schluessel zuerst, danach alphabetisch nach Name."""
        rows = [_row(k) for k in self.crypto().trusted_keys()]
        return sorted(rows, key=lambda r: (not r.own, r.name == NO_NAME, r.name.casefold()))
