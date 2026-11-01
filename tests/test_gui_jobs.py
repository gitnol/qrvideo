"""Hintergrund-Jobs der GUI ohne Tk: Fortschritt, Ergebnis, Fehler und Abbruch kommen als Ereignisse an."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest

from qrvideo_gui.jobs import (
    Cancelled,
    Event,
    Failed,
    Finished,
    Job,
    Progress,
    ProgressEvent,
    WasCancelled,
)


def _run(job: Job[Any]) -> list[Event]:
    job.start()
    job.join(5)
    assert not job.running
    return job.drain()


def test_result_and_progress_arrive_in_order() -> None:
    def task(progress: Progress) -> str:
        progress.report(1, 2, "eins")
        progress.report(2, 2, "zwei")
        return "fertig"

    events = _run(Job(task))
    assert events == [ProgressEvent(1, 2, "eins"), ProgressEvent(2, 2, "zwei"), Finished("fertig")]


def test_exception_becomes_friendly_message_not_traceback() -> None:
    def task(progress: Progress) -> None:
        raise FileNotFoundError(2, "No such file", "fehlt.mp4")

    events = _run(Job(task))
    assert len(events) == 1
    assert isinstance(events[0], Failed)
    assert "fehlt.mp4" in events[0].message
    assert "Traceback" not in events[0].message


def test_count_reports_each_item_with_total() -> None:
    def task(progress: Progress) -> list[int]:
        return list(progress.count(iter([10, 20, 30]), 3, "Frame"))

    events = _run(Job(task))
    assert events[:3] == [ProgressEvent(i, 3, "Frame") for i in (1, 2, 3)]
    assert events[3] == Finished([10, 20, 30])


def test_cancel_stops_at_next_step() -> None:
    started, cancelled = threading.Event(), threading.Event()
    seen: list[int] = []

    def endless() -> Iterator[int]:
        n = 0
        while True:
            n += 1
            yield n

    def task(progress: Progress) -> None:
        for item in progress.count(endless(), None, "Frame"):
            seen.append(item)
            started.set()
            assert cancelled.wait(5)  # erst weiter, wenn der Abbruch gesetzt ist (kein Wettlauf)

    job: Job[None] = Job(task)
    job.start()
    assert started.wait(5)
    job.cancel()
    cancelled.set()
    job.join(5)
    events = job.drain()
    assert events == [WasCancelled()]
    assert seen == [1]


def test_check_raises_cancelled_after_cancel() -> None:
    progress = Progress()
    progress.check()
    progress.cancel()
    with pytest.raises(Cancelled):
        progress.check()
    with pytest.raises(Cancelled):
        progress.report(1, 1)


def test_job_cannot_start_twice() -> None:
    job: Job[None] = Job(lambda progress: None)
    job.start()
    with pytest.raises(RuntimeError):
        job.start()
    job.join(5)
