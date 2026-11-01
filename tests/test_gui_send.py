"""Reiter „Senden“: Presenter mit Fakes (Crypto, Frames, Writer) und ein Durchlauf der Oberfläche."""

from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from gui_fakes import ALICE, BOB, FakeCrypto, pump

import qrcodegenmod as q
from qrvideo.encoder import frame_count
from qrvideo.videoio import VideoSettings
from qrvideo_gui.jobs import Cancelled, Job, Progress, ProgressEvent
from qrvideo_gui.keys import KeyService
from qrvideo_gui.send import SendPresenter, SendRequest, suggest_target, validate

Frame = npt.NDArray[np.uint8]


class Recorder:
    """Ersetzt iter_frames + write_video: zählt Frames, schreibt eine Datei, merkt sich das Schließen."""

    def __init__(self, frames: int = 3) -> None:
        self.frames = frames
        self.closed = False
        self.payload = b""
        self.format: tuple[q.Ecc, int, int] | None = None  # ECC, Version, Paritaet
        self.source: Iterator[Frame] | None = None

    def iter_frames(
        self, payload: bytes, ecl: q.Ecc, workers: int | None, version: int, parity: int
    ) -> Iterator[Frame]:
        self.payload = payload
        self.format = (ecl, version, parity)
        # Referenz halten: sonst schlösse CPython den Generator per Referenzzählung, und der Test sähe nicht,
        # ob der Presenter ihn selbst schließt (den Prozess-Pool beendet)
        self.source = self._frames()
        return self.source

    def _frames(self) -> Iterator[Frame]:
        try:
            for _ in range(self.frames):
                yield np.zeros((2, 2), dtype=np.uint8)
        finally:
            self.closed = True

    def write_video(self, path: Path, frames: Iterable[Frame], settings: VideoSettings) -> int:
        count = sum(1 for _ in frames)
        path.write_bytes(b"video")
        return count


def _presenter(recorder: Recorder, crypto: FakeCrypto | None = None) -> tuple[SendPresenter, FakeCrypto]:
    crypto = crypto or FakeCrypto([ALICE, BOB])
    presenter = SendPresenter(KeyService(lambda: crypto), recorder.iter_frames, recorder.write_video)
    return presenter, crypto


def _request(tmp_path: Path, **changes: object) -> SendRequest:
    source = tmp_path / "bericht.xlsx"
    source.write_bytes(b"geheime Tabelle")
    values: dict[str, object] = {
        "source": source,
        "recipients": (BOB.fingerprint,),
        "signer": ALICE.fingerprint,
        "target": tmp_path / "bericht.mp4",
    }
    values.update(changes)
    return SendRequest(**values)  # type: ignore[arg-type]


def test_send_encrypts_for_recipients_and_reports_every_frame(tmp_path: Path) -> None:
    recorder = Recorder(frames=3)
    presenter, crypto = _presenter(recorder)
    events: list[ProgressEvent] = []

    class Spy(Progress):
        def report(self, done: int, total: int | None = None, text: str = "") -> None:
            events.append(ProgressEvent(done, total, text))

    result = presenter.run(_request(tmp_path), Spy())
    assert crypto.encrypted == [([BOB.fingerprint], ALICE.fingerprint, None, False)]
    assert recorder.payload == FakeCrypto.PREFIX + b"geheime Tabelle"
    assert recorder.format == (q.Ecc.LOW, 3, 14)  # Standard wie die CLI: ECC L, 10 % Paritaet (I18)
    expected_total = frame_count(recorder.payload, q.Ecc.LOW, 14)
    frame_events = [e for e in events if e.total is not None]
    assert [e.done for e in frame_events] == [1, 2, 3]
    assert {e.total for e in frame_events} == {expected_total}
    assert result.frames == 3
    assert result.target == tmp_path / "bericht.mp4"
    assert (tmp_path / "bericht.mp4").read_bytes() == b"video"


def test_existing_target_needs_confirmation(tmp_path: Path) -> None:
    recorder = Recorder()
    presenter, crypto = _presenter(recorder)
    request = _request(tmp_path)
    request.target.write_bytes(b"alt")
    assert presenter.needs_overwrite(request)
    with pytest.raises(FileExistsError):
        presenter.run(request, Progress())
    assert request.target.read_bytes() == b"alt"
    assert crypto.encrypted == []
    presenter.run(request, Progress(), overwrite=True)
    assert request.target.read_bytes() == b"video"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"recipients": ()}, "Empfänger"),
        ({"signer": ""}, "Signaturschlüssel"),
        ({"source": Path("fehlt.xlsx")}, "Datei"),
        ({"target": Path("ziel.avi")}, ".mp4"),
    ],
)
def test_validate_names_the_missing_field(tmp_path: Path, changes: dict[str, object], expected: str) -> None:
    problems = validate(_request(tmp_path, **changes))
    assert len(problems) == 1
    assert expected in problems[0]
    with pytest.raises(ValueError, match=expected):
        _presenter(Recorder())[0].run(_request(tmp_path, **changes), Progress())


def test_target_must_not_be_the_source(tmp_path: Path) -> None:
    request = _request(tmp_path)
    assert validate(_request(tmp_path, target=request.source.with_suffix(".mp4"))) == []
    same = _request(tmp_path, source=tmp_path / "film.mp4", target=tmp_path / "film.mp4")
    same.source.write_bytes(b"x")
    assert any("Quelldatei" in p for p in validate(same))


def test_cancel_stops_rendering_and_closes_the_frame_source(tmp_path: Path) -> None:
    recorder = Recorder(frames=50)
    presenter, _ = _presenter(recorder)
    progress = Progress()
    original = progress.report

    def cancel_after_second(done: int, total: int | None = None, text: str = "") -> None:
        original(done, total, text)
        if done == 2:
            progress.cancel()

    progress.report = cancel_after_second  # type: ignore[method-assign]
    with pytest.raises(Cancelled):
        presenter.run(_request(tmp_path), progress)
    assert recorder.closed


def test_suggested_video_name_is_neutral_and_next_to_the_file(tmp_path: Path) -> None:
    """Threat T1: der Videoname landet als Datei- und oft als Titelname im Netz (I27b2)."""
    names = {suggest_target(tmp_path / "Gehaltsliste Mueller.xlsx") for _ in range(5)}
    assert len(names) == 5  # zufaellig, nicht ableitbar
    for name in names:
        assert name.parent == tmp_path
        assert re.fullmatch(r"qrvideo-[0-9a-f]{8}\.mp4", name.name)


def test_original_name_travels_encrypted(tmp_path: Path) -> None:
    recorder = Recorder()
    presenter, crypto = _presenter(recorder)
    presenter.run(_request(tmp_path), Progress())
    assert crypto.embedded_name == "bericht.xlsx"


def test_send_tab_runs_and_shows_result(tmp_path: Path, root: tk.Toplevel) -> None:
    from qrvideo_gui.send_view import SendTab

    recorder = Recorder(frames=2)
    presenter, crypto = _presenter(recorder)
    status = tk.StringVar(root)
    tab = SendTab(root, presenter, status, ask=lambda title, text: True)
    tab.pack()
    tab.set_keys(KeyService(lambda: crypto).rows())
    source = tmp_path / "bericht.xlsx"
    source.write_bytes(b"geheim")
    tab.choose_source(source)
    assert Path(tab.target.get()).parent == tmp_path and "bericht" not in tab.target.get()
    assert tab.signer_fingerprint() == ALICE.fingerprint
    tab.recipients.set_checked([BOB.fingerprint])
    tab.send_button.invoke()
    pump(root, lambda: "Fertig" in tab.result.get())
    assert "2 Frames" in tab.result.get()
    assert crypto.encrypted[0][0] == [BOB.fingerprint]


def test_send_tab_shows_validation_problem_without_starting(tmp_path: Path, root: tk.Toplevel) -> None:
    from qrvideo_gui.send_view import SendTab

    presenter, crypto = _presenter(Recorder())
    tab = SendTab(root, presenter, tk.StringVar(root), ask=lambda title, text: True)
    tab.set_keys(KeyService(lambda: crypto).rows())
    tab.send_button.invoke()
    assert "Datei" in tab.result.get()
    assert crypto.encrypted == []
    assert not isinstance(tab.job, Job)
