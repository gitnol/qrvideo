"""Handshake-Format (ohne GnuPG) und Ende-zu-Ende mit temporaerem Schluesselbund."""

from __future__ import annotations

import json

import pytest

from qrvideo.handshake import Challenge, HandshakeError, Response, _encode, parse

FOLDER_REF = "folder:qrvideo-0123abcd.mp4"


def test_roundtrip_challenge_and_response() -> None:
    challenge = Challenge(("bericht.xlsx", "präsentation.pptx"), ("youtube:AbCdEfGhIjK", FOLDER_REF))
    assert json.loads(_encode(challenge))["v"] == 2
    assert parse(_encode(challenge)) == challenge
    for selection in ("bericht.xlsx", "youtube:AbCdEfGhIjK", FOLDER_REF):
        assert parse(_encode(Response(selection))) == Response(selection)


def test_sender_may_still_give_bare_youtube_links() -> None:
    """Eingabe wie bis I29b; geschrieben wird immer mit Kanal (Format v2)."""
    challenge = Challenge(("a.txt",), ("https://youtu.be/AbCdEfGhIjK", "AbCdEfGhIjK"))
    assert json.loads(_encode(challenge))["videos"] == ["youtube:AbCdEfGhIjK"] * 2


def test_version_1_messages_stay_readable() -> None:
    """Wortgleich so, wie I8a bis I29b geschrieben haben: nackte YouTube-IDs."""
    data = b'{"v": 1, "files": ["a.txt"], "videos": ["AbCdEfGhIjK"], "kind": "challenge"}'
    assert parse(data) == Challenge(("a.txt",), ("youtube:AbCdEfGhIjK",))
    assert parse(b'{"v": 1, "selection": "AbCdEfGhIjK", "kind": "response"}') == Response("AbCdEfGhIjK")


@pytest.mark.parametrize(
    "videos",
    [["ftp:x.mp4"], ["folder:../geheim.mp4"], ["folder:CON.mp4"], ["AbCdEfGhIjK"], ["youtube:kurz"]],
)
def test_version_2_videos_are_checked_by_their_channel(videos: list[str]) -> None:
    data = json.dumps({"v": 2, "kind": "challenge", "files": [], "videos": videos}).encode()
    with pytest.raises(HandshakeError, match="Video"):
        parse(data)


@pytest.mark.parametrize("selection", ["ftp:x", "folder:../geheim.mp4", r"C:\Windows\win.ini"])
def test_version_2_selection_with_colon_must_be_a_channel_ref(selection: str) -> None:
    data = json.dumps({"v": 2, "kind": "response", "selection": selection}).encode()
    with pytest.raises(HandshakeError, match="Auswahl"):
        parse(data)


def test_fields_are_named_not_positional() -> None:
    """Gegenstueck zu K10: Reihenfolge der Felder spielt keine Rolle."""
    data = json.dumps({"files": ["a.txt"], "kind": "challenge", "videos": [], "v": 1}).encode()
    assert parse(data) == Challenge(("a.txt",), ())


def test_untrusted_content_is_sanitized() -> None:
    data = json.dumps({"v": 1, "kind": "challenge", "files": ["..\\..\\Autostart\\x.bat", "CON"]}).encode()
    assert parse(data).files == ("x.bat", "datei_CON")  # type: ignore[union-attr]
    data = json.dumps({"v": 1, "kind": "response", "selection": "/etc/passwd"}).encode()
    assert parse(data) == Response("passwd")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff\xfe", "Kein JSON"),
        (b"[1, 2]", "Formatversion"),
        (json.dumps({"v": 3, "kind": "challenge", "files": []}).encode(), "Formatversion"),
        (json.dumps({"v": 1, "kind": "angebot"}).encode(), "Nachrichtenart"),
        (json.dumps({"v": 1, "kind": "challenge", "files": "a.txt"}).encode(), "Liste"),
        (json.dumps({"v": 1, "kind": "challenge", "files": ["a"] * 201}).encode(), "Liste"),
        (json.dumps({"v": 1, "kind": "challenge", "files": [1]}).encode(), "Liste"),
        (json.dumps({"v": 1, "kind": "response", "selection": ""}).encode(), "selection"),
    ],
)
def test_invalid_messages(payload: bytes, message: str) -> None:
    with pytest.raises(HandshakeError, match=message):
        parse(payload)


def test_invalid_video_id_is_rejected() -> None:
    data = json.dumps({"v": 1, "kind": "challenge", "files": [], "videos": ["kein-video"]}).encode()
    with pytest.raises(ValueError, match="Video-ID"):
        parse(data)
