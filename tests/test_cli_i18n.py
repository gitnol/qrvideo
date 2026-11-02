"""CLI in drei Sprachen (ADR-006): `--lang`, `QRVIDEO_LANG`, Hilfe, argparse-Fehler, Zahlenformat."""

from __future__ import annotations

from pathlib import Path

import pytest

import qrvideo.cli as cli
from qrvideo.decoder import DecodeReport
from qrvideo.i18n import set_language
from qrvideo.videoio import VideoSettings


def _interrupt(args: object) -> None:
    raise KeyboardInterrupt


@pytest.mark.parametrize(
    ("lang", "expected"), [("de", "Abgebrochen"), ("en", "Cancelled"), ("es", "Cancelado")]
)
def test_lang_option_selects_the_language(
    lang: str, expected: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "cmd_keys", _interrupt)
    assert cli.main(["--lang", lang, "keys"]) == 130
    assert capsys.readouterr().err.strip() == expected


def test_environment_selects_the_language_and_option_wins(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "cmd_keys", _interrupt)
    monkeypatch.setenv("QRVIDEO_LANG", "es")
    cli.main(["keys"])
    assert capsys.readouterr().err.strip() == "Cancelado"
    cli.main(["--lang", "en", "keys"])
    assert capsys.readouterr().err.strip() == "Cancelled"


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", ("usage: qrvideo", "Transfer files as a QR code video", "show this help message and exit")),
        ("es", ("uso: qrvideo", "Transferir archivos como vídeo", "mostrar esta ayuda y salir", "opciones")),
        (
            "de",
            ("Aufruf: qrvideo", "Dateien als QR-Code-Video übertragen", "diese Hilfe anzeigen", "Optionen"),
        ),
    ],
)
def test_help_is_translated(lang: str, expected: tuple[str, ...], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--lang", lang, "--help"])
    out = capsys.readouterr().out
    assert all(text in out for text in expected), out


def test_argparse_errors_are_translated(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--lang", "es", "decode"])
    assert exit_info.value.code == 2
    assert "qrvideo decode: error: se requieren los siguientes argumentos: input, -o/--output" in (
        capsys.readouterr().err
    )


def test_existing_target_is_reported_in_spanish(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source, target = tmp_path / "a.bin", tmp_path / "a.mp4"
    source.write_bytes(b"x")
    target.write_bytes(b"")
    assert cli.main(["--lang", "es", "encode", str(source), "-o", str(target)]) == 1
    assert capsys.readouterr().err.strip() == f"Error: {target} ya existe (--force para sobrescribir)"


@pytest.mark.parametrize(
    ("lang", "video", "report"),
    [
        (
            "de",
            "v.mp4: 30.000 Frames (1.000,0 s)",
            "12.000 Frames, 4 QR-Codes gelesen, 0 leer, 1.500 Bytes per",
        ),
        (
            "en",
            "v.mp4: 30,000 frames (1,000.0 s)",
            "12,000 frames, 4 QR codes read, 0 empty, 1,500 bytes corrected",
        ),
        (
            "es",
            "v.mp4: 30.000 fotogramas (1000,0 s)",
            "12.000 fotogramas, 4 códigos QR leídos, 0 vacíos, 1500 bytes",
        ),
    ],
)
def test_counts_and_seconds_use_the_language_format(
    lang: str, video: str, report: str, capsys: pytest.CaptureFixture[str]
) -> None:
    set_language(lang)
    cli._print_video(Path("v.mp4"), 30000, VideoSettings())
    cli._report(DecodeReport(frames=12000, qr_codes=4, corrected_bytes=1500))
    captured = capsys.readouterr()
    assert captured.out.strip() == video
    assert captured.err.startswith(report)
