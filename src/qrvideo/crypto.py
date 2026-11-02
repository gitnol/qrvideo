"""GnuPG: verschluesseln und signieren fuer vertraute Empfaenger, entschluesseln nur mit vertrauter Signatur.

Thesis (QRCrypt in POC.py): Binary hart auf "C:\\Program Files (x86)\\GnuPG", Pruefungen per `assert`
(fallen mit `python -O` weg), Klartext wurde vor der Trust-Pruefung auf Platte geschrieben. Hier: Binary aus
Umgebung/PATH, Pruefungen per Exception, Klartext erst nach bestandener Pruefung schreiben.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_to_bytes

import gnupg

from .i18n import _

TRUSTED_OWNERTRUST = ("u", "f")  # ultimate, full
# Threat T1: ohne diese Option stehen die Empfaenger-KeyIDs unverschluesselt in der Nachricht, und jeder mit
# dem Video-Link liest sie (`gpg --list-packets`). Sichtbar bleibt nur die Zahl der Empfaenger.
HIDE_RECIPIENTS = "--throw-keyids"
_PLAINTEXT = re.compile(r"^\[GNUPG:\] PLAINTEXT \S+ \S+ ?(\S*)", re.MULTILINE)


class GpgError(RuntimeError):
    """GnuPG-Aufruf fehlgeschlagen."""


class GpgNotFoundError(GpgError):
    """Kein gpg-Programm gefunden (weder `QRVIDEO_GPG` noch Installation noch PATH)."""


class RecipientsError(GpgError):
    """Keine Empfaenger angegeben oder mindestens einer nicht voll vertraut."""


class EncryptError(GpgError):
    """gpg konnte nicht verschluesseln oder signieren."""


class DecryptError(GpgError):
    """gpg konnte nicht entschluesseln."""


class UntrustedSignatureError(GpgError):
    """Nachricht ist nicht oder nicht von einem vertrauten Schluessel signiert."""


@dataclass(frozen=True)
class KeyInfo:
    keyid: str
    fingerprint: str
    uids: tuple[str, ...]
    ownertrust: str


@dataclass(frozen=True)
class SignatureInfo:
    signer_keyid: str
    signer_fingerprint: str
    username: str


WINDOWS_GPG = (r"C:\Program Files\GnuPG\bin\gpg.exe", r"C:\Program Files (x86)\GnuPG\bin\gpg.exe")


def _is_git_bundled(path: str) -> bool:
    """Git for Windows bringt eine MSYS-gpg mit eigenem Schluesselbund mit; die steht oft zuerst im PATH."""
    return "\\git\\usr\\bin\\" in path.lower().replace("/", "\\")


def find_gpg_binary() -> str:
    """QRVIDEO_GPG, dann GnuPG-Installation unter Windows, dann gpg im PATH (ohne die gpg aus Git)."""
    explicit = os.environ.get("QRVIDEO_GPG")
    if explicit:
        if not Path(explicit).is_file():
            raise GpgError(_("QRVIDEO_GPG does not point to a file: {path}").format(path=explicit))
        return explicit
    on_path = shutil.which("gpg")
    candidates = [
        *(WINDOWS_GPG if os.name == "nt" else ()),
        on_path if on_path and not _is_git_bundled(on_path) else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise GpgNotFoundError(_("gpg not found: install GnuPG or set QRVIDEO_GPG"))


class Crypto:
    def __init__(self, homedir: Path | None = None, binary: str | None = None) -> None:
        self._gpg = gnupg.GPG(
            gpgbinary=binary or find_gpg_binary(), gnupghome=str(homedir) if homedir else None
        )

    def trusted_keys(self) -> list[KeyInfo]:
        """Oeffentliche Schluessel mit Ownertrust full oder ultimate."""
        return [
            KeyInfo(k["keyid"], k["fingerprint"], tuple(k["uids"]), k["ownertrust"])
            for k in self._gpg.list_keys()
            if k["ownertrust"] in TRUSTED_OWNERTRUST
        ]

    def _require_trusted(self, recipients: list[str]) -> None:
        trusted = {v for key in self.trusted_keys() for v in (key.keyid, key.fingerprint)}
        unknown = [r for r in recipients if r.upper() not in trusted]
        if not recipients or unknown:
            missing = unknown or _("none given")
            raise RecipientsError(_("Recipients missing or not trusted: {keys}").format(keys=missing))

    def encrypt(
        self,
        data: bytes,
        recipients: list[str],
        signer: str,
        passphrase: str | None = None,
        armor: bool = False,
        filename: str | None = None,
    ) -> bytes:
        """Fuer alle Empfaenger verschluesseln (Empfaenger verborgen), mit `signer` signieren.

        `filename` reist verschluesselt im Literal-Paket (`--set-filename`), nicht im Video- oder Titelnamen.
        Passphrase sonst ueber gpg-agent.
        """
        self._require_trusted(recipients)
        extra = [HIDE_RECIPIENTS, *(["--set-filename", filename] if filename else [])]
        result = self._gpg.encrypt(
            data, recipients, sign=signer, passphrase=passphrase, armor=armor, extra_args=extra
        )
        if not result.ok:
            raise EncryptError(_("Encryption failed: {status}").format(status=result.status))
        return bytes(result.data)

    def decrypt(self, data: bytes, passphrase: str | None = None) -> tuple[bytes, SignatureInfo]:
        """Entschluesseln; nur mit gueltiger Signatur eines voll vertrauten Schluessels."""
        plain, signer, _name = self.decrypt_with_name(data, passphrase)
        return plain, signer

    def decrypt_with_name(
        self, data: bytes, passphrase: str | None = None
    ) -> tuple[bytes, SignatureInfo, str | None]:
        """Wie `decrypt`, dazu der eingebettete Dateiname (None ohne) - unsanitisiert, also fremde Eingabe."""
        result = self._gpg.decrypt(data, passphrase=passphrase)
        if not result.ok:
            raise DecryptError(_("Decryption failed: {status}").format(status=result.status))
        # python-gnupg ueberschreibt valid/trust_level je Statuszeile; deshalb jede Signatur einzeln pruefen
        # (Code-Review #7). NO_SECKEY betrifft andere Empfaenger einer Nachricht, keine Signatur.
        problems = [p for p in result.problems if p.get("status") != "no secret key"]
        if problems:
            status = problems[0].get("status")
            raise UntrustedSignatureError(_("Signature problem: {status}").format(status=status))
        signatures = list(result.sig_info.values())
        if len(signatures) != 1:
            text = _("Message is not validly signed ({count} signatures)")
            raise UntrustedSignatureError(text.format(count=len(signatures)))
        sig = signatures[0]
        if sig.get("status") != "signature valid" or sig.get("trust_level") is None:
            raise UntrustedSignatureError(_("Message is not validly signed"))
        if sig["trust_level"] < result.TRUST_FULLY:
            text = _("Signing key {keyid} is not fully trusted")
            raise UntrustedSignatureError(text.format(keyid=sig.get("keyid")))
        # Primaerschluessel statt Signatur-Unterschluessel (Code-Review #6)
        fingerprint = sig.get("pubkey_fingerprint") or sig.get("fingerprint")
        signer = SignatureInfo(str(sig.get("keyid")), str(fingerprint), str(sig.get("username")))
        return bytes(result.data), signer, _embedded_name(result.stderr or "")


def _embedded_name(status: str) -> str | None:
    """Dateiname aus der Statuszeile PLAINTEXT.

    gpg schreibt Rohbytes (UTF-8), Sonderzeichen als %XX; python-gnupg dekodiert verlustfrei als latin-1.
    """
    match = _PLAINTEXT.search(status)
    if not match or not match.group(1):
        return None
    return unquote_to_bytes(match.group(1).encode("latin-1")).decode("utf-8", errors="replace")
