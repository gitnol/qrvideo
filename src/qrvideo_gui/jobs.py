"""Lange Vorgaenge im Hintergrund-Thread: Fortschritt, Ergebnis und Fehler als Ereignisse in einer Queue.

Tk ist nicht threadsicher (ADR-004): Der Thread fasst keine Widgets an, das Fenster holt die Ereignisse per
`after()` mit `Job.drain()` ab. Abbrechen setzt ein Event; `Progress.report`/`count` werfen beim naechsten
Schritt `Cancelled`, damit z. B. `write_video` die halbe Datei entfernt.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")

log = logging.getLogger(__name__)


class Cancelled(Exception):
    """Der Nutzer hat den Vorgang abgebrochen."""


@dataclass(frozen=True)
class ProgressEvent:
    done: int
    total: int | None  # None = Gesamtzahl unbekannt (Balken laeuft unbestimmt)
    text: str = ""


@dataclass(frozen=True)
class Finished:
    result: object


@dataclass(frozen=True)
class Failed:
    message: str  # verstaendlicher Text fuer den Nutzer (errors.friendly_message)


@dataclass(frozen=True)
class WasCancelled:
    pass


Event = ProgressEvent | Finished | Failed | WasCancelled


class Progress:
    """Wird an die Aufgabe uebergeben: Fortschritt melden und Abbruch pruefen."""

    def __init__(self, events: queue.Queue[Event] | None = None) -> None:
        self._events = events
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def check(self) -> None:
        if self._cancel.is_set():
            raise Cancelled

    def report(self, done: int, total: int | None = None, text: str = "") -> None:
        self.check()
        if self._events is not None:
            self._events.put(ProgressEvent(done, total, text))

    def count(self, items: Iterable[T], total: int | None, text: str = "") -> Iterator[T]:
        """Reicht die Elemente durch und meldet jedes einzelne; bricht vor dem naechsten Element ab."""
        for done, item in enumerate(items, start=1):
            self.check()
            yield item
            self.report(done, total, text)


class Job(Generic[R]):
    """Ein Vorgang = ein Thread. Ereignisse: ProgressEvent*, dann eines von Finished/Failed/WasCancelled."""

    def __init__(self, task: Callable[[Progress], R]) -> None:
        self._task = task
        self._events: queue.Queue[Event] = queue.Queue()
        self._progress = Progress(self._events)
        self._thread = threading.Thread(target=self._run, name="qrvideo-gui-job", daemon=True)
        self._started = False

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        if self._started:
            raise RuntimeError("Vorgang laeuft bereits")
        self._started = True
        self._thread.start()

    def cancel(self) -> None:
        self._progress.cancel()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def drain(self) -> list[Event]:
        """Alle bisher eingetroffenen Ereignisse (nicht blockierend)."""
        out: list[Event] = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                return out

    def _run(self) -> None:
        from .errors import friendly_message

        try:
            result = self._task(self._progress)
        except Cancelled:
            self._events.put(WasCancelled())
        except Exception as exc:  # Grenze zur Oberflaeche: alles wird zur Meldung, Details ins Log
            log.exception("Vorgang fehlgeschlagen")
            self._events.put(Failed(friendly_message(exc)))
        else:
            self._events.put(Finished(result))
