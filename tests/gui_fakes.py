"""Gemeinsame Attrappen der GUI-Tests: Schlüssel, Fake-Crypto, Tk-Ereignisse abarbeiten."""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable

from qrvideo.crypto import KeyInfo, SignatureInfo, UntrustedSignatureError

ALICE = KeyInfo("AAAA1111", "A" * 40, ("Alice <alice@example.test>",), "u")
BOB = KeyInfo("BBBB2222", "B" * 40, ("Bob <bob@example.test>",), "f")
NAMELESS = KeyInfo("CCCC3333", "C" * 40, (), "f")


class FakeCrypto:
    """Verschlüsseln = Präfix voranstellen; merkt sich die Aufrufe. Entschlüsseln liefert `signer`."""

    PREFIX = b"PGP:"

    def __init__(self, keys: list[KeyInfo], signer: SignatureInfo | None = None) -> None:
        self.keys = keys
        self.signer = signer
        self.encrypted: list[tuple[list[str], str, str | None, bool]] = []
        self.embedded_name: str | None = None  # Name im verschluesselten Paket (I27a)

    def trusted_keys(self) -> list[KeyInfo]:
        return list(self.keys)

    def encrypt(
        self,
        data: bytes,
        recipients: list[str],
        signer: str,
        passphrase: str | None = None,
        armor: bool = False,
        filename: str | None = None,
    ) -> bytes:
        self.encrypted.append((list(recipients), signer, passphrase, armor))
        self.embedded_name = filename
        return self.PREFIX + data

    def decrypt(self, data: bytes, passphrase: str | None = None) -> tuple[bytes, SignatureInfo]:
        if self.signer is None or not data.startswith(self.PREFIX):
            raise UntrustedSignatureError("Nachricht ist nicht gueltig signiert")
        return data[len(self.PREFIX) :], self.signer

    def decrypt_with_name(
        self, data: bytes, passphrase: str | None = None
    ) -> tuple[bytes, SignatureInfo, str | None]:
        plain, signer = self.decrypt(data, passphrase)
        return plain, signer, self.embedded_name


def pump(root: tk.Misc, until: Callable[[], bool], timeout_ms: int = 5000) -> None:
    """Tk-Ereignisse abarbeiten, bis `until()` wahr ist (Hintergrund-Jobs melden sich per after())."""
    for _ in range(timeout_ms // 20):
        root.update()
        if until():
            return
        time.sleep(0.02)
    raise AssertionError("Bedingung nicht erreicht")
