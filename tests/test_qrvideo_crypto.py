"""GnuPG mit temporaerem Schluesselbund: Vertrauen, Signaturpruefung, Ende-zu-Ende ueber ein Video."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import gnupg
import pytest

from qrvideo.cli import main
from qrvideo.crypto import (
    Crypto,
    DecryptError,
    EncryptError,
    GpgError,
    RecipientsError,
    UntrustedSignatureError,
    find_gpg_binary,
)

pytestmark = pytest.mark.integration


@dataclass
class Keyring:
    home: Path
    crypto: Crypto
    alice: str  # Absender, vertraut
    bob: str  # Empfaenger, vertraut
    mallory: str  # nur oeffentlicher Schluessel vorhanden, nicht vertraut
    mallory_gpg: gnupg.GPG  # Mallorys eigener Schluesselbund (dort kennt sie Bobs oeffentlichen Schluessel)


def _new_key(gpg: gnupg.GPG, name: str) -> str:
    params = gpg.gen_key_input(
        key_type="EDDSA",
        key_curve="ed25519",
        subkey_type="ECDH",
        subkey_curve="cv25519",
        name_real=name,
        name_email=f"{name.lower()}@example.test",
        no_protection=True,
    )
    return str(gpg.gen_key(params).fingerprint)


@pytest.fixture(scope="module")
def keyring(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Keyring]:
    try:
        binary = find_gpg_binary()
    except GpgError:
        pytest.skip("GnuPG nicht installiert")
    home = tmp_path_factory.mktemp("gnupg")
    foreign = tmp_path_factory.mktemp("gnupg_mallory")
    gpg = gnupg.GPG(gpgbinary=binary, gnupghome=str(home))
    alice, bob = (
        _new_key(gpg, "Alice"),
        _new_key(gpg, "Bob"),
    )  # eigene Schluessel: GnuPG vertraut ihnen ultimativ
    mallory_gpg = gnupg.GPG(gpgbinary=binary, gnupghome=str(foreign))
    mallory = _new_key(mallory_gpg, "Mallory")
    gpg.import_keys(mallory_gpg.export_keys(mallory))
    mallory_gpg.import_keys(gpg.export_keys(bob))
    yield Keyring(home, Crypto(homedir=home, binary=binary), alice, bob, mallory, mallory_gpg)
    gpgconf = Path(binary).with_name("gpgconf.exe" if binary.endswith(".exe") else "gpgconf")
    for h in (home, foreign):
        subprocess.run([str(gpgconf), "--homedir", str(h), "--kill", "all"], check=False, capture_output=True)


def test_trusted_keys(keyring: Keyring) -> None:
    trusted = {k.fingerprint for k in keyring.crypto.trusted_keys()}
    assert trusted == {keyring.alice, keyring.bob}


def test_encrypt_decrypt_roundtrip(keyring: Keyring) -> None:
    secret = b"Bachelorarbeit 2019 \x00\xff"
    encrypted = keyring.crypto.encrypt(secret, [keyring.bob], keyring.alice)
    assert secret not in encrypted
    plain, signer = keyring.crypto.decrypt(encrypted)
    assert plain == secret
    assert signer.signer_fingerprint == keyring.alice


def test_untrusted_recipient_is_refused(keyring: Keyring) -> None:
    with pytest.raises(RecipientsError):
        keyring.crypto.encrypt(b"x", [keyring.mallory], keyring.alice)
    with pytest.raises(RecipientsError):
        keyring.crypto.encrypt(b"x", [], keyring.alice)


def test_failed_gpg_encryption_is_an_encrypt_error(keyring: Keyring, monkeypatch: pytest.MonkeyPatch) -> None:
    # gpg zum Scheitern zu bringen ist unzuverlaessig (fehlt der Signaturschluessel, nimmt gpg einen anderen,
    # KNOWN_ISSUES); der GUI-Hinweis haengt nur an der Klasse
    failed = type("Result", (), {"ok": False, "status": "signing failed", "data": b""})()
    monkeypatch.setattr(keyring.crypto._gpg, "encrypt", lambda *args, **kwargs: failed)
    with pytest.raises(EncryptError, match="signing failed"):
        keyring.crypto.encrypt(b"x", [keyring.bob], keyring.alice)


def test_untrusted_or_missing_signature_is_refused(keyring: Keyring) -> None:
    raw = gnupg.GPG(gpgbinary=find_gpg_binary(), gnupghome=str(keyring.home))
    by_mallory = keyring.mallory_gpg.encrypt(
        b"x", [keyring.bob], sign=keyring.mallory, always_trust=True, armor=False
    ).data
    assert by_mallory
    with pytest.raises(UntrustedSignatureError, match="nicht voll vertraut"):
        keyring.crypto.decrypt(by_mallory)
    unsigned = raw.encrypt(b"x", [keyring.bob], armor=False).data
    with pytest.raises(UntrustedSignatureError, match="nicht gültig signiert"):
        keyring.crypto.decrypt(unsigned)
    with pytest.raises(DecryptError):
        keyring.crypto.decrypt(b"kein PGP")


def test_cli_send_and_receive(keyring: Keyring, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "bericht.xlsx"
    source.write_bytes(bytes(range(256)) * 300)
    video = tmp_path / "bericht.mp4"
    home = ["--gnupghome", str(keyring.home)]
    send = [
        "send",
        str(source),
        "-r",
        keyring.bob,
        "--sign",
        keyring.alice,
        "-o",
        str(video),
        "--workers",
        "1",
    ]
    assert main([*home, *send]) == 0
    out_dir = tmp_path / "eingang"
    out_dir.mkdir()
    assert main([*home, "receive", str(video), "-o", str(out_dir)]) == 0
    assert (
        out_dir / "bericht.xlsx"
    ).read_bytes() == source.read_bytes()  # Name kam verschluesselt mit (I27a)
    assert "signiert von Alice" in capsys.readouterr().out
    assert main([*home, "receive", str(video), "-o", str(out_dir)]) == 1  # vorhandene Datei bleibt
    assert "existiert bereits" in capsys.readouterr().err
    assert main([*home, "receive", str(video), "-o", str(out_dir), "--force"]) == 0
    assert main([*home, "keys"]) == 0


def test_handshake_challenge_respond_inspect(
    keyring: Keyring, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Thesis-Ablauf: Server bietet an, Client waehlt, Server liest die Antwort (ein Schluesselbund)."""
    offer = tmp_path / "angebot"
    offer.mkdir()
    for name in ("bericht.xlsx", "video.mp4"):
        (offer / name).write_bytes(b"x")
    home = ["--gnupghome", str(keyring.home)]
    challenge, response = tmp_path / "challenge.asc", tmp_path / "response.asc"
    args = ["challenge", str(offer), "-r", keyring.bob, "--sign", keyring.alice, "--video", "AbCdEfGhIjK"]
    args += ["--video", "folder:qrvideo-0123abcd.mp4"]  # Kanal-Verweis, seit I29c1
    assert main([*home, *args, "-o", str(challenge)]) == 0
    assert challenge.read_bytes().startswith(b"-----BEGIN PGP MESSAGE-----")
    assert main([*home, "inspect", str(challenge)]) == 0
    listing = capsys.readouterr().out
    assert "0  bericht.xlsx" in listing and "2  youtube:AbCdEfGhIjK" in listing
    assert "3  folder:qrvideo-0123abcd.mp4" in listing
    assert (
        main([*home, "respond", str(challenge), "--select", "0", "--sign", keyring.bob, "-o", str(response)])
        == 0
    )
    assert main([*home, "inspect", str(response)]) == 0
    assert "Auswahl: bericht.xlsx" in capsys.readouterr().out
    assert (
        main([*home, "respond", str(challenge), "--select", "3", "--sign", keyring.bob, "-o", str(response)])
        == 0
    )
    assert main([*home, "inspect", str(response)]) == 0
    assert "Auswahl: folder:qrvideo-0123abcd.mp4" in capsys.readouterr().out
    assert (
        main([*home, "respond", str(challenge), "--select", "9", "--sign", keyring.bob, "-o", str(response)])
        == 1
    )
    assert (
        main([*home, "respond", str(response), "--select", "0", "--sign", keyring.bob, "-o", str(response)])
        == 1
    )


def test_handshake_over_qr_png(keyring: Keyring, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Wie in der Thesis: Challenge und Response als QR-Code-Bild statt als Text."""
    offer = tmp_path / "angebot"
    offer.mkdir()
    (offer / "thesis.pdf").write_bytes(b"x")
    home = ["--gnupghome", str(keyring.home)]
    png, response_png = tmp_path / "challenge.png", tmp_path / "response.png"
    challenge = ["challenge", str(offer), "-r", keyring.bob, "--sign", keyring.alice]
    assert main([*home, *challenge, "-o", str(tmp_path / "c.asc"), "--png", str(png)]) == 0
    respond = ["respond", str(png), "--select", "0", "--sign", keyring.bob]
    assert main([*home, *respond, "-o", str(tmp_path / "r.asc"), "--png", str(response_png)]) == 0
    assert main([*home, "inspect", str(response_png)]) == 0
    assert "Auswahl: thesis.pdf" in capsys.readouterr().out


def test_signer_fingerprint_is_primary_key_with_signing_subkey(tmp_path: Path) -> None:
    """Review #6: bei einem Signatur-Unterschluessel lieferte decrypt den Unterschluessel-Fingerprint."""
    binary = find_gpg_binary()
    home = tmp_path / "gnupg_subkey"
    home.mkdir()

    def gpg(*args: str) -> str:
        cmd = [
            binary,
            "--homedir",
            str(home),
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            *args,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

    try:
        gpg("--quick-gen-key", "Carol <carol@example.test>", "ed25519", "cert", "never")
        primary = gpg("--list-keys", "--with-colons").split("fpr:::::::::")[1].split(":")[0]
        gpg("--quick-add-key", primary, "ed25519", "sign", "never")
        gpg("--quick-add-key", primary, "cv25519", "encr", "never")
        crypto = Crypto(homedir=home, binary=binary)
        _, signer = crypto.decrypt(crypto.encrypt(b"hallo", [primary], primary))
        assert signer.signer_fingerprint == primary
        crypto.encrypt(b"antwort", [signer.signer_fingerprint], primary)  # wie `respond` ohne -r
    finally:
        gpgconf = Path(binary).with_name("gpgconf.exe" if binary.endswith(".exe") else "gpgconf")
        subprocess.run(
            [str(gpgconf), "--homedir", str(home), "--kill", "all"], check=False, capture_output=True
        )


def test_message_for_several_recipients_still_decrypts(keyring: Keyring) -> None:
    """Multicast (Thesis-Kernziel): NO_SECKEY fuer den anderen Empfaenger ist kein Signaturproblem."""
    raw = gnupg.GPG(gpgbinary=find_gpg_binary(), gnupghome=str(keyring.home))
    sealed = raw.encrypt(b"an alle", [keyring.bob, keyring.mallory], sign=keyring.alice, always_trust=True)
    assert sealed.ok
    plain, signer = keyring.crypto.decrypt(sealed.data)
    assert plain == b"an alle" and signer.signer_fingerprint == keyring.alice


def _keyids_without_secret_key(home: Path, message: bytes) -> list[str]:
    """Orakel GnuPG: Empfaenger-KeyIDs, die `gpg --list-packets` ohne jeden Schluessel liest."""
    listing = subprocess.run(
        [find_gpg_binary(), "--homedir", str(home), "--batch", "--list-packets"],
        input=message,
        capture_output=True,
    )
    text = (listing.stdout + listing.stderr).decode(errors="replace")
    return re.findall(r":pubkey enc packet: .*keyid ([0-9A-F]{16})", text)


def test_recipients_are_hidden(keyring: Keyring, tmp_path: Path) -> None:
    """Threat T1: wer den Video-Link hat, dekodiert die Nachricht und sah bisher, fuer wen sie ist."""
    raw = gnupg.GPG(gpgbinary=find_gpg_binary(), gnupghome=str(keyring.home))
    visible = raw.encrypt(b"x", [keyring.bob], sign=keyring.alice, armor=False).data
    bob_keys = {k["keyid"] for k in raw.list_keys() if k["fingerprint"] == keyring.bob} | {
        s[0] for k in raw.list_keys() if k["fingerprint"] == keyring.bob for s in k["subkeys"]
    }
    assert set(_keyids_without_secret_key(tmp_path, visible)) & bob_keys  # Orakel sieht ohne Schutz Bob
    hidden = keyring.crypto.encrypt(b"x", [keyring.bob], keyring.alice)
    ids = _keyids_without_secret_key(tmp_path, hidden)
    assert ids and not set(ids) & bob_keys
    assert set(ids) == {"0000000000000000"}
    assert keyring.crypto.decrypt(hidden)[0] == b"x"


def test_original_filename_travels_encrypted(keyring: Keyring) -> None:
    name = "Quartalsbericht Ärger 2026.xlsx"
    sealed = keyring.crypto.encrypt(b"Zahlen", [keyring.bob], keyring.alice, filename=name)
    assert b"Quartalsbericht" not in sealed
    plain, signer, embedded = keyring.crypto.decrypt_with_name(sealed)
    assert (plain, embedded) == (b"Zahlen", name)
    assert signer.signer_fingerprint == keyring.alice
    unnamed = keyring.crypto.encrypt(b"Zahlen", [keyring.bob], keyring.alice)
    assert keyring.crypto.decrypt_with_name(unnamed)[2] is None


def test_hidden_recipients_still_allow_multicast(keyring: Keyring) -> None:
    """Verborgene Empfaenger: gpg probiert die eigenen Schluessel, der fremde Empfaenger stoert nicht."""
    raw = gnupg.GPG(gpgbinary=find_gpg_binary(), gnupghome=str(keyring.home))
    sealed = raw.encrypt(
        b"an alle",
        [keyring.bob, keyring.mallory],
        sign=keyring.alice,
        always_trust=True,
        armor=False,
        extra_args=["--throw-keyids"],
    )
    assert sealed.ok
    plain, signer = keyring.crypto.decrypt(sealed.data)
    assert plain == b"an alle" and signer.signer_fingerprint == keyring.alice
    assert keyring.mallory_gpg.decrypt(sealed.data).data == b"an alle"
