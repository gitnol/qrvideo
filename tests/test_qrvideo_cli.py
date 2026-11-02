"""YouTube-ID, Download-Optionen (ohne Netz), Dateinamen und CLI-Fehlerpfade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qrvideo import youtube
from qrvideo.cli import main
from qrvideo.paths import safe_filename


@pytest.mark.parametrize(
    "text",
    [
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42",
        "https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
        "https://youtube.com/shorts/dQw4w9WgXcQ?si=abc",
        "  dQw4w9WgXcQ ",
    ],
)
def test_parse_video_id(text: str) -> None:
    assert youtube.parse_video_id(text) == "dQw4w9WgXcQ"


@pytest.mark.parametrize("text", ["", "zu-kurz", "https://example.com/watch?x=1", "dQw4w9WgXcQQ"])
def test_parse_video_id_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        youtube.parse_video_id(text)


class FakeYoutubeDL:
    seen: dict[str, Any] = {}

    def __init__(self, options: dict[str, Any]) -> None:
        FakeYoutubeDL.seen = options

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool) -> dict[str, str]:
        assert download and url.endswith("v=AbCdEfGhIjK")
        info = {"id": "AbCdEfGhIjK", "ext": "mp4"}
        Path(self.prepare_filename(info)).write_bytes(b"video")
        return info

    def prepare_filename(self, info: dict[str, str]) -> str:
        """Wie yt-dlp: outtmpl relativ zu paths.home."""
        home = FakeYoutubeDL.seen.get("paths", {}).get("home", "")
        name = (
            str(FakeYoutubeDL.seen["outtmpl"]).replace("%(id)s", info["id"]).replace("%(ext)s", info["ext"])
        )
        return str(Path(home) / name)


def test_download_options(tmp_path: Path) -> None:
    path = youtube.download("https://youtu.be/AbCdEfGhIjK", tmp_path / "eingang", ydl_class=FakeYoutubeDL)
    assert path == tmp_path / "eingang" / "AbCdEfGhIjK.mp4"
    options = FakeYoutubeDL.seen
    assert "height=1080" in options["format"] and options["noplaylist"] is True
    assert not {"netrc_cmd", "external_downloader", "writelink", "writeurllink"} & options.keys()
    assert "cookiesfrombrowser" not in options  # Cookies nur auf ausdruecklichen Wunsch (I30a)


def test_download_with_browser_cookies(tmp_path: Path) -> None:
    youtube.download(
        "AbCdEfGhIjK", tmp_path, ydl_class=FakeYoutubeDL, cookies_from_browser=("firefox", "default")
    )
    assert FakeYoutubeDL.seen["cookiesfrombrowser"] == ("firefox", "default")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("firefox", ("firefox",)),
        (" Chrome:Profile 1 ", ("chrome", "Profile 1")),
        (r"edge:C:\Users\x\Edge", ("edge", r"C:\Users\x\Edge")),  # Profil als Pfad: nur am ersten Doppelpunkt
    ],
)
def test_parse_browser_spec(text: str, expected: tuple[str, ...]) -> None:
    assert youtube.parse_browser_spec(text) == expected


@pytest.mark.parametrize("text", ["netscape", "", "firefox:", "firefox:\x00", ":default"])
def test_parse_browser_spec_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="Browser"):
        youtube.parse_browser_spec(text)


def test_browser_list_matches_yt_dlp() -> None:
    cookies = pytest.importorskip("yt_dlp.cookies")
    assert set(youtube.BROWSERS) == set(cookies.SUPPORTED_BROWSERS)


def test_cli_download_passes_cookies_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[Any] = []

    def fake_download(
        video: str, target: Path, ydl_class: Any = None, cookies_from_browser: Any = None
    ) -> Path:
        calls.append(cookies_from_browser)
        return target / f"{video}.mp4"

    monkeypatch.setattr(youtube, "download", fake_download)
    assert main(["download", "AbCdEfGhIjK", "-d", str(tmp_path)]) == 0
    assert main(["download", "AbCdEfGhIjK", "-d", str(tmp_path), "--cookies-from-browser", "firefox"]) == 0
    assert calls == [None, ("firefox",)]
    with pytest.raises(SystemExit) as exit_info:
        main(["download", "AbCdEfGhIjK", "--cookies-from-browser", "netscape"])
    assert exit_info.value.code == 2
    capsys.readouterr()
    folder = ["--channel", "folder", "--folder", str(tmp_path), "--cookies-from-browser", "firefox"]
    assert main(["download", "qrvideo-0123abcd.mp4", "-d", str(tmp_path / "e"), *folder]) == 1
    assert "nur für YouTube" in capsys.readouterr().err


def test_token_path_outside_program(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert youtube.default_token_path() == tmp_path / "qrvideo" / "youtube-token.json"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bericht.xlsx", "bericht.xlsx"),
        ("../../Windows/System32/evil.dll", "evil.dll"),
        ("C:\\Users\\x\\a.txt", "a.txt"),
        ('a<b>c:d"e|f?g*h', "a_b_c_d_e_f_g_h"),
        ("CON.txt", "datei_CON.txt"),
        ("..", "datei"),
        ("", "datei"),
        ("zeile\nzwei", "zeile_zwei"),
    ],
)
def test_safe_filename(name: str, expected: str) -> None:
    assert safe_filename(name) == expected


def test_cli_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["decode", str(tmp_path / "fehlt.mp4"), "-o", str(tmp_path / "x")]) == 1
    assert "Fehler" in capsys.readouterr().err


@pytest.mark.integration
def test_cli_encode_decode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "daten.bin"
    source.write_bytes(bytes(range(256)) * 100)
    video = tmp_path / "daten.mp4"
    assert main(["encode", str(source), "-o", str(video), "--ecc", "Q", "--crf", "18", "--workers", "1"]) == 0
    assert main(["decode", str(video), "-o", str(tmp_path / "zurueck.bin")]) == 0
    assert (tmp_path / "zurueck.bin").read_bytes() == source.read_bytes()
    assert "Frames" in capsys.readouterr().out


def test_gpg_lookup_skips_git_bundled_gpg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from qrvideo import crypto

    git_gpg = tmp_path / "Git" / "usr" / "bin" / "gpg.exe"
    git_gpg.parent.mkdir(parents=True)
    git_gpg.write_bytes(b"")
    monkeypatch.delenv("QRVIDEO_GPG", raising=False)
    monkeypatch.setattr("qrvideo.crypto.shutil.which", lambda _: str(git_gpg))
    monkeypatch.setattr(crypto, "WINDOWS_GPG", ())
    with pytest.raises(crypto.GpgNotFoundError):
        crypto.find_gpg_binary()
    monkeypatch.setenv("QRVIDEO_GPG", str(git_gpg))
    assert crypto.find_gpg_binary() == str(git_gpg)  # explizite Wahl gewinnt
    monkeypatch.setenv("QRVIDEO_GPG", str(tmp_path / "fehlt.exe"))
    with pytest.raises(crypto.GpgError, match="keine Datei"):
        crypto.find_gpg_binary()


class _FakeDecrypt:
    """Nachbau eines python-gnupg-Ergebnisses (Konstanten wie gnupg.Verify)."""

    TRUST_MARGINAL, TRUST_FULLY = 2, 3
    ok, valid, key_id, fingerprint, username, data = True, True, "ABCD", "ABCD" * 10, "Eve", b"geheim"
    stderr = ""  # Statuszeilen von gpg (hier ohne PLAINTEXT)

    def __init__(self, trust_level: int, sigs: int = 1, problems: list[dict[str, str]] | None = None) -> None:
        self.trust_level = trust_level
        self.problems = problems or []
        self.sig_info = {
            f"sig{i}": {
                "status": "signature valid",
                "trust_level": trust_level,
                "fingerprint": "ABCD" * 10,
                "pubkey_fingerprint": "ABCD" * 10,
                "keyid": "ABCD",
                "username": "Eve",
            }
            for i in range(sigs)
        }


@pytest.mark.parametrize(("level", "accepted"), [(2, False), (3, True), (4, True)])
def test_decrypt_requires_full_trust(level: int, accepted: bool) -> None:
    from types import SimpleNamespace

    from qrvideo.crypto import Crypto, UntrustedSignatureError

    crypto = Crypto.__new__(Crypto)
    crypto._gpg = SimpleNamespace(decrypt=lambda data, passphrase: _FakeDecrypt(level))
    if accepted:
        assert crypto.decrypt(b"x")[0] == b"geheim"
    else:
        with pytest.raises(UntrustedSignatureError, match="nicht voll vertraut"):
            crypto.decrypt(b"x")


def test_ctrl_c_exits_130(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import qrvideo.cli as cli

    def interrupted(args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "cmd_keys", interrupted)
    assert cli.main(["keys"]) == 130
    assert "Abgebrochen" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("version", "warns"), [("7.1-essentials_build-www.gyan.dev", True), ("8.1.3", False)]
)
def test_outdated_ffmpeg_warning(monkeypatch: pytest.MonkeyPatch, version: str, warns: bool) -> None:
    from qrvideo.videoio import outdated_ffmpeg_warning

    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    assert (outdated_ffmpeg_warning(version) is not None) is warns
    monkeypatch.setenv("IMAGEIO_FFMPEG_EXE", "ffmpeg")
    assert outdated_ffmpeg_warning(version) is None


@pytest.mark.integration
def test_bundled_ffmpeg_version_is_read() -> None:
    from qrvideo.videoio import ffmpeg_version

    assert ffmpeg_version()[0].isdigit()


@pytest.mark.parametrize(
    ("sigs", "problems", "accepted"),
    [
        (2, [], False),  # Review #7: mehrere Signaturen - es zaehlte nur die zuletzt gemeldete
        (0, [], False),
        (1, [{"status": "signature error", "keyid": "BEEF"}], False),  # ERRSIG + GOODSIG
        (1, [{"status": "no public key", "keyid": "BEEF"}], False),
        (1, [{"status": "no secret key", "keyid": "BEEF"}], True),  # anderer Empfaenger: kein Signaturproblem
    ],
)
def test_decrypt_checks_every_signature(sigs: int, problems: list[dict[str, str]], accepted: bool) -> None:
    from types import SimpleNamespace

    from qrvideo.crypto import Crypto, UntrustedSignatureError

    crypto = Crypto.__new__(Crypto)
    crypto._gpg = SimpleNamespace(decrypt=lambda data, passphrase: _FakeDecrypt(4, sigs, problems))
    if accepted:
        assert crypto.decrypt(b"x")[0] == b"geheim"
    else:
        with pytest.raises(UntrustedSignatureError):
            crypto.decrypt(b"x")


def test_upload_title_does_not_reveal_the_file_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Threat T1: ohne --title stand der Dateiname als YouTube-Titel im Netz."""
    titles: list[str] = []

    def fake_upload(path: Path, title: str, secrets: Path, **_: Any) -> youtube.Uploaded:
        titles.append(title)
        return youtube.Uploaded("VIDEOID1234", "private" if len(titles) == 1 else "unlisted")

    monkeypatch.setattr(youtube, "upload", fake_upload)
    video = tmp_path / "Gehaltsliste_Mueller.mp4"
    video.write_bytes(b"video")
    for extra in ([], ["--title", "Eigener Titel"]):
        assert main(["upload", str(video), "--client-secrets", str(tmp_path / "c.json"), *extra]) == 0
    assert "Gehalt" not in titles[0] and "Mueller" not in titles[0]
    assert titles[0].startswith("qrvideo ")
    assert titles[1] == "Eigener Titel"
    out, err = capsys.readouterr()
    assert out.split() == ["https://youtu.be/VIDEOID1234"] * 2
    assert (
        err.count("Hinweis:") == 1 and "privat" in err
    )  # nur beim ersten, „privat“ gespeicherten Upload (I30b1)


def test_receive_sanitizes_the_embedded_file_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Der Name im verschluesselten Paket stammt vom Absender: fremde Eingabe, nie ein Pfad (Threat T5)."""
    import qrvideo.cli as cli
    from qrvideo.crypto import SignatureInfo
    from qrvideo.decoder import DecodeReport

    class NamingCrypto:
        def decrypt_with_name(self, data: bytes, passphrase: str | None) -> tuple[bytes, SignatureInfo, str]:
            return b"inhalt", SignatureInfo("ABCD", "ABCD" * 10, "Eve"), "../../boese.txt"

    monkeypatch.setattr(cli, "decode_video", lambda path: (b"chiffrat", DecodeReport()))
    monkeypatch.setattr(cli, "_crypto", lambda args: NamingCrypto())
    inbox = tmp_path / "eingang"
    inbox.mkdir()
    assert cli.main(["receive", str(tmp_path / "video.mp4"), "-o", str(inbox)]) == 0
    assert [p.name for p in inbox.iterdir()] == ["boese.txt"]
    assert not (tmp_path / "boese.txt").exists()


def test_upload_and_download_through_the_folder_channel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-005: derselbe Befehl, anderer Kanal — ohne Netz und ohne OAuth-Client."""
    shared, inbox = tmp_path / "geteilt", tmp_path / "eingang"
    shared.mkdir()
    video = tmp_path / "Gehaltsliste_Mueller.mp4"
    video.write_bytes(b"qr-video")
    assert main(["upload", str(video), "--channel", "folder", "--folder", str(shared)]) == 0
    ref = capsys.readouterr().out.strip()
    assert ref.startswith("qrvideo-") and (shared / ref).read_bytes() == b"qr-video"
    assert main(["download", ref, "--channel", "folder", "--folder", str(shared), "-d", str(inbox)]) == 0
    assert capsys.readouterr().out.strip() == str(inbox / ref)
    assert (inbox / ref).read_bytes() == b"qr-video"


@pytest.mark.parametrize(
    "args",
    [
        ["upload", "VIDEO"],  # YouTube ohne --client-secrets
        ["upload", "VIDEO", "--channel", "folder"],  # Ordner-Kanal ohne --folder
        ["download", "../geheim.mp4", "--channel", "folder", "--folder", "FOLDER"],
    ],
)
def test_channel_misuse_is_reported(
    args: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"v")
    (tmp_path / "geheim.mp4").write_bytes(b"geheim")
    (tmp_path / "geteilt").mkdir()
    argv = [str(video) if a == "VIDEO" else str(tmp_path / "geteilt") if a == "FOLDER" else a for a in args]
    assert main([*argv, "-d", str(tmp_path / "eingang")] if args[0] == "download" else argv) == 1
    assert "Fehler" in capsys.readouterr().err
    assert not (tmp_path / "eingang").exists()


@pytest.mark.integration
def test_cli_round_trip_through_the_folder_channel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ende-zu-Ende (TODO I29b): encode -> upload -> download -> decode, Kanal = gemeinsamer Ordner."""
    shared, inbox = tmp_path / "geteilt", tmp_path / "eingang"
    shared.mkdir()
    source = tmp_path / "daten.bin"
    source.write_bytes(bytes(range(256)) * 100)
    video = tmp_path / "daten.mp4"
    assert main(["encode", str(source), "-o", str(video), "--crf", "18", "--workers", "1"]) == 0
    capsys.readouterr()
    assert main(["upload", str(video), "--channel", "folder", "--folder", str(shared)]) == 0
    ref = capsys.readouterr().out.strip()
    assert main(["download", ref, "--channel", "folder", "--folder", str(shared), "-d", str(inbox)]) == 0
    fetched = Path(capsys.readouterr().out.strip())
    assert main(["decode", str(fetched), "-o", str(tmp_path / "zurueck.bin")]) == 0
    assert (tmp_path / "zurueck.bin").read_bytes() == source.read_bytes()
