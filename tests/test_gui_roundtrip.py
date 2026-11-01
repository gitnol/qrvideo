"""Ende-zu-Ende über die GUI-Presenter mit echtem GnuPG, Prozess-Pool und ffmpeg (keine Attrappen).

Getrennte, temporäre Schlüsselbunde wie im echten Einsatz: Alice und Bob haben je ihren eigenen Schlüssel
und den des anderen importiert, beglaubigt und voll vertraut. Carol kennt nur Alices öffentlichen Schlüssel.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import gnupg
import pytest

from qrvideo.crypto import Crypto, GpgError, find_gpg_binary
from qrvideo_gui.handshake import ChallengeRequest, HandshakePresenter, ResponseRequest
from qrvideo_gui.jobs import Failed, Finished, Job, Progress, ProgressEvent
from qrvideo_gui.keys import KeyService
from qrvideo_gui.receive import ReceivePresenter, ReceiveRequest
from qrvideo_gui.send import SendPresenter, SendRequest, suggest_target

pytestmark = pytest.mark.integration


@dataclass
class Person:
    keys: KeyService
    fingerprint: str
    home: Path


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


def _trust(binary: str, gpg: gnupg.GPG, home: Path, owner: gnupg.GPG, fingerprint: str) -> None:
    """Fremden Schlüssel importieren, beglaubigen und voll vertrauen (wie in Kleopatra)."""
    gpg.import_keys(owner.export_keys(fingerprint))
    subprocess.run(
        [binary, "--homedir", str(home), "--batch", "--yes", "--quick-sign-key", fingerprint],
        check=True,
        capture_output=True,
    )
    gpg.trust_keys(fingerprint, "TRUST_FULLY")


@pytest.fixture(scope="module")
def people(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Person]]:
    try:
        binary = find_gpg_binary()
    except GpgError:
        pytest.skip("GnuPG nicht installiert")
    homes = {name: tmp_path_factory.mktemp(f"gnupg_{name.lower()}") for name in ("Alice", "Bob", "Carol")}
    gpgs = {name: gnupg.GPG(gpgbinary=binary, gnupghome=str(home)) for name, home in homes.items()}
    fps = {name: _new_key(gpg, name) for name, gpg in gpgs.items()}
    for me, other in (("Alice", "Bob"), ("Bob", "Alice"), ("Carol", "Alice")):
        _trust(binary, gpgs[me], homes[me], gpgs[other], fps[other])
    yield {
        name: Person(KeyService(partial(Crypto, homedir=home, binary=binary)), fps[name], home)
        for name, home in homes.items()
    }
    gpgconf = Path(binary).with_name("gpgconf.exe" if os.name == "nt" else "gpgconf")
    for home in homes.values():
        subprocess.run(
            [str(gpgconf), "--homedir", str(home), "--kill", "all"], check=False, capture_output=True
        )


def _run_job(task: Job[object]) -> list[object]:
    task.start()
    task.join(300)
    assert not task.running
    return list(task.drain())


def test_send_then_receive_through_the_presenters(people: dict[str, Person], tmp_path: Path) -> None:
    alice, bob = people["Alice"], people["Bob"]
    rows = alice.keys.rows()
    assert [r.own for r in rows] == [True, False]
    source = tmp_path / "bericht.xlsx"
    source.write_bytes(os.urandom(40_000) + "Ü\x00\xff".encode())
    video = suggest_target(source)
    request = SendRequest(source, (bob.fingerprint,), alice.fingerprint, video)

    events = _run_job(Job(lambda progress: SendPresenter(alice.keys).run(request, progress)))
    finished = events[-1]
    assert isinstance(finished, Finished), events[-1]
    frames = [e for e in events if isinstance(e, ProgressEvent) and e.total]
    assert frames and frames[-1].done == frames[-1].total == finished.result.frames  # type: ignore[attr-defined]

    inbox = tmp_path / "eingang"
    inbox.mkdir()
    received = ReceivePresenter(bob.keys).run(ReceiveRequest(str(video), inbox), Progress())
    assert received.target == inbox / "bericht.xlsx"
    assert received.target.read_bytes() == source.read_bytes()
    assert received.signer_fingerprint == alice.fingerprint
    assert received.unreadable == 0


def test_receiver_without_secret_key_gets_a_clear_message(people: dict[str, Person], tmp_path: Path) -> None:
    alice, bob, carol = people["Alice"], people["Bob"], people["Carol"]
    source = tmp_path / "nur_fuer_bob.txt"
    source.write_bytes(b"geheim")
    video = suggest_target(source)
    SendPresenter(alice.keys).run(
        SendRequest(source, (bob.fingerprint,), alice.fingerprint, video), Progress()
    )
    inbox = tmp_path / "carol"
    inbox.mkdir()
    events = _run_job(Job(lambda p: ReceivePresenter(carol.keys).run(ReceiveRequest(str(video), inbox), p)))
    assert isinstance(events[-1], Failed)
    assert "privater Schlüssel" in events[-1].message
    assert list(inbox.iterdir()) == []


def test_handshake_round_over_qr_png(people: dict[str, Person], tmp_path: Path) -> None:
    alice, bob = people["Alice"], people["Bob"]
    offer = tmp_path / "angebot"
    offer.mkdir()
    for name in ("bericht.xlsx", "fotos.zip"):
        (offer / name).write_bytes(b"x")
    challenge = tmp_path / "challenge.asc"
    HandshakePresenter(alice.keys).create_challenge(
        ChallengeRequest(
            offer,
            ("https://youtu.be/dQw4w9WgXcQ", "folder:qrvideo-0123abcd.mp4"),  # Ordner-Verweis seit I29c2
            (bob.fingerprint,),
            alice.fingerprint,
            challenge,
            True,
        ),
        Progress(),
    )
    opened = HandshakePresenter(bob.keys).open_message(challenge.with_suffix(".png"), Progress())
    assert opened.signer_fingerprint == alice.fingerprint
    assert opened.entries == (
        "bericht.xlsx",
        "fotos.zip",
        "youtube:dQw4w9WgXcQ",
        "folder:qrvideo-0123abcd.mp4",
    )
    response = tmp_path / "response.asc"
    HandshakePresenter(bob.keys).create_response(
        ResponseRequest(opened, 3, bob.fingerprint, response, True), Progress()
    )
    answer = HandshakePresenter(alice.keys).open_message(response.with_suffix(".png"), Progress())
    assert (answer.kind, answer.selection, answer.signer_fingerprint) == (
        "response",
        "folder:qrvideo-0123abcd.mp4",
        bob.fingerprint,
    )
