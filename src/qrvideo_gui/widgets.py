"""Gemeinsame Tk-Bausteine: Job-Ereignisse abholen, Empfaenger-Haekchen, Fortschritt, Ordner oeffnen."""

from __future__ import annotations

import logging
import os
import subprocess
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import Any

from qrvideo.i18n import _, format_number

from .jobs import Event, Failed, Finished, Job, ProgressEvent, WasCancelled
from .keys import KeyRow, default_signer

POLL_MS = 100
PAD = 8
WRAP = 720

log = logging.getLogger(__name__)


def watch(widget: tk.Misc, job: Job[Any], on_event: Callable[[Event], None]) -> None:
    """Startet den Job und reicht seine Ereignisse im Tk-Thread an `on_event` weiter, bis er endet."""

    def poll() -> None:
        done = False
        for event in job.drain():
            on_event(event)
            done = done or isinstance(event, Finished | Failed | WasCancelled)
        if done:
            return
        try:
            widget.after(POLL_MS, poll)
        except tk.TclError:  # Fenster wurde geschlossen; der Job endet als Daemon-Thread
            job.cancel()

    job.start()
    widget.after(POLL_MS, poll)


class KeyChecklist(ttk.Frame):
    """Ein Haekchen je vertrautem Schluessel (Name + Schluessel-ID)."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._vars: dict[str, tk.BooleanVar] = {}
        self._empty = ttk.Label(self, text=_("No trusted keys loaded yet (“Keys” tab)."))
        self._empty.pack(anchor="w")

    def set_rows(self, rows: list[KeyRow]) -> None:
        checked = set(self.checked())
        for child in self.winfo_children():
            child.destroy()
        self._vars = {}
        for row in rows:
            var = tk.BooleanVar(self, value=row.fingerprint in checked)
            self._vars[row.fingerprint] = var
            text = _("{name}   ({keyid}, own key)") if row.own else _("{name}   ({keyid})")
            label = text.format(name=row.name, keyid=row.keyid)
            ttk.Checkbutton(self, text=label, variable=var).pack(anchor="w")
        if not rows:
            ttk.Label(self, text=_("No trusted keys found (“Keys” tab).")).pack(anchor="w")

    def checked(self) -> list[str]:
        return [fingerprint for fingerprint, var in self._vars.items() if var.get()]

    def set_checked(self, fingerprints: list[str]) -> None:
        for fingerprint, var in self._vars.items():
            var.set(fingerprint in fingerprints)


class SignerChoice(ttk.Combobox):
    """Auswahl des eigenen Signaturschluessels; ohne eigenen Schluessel stehen alle vertrauten zur Wahl."""

    def __init__(self, parent: tk.Misc) -> None:
        self._var = tk.StringVar(parent)
        super().__init__(parent, textvariable=self._var, state="readonly", width=60)
        self._signers: dict[str, str] = {}  # Anzeigetext -> Fingerprint

    def set_rows(self, rows: list[KeyRow]) -> None:
        own = [r for r in rows if r.own] or rows
        self._signers = {f"{r.name}   ({r.keyid})": r.fingerprint for r in own}
        self.configure(values=list(self._signers))
        preferred = default_signer(rows)
        current = next((t for t, f in self._signers.items() if f == preferred), "")
        if not self._var.get() and current:
            self._var.set(current)

    def fingerprint(self) -> str:
        return self._signers.get(self._var.get(), "")


class ProgressPanel(ttk.Frame):
    """Fortschrittsbalken mit Text; ohne Gesamtzahl laeuft der Balken unbestimmt."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.bar = ttk.Progressbar(self, length=400, mode="determinate")
        self.bar.pack(side="left", fill="x", expand=True)
        self.text = tk.StringVar(self)
        ttk.Label(self, textvariable=self.text, width=34).pack(side="left", padx=(PAD, 0))

    def show(self, event: ProgressEvent) -> None:
        if event.total:
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=event.total, value=event.done)
            text = _("{what} {done} of {total}")
            self.text.set(
                text.format(what=event.text, done=format_number(event.done), total=format_number(event.total))
            )
        else:
            if str(self.bar.cget("mode")) != "indeterminate":
                self.bar.configure(mode="indeterminate")
                self.bar.start(15)
            self.text.set(event.text if not event.done else f"{event.text} {event.done}")

    def reset(self) -> None:
        self.bar.stop()
        self.bar.configure(mode="determinate", value=0)
        self.text.set("")


def open_folder(path: Path) -> None:
    """Ordner im Explorer oeffnen; Datei darin markieren, wenn `path` eine Datei ist."""
    try:
        if os.name == "nt" and path.is_file():
            subprocess.run(["explorer", f"/select,{path}"], check=False)
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", str(path if path.is_dir() else path.parent)], check=False)
    except OSError:
        log.warning("Ordner konnte nicht geöffnet werden: %s", path)
