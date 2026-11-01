"""Reiter „Senden“: vier nummerierte Schritte, Fortschritt, Ergebnis mit „Ordner öffnen“; Logik in send.py."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .jobs import Event, Failed, Finished, Job, ProgressEvent, WasCancelled
from .keys import KeyRow
from .send import YOUTUBE_HINT, SendPresenter, SendRequest, SendResult, suggest_target
from .widgets import PAD, WRAP, KeyChecklist, ProgressPanel, SignerChoice, open_folder, watch

Ask = Callable[[str, str], bool]


class SendTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        presenter: SendPresenter,
        status: tk.StringVar,
        ask: Ask = messagebox.askyesno,
    ) -> None:
        super().__init__(parent, padding=PAD)
        self._presenter, self._status, self._ask = presenter, status, ask
        self.job: Job[Any] | None = None
        self._suggested = ""
        self._done_path: Path | None = None
        self.source, self.target = tk.StringVar(self), tk.StringVar(self)
        self.result = tk.StringVar(self)
        self.columnconfigure(1, weight=1)

        self._step(0, "1. Datei, die Sie senden möchten")
        ttk.Entry(self, textvariable=self.source).grid(row=0, column=1, sticky="ew")
        ttk.Button(self, text="Durchsuchen …", command=self._browse_source).grid(row=0, column=2, padx=PAD)
        self._step(1, "2. Empfänger ankreuzen")
        self.recipients = KeyChecklist(self)
        self.recipients.grid(row=1, column=1, columnspan=2, sticky="w", pady=PAD)
        self._step(2, "3. Signieren mit Ihrem Schlüssel")
        self.signer_box = SignerChoice(self)
        self.signer_box.grid(row=2, column=1, sticky="w")
        self._step(3, "4. Zielvideo")
        ttk.Entry(self, textvariable=self.target).grid(row=3, column=1, sticky="ew", pady=PAD)
        ttk.Button(self, text="Speichern unter …", command=self._browse_target).grid(
            row=3, column=2, padx=PAD
        )

        buttons = ttk.Frame(self)
        buttons.grid(row=4, column=1, sticky="w", pady=PAD)
        self.send_button = ttk.Button(buttons, text="Senden", command=self.start_send)
        self.send_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="Abbrechen", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=PAD)
        self.progress = ProgressPanel(self)
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew")
        ttk.Label(self, textvariable=self.result, wraplength=WRAP, justify="left").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=PAD
        )
        self.open_button = ttk.Button(self, text="Ordner öffnen", command=self._open, state="disabled")
        self.open_button.grid(row=7, column=0, sticky="w")
        self.hint = ttk.Label(self, text="", wraplength=WRAP, justify="left", foreground="#555")
        self.hint.grid(row=8, column=0, columnspan=3, sticky="w", pady=PAD)

    def _step(self, row: int, text: str) -> None:
        ttk.Label(self, text=text).grid(row=row, column=0, sticky="nw", padx=(0, PAD), pady=PAD)

    @property
    def busy(self) -> bool:
        return self.job is not None and self.job.running

    def set_keys(self, rows: list[KeyRow]) -> None:
        self.recipients.set_rows(rows)
        self.signer_box.set_rows(rows)

    def signer_fingerprint(self) -> str:
        return self.signer_box.fingerprint()

    def choose_source(self, path: Path) -> None:
        self.source.set(str(path))
        if not self.target.get() or self.target.get() == self._suggested:
            self._suggested = str(suggest_target(path))
            self.target.set(self._suggested)

    def _browse_source(self) -> None:
        chosen = filedialog.askopenfilename(parent=self, title="Datei zum Senden wählen")
        if chosen:
            self.choose_source(Path(chosen))

    def _browse_target(self) -> None:
        chosen = filedialog.asksaveasfilename(
            parent=self, title="Zielvideo", defaultextension=".mp4", filetypes=[("MP4-Video", "*.mp4")]
        )
        if chosen:
            self.target.set(chosen)

    def _request(self) -> SendRequest:
        return SendRequest(
            source=Path(self.source.get().strip()),
            recipients=tuple(self.recipients.checked()),
            signer=self.signer_fingerprint(),
            target=Path(self.target.get().strip()),
        )

    def start_send(self) -> None:
        from .send import validate

        request = self._request()
        problems = validate(request)
        if problems:
            self.result.set("\n".join(problems))
            return
        overwrite = self._presenter.needs_overwrite(request)
        if overwrite and not self._ask(
            "Video überschreiben?", f"„{request.target.name}“ gibt es schon. Überschreiben?"
        ):
            return
        presenter = self._presenter  # Task erfasst kein Widget: Tk-Objekte nie im Worker-Thread freigeben
        self.job = Job(lambda progress: presenter.run(request, progress, overwrite))
        self._set_running(True)
        self.result.set("")
        self.hint.configure(text="")
        self._status.set("Senden läuft …")
        watch(self, self.job, self._on_event)

    def cancel(self) -> None:
        if self.job is not None:
            self.job.cancel()
            self._status.set("Wird abgebrochen …")

    def _set_running(self, running: bool) -> None:
        self.send_button.state(["disabled"] if running else ["!disabled"])
        self.cancel_button.state(["!disabled"] if running else ["disabled"])
        self.open_button.state(["disabled"])

    def _on_event(self, event: Event) -> None:
        if isinstance(event, ProgressEvent):
            self.progress.show(event)
            return
        self._set_running(False)
        self.progress.reset()
        if isinstance(event, Finished):
            result: SendResult = event.result  # type: ignore[assignment]
            self._done_path = result.target
            self.result.set(
                f"Fertig: {result.target.name} – {result.frames} Frames, {result.seconds:.1f} s Video "
                f"(gedauert: {result.elapsed:.0f} s)."
            )
            self.open_button.state(["!disabled"])
            self.hint.configure(text=YOUTUBE_HINT)
        elif isinstance(event, Failed):
            self.result.set(event.message)
        elif isinstance(event, WasCancelled):
            self.result.set("Abgebrochen. Es wurde kein Video gespeichert.")
        self._status.set("Bereit")

    def _open(self) -> None:
        if self._done_path is not None:
            open_folder(self._done_path)
