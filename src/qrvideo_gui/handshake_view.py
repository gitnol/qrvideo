"""Reiter „Handshake“: links Angebot (Challenge) erstellen, rechts Nachricht öffnen und beantworten."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .handshake import (
    CHALLENGE,
    ChallengeRequest,
    HandshakePresenter,
    OpenedMessage,
    ResponseRequest,
    SealedResult,
)
from .jobs import Event, Failed, Finished, Job, Progress, WasCancelled
from .keys import KeyRow, format_fingerprint
from .widgets import PAD, KeyChecklist, SignerChoice, watch

Ask = Callable[[str, str], bool]
WRAP = 400
INTRO = (
    "Der Handshake klärt vorab, was übertragen wird: Der Anbieter verschickt ein verschlüsseltes Angebot "
    "(Challenge), der Empfänger antwortet mit seiner Auswahl (Response). Beide Nachrichten reisen als "
    "Text (.asc) oder als QR-Code-Bild (.png) über einen beliebigen Kanal."
)


def _file_row(parent: tk.Misc, row: int, text: str, var: tk.StringVar, browse: Callable[[], None]) -> None:
    ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=(PAD, 0))
    line = ttk.Frame(parent)
    line.grid(row=row + 1, column=0, sticky="ew")
    line.columnconfigure(0, weight=1)
    ttk.Entry(line, textvariable=var).grid(row=0, column=0, sticky="ew")
    ttk.Button(line, text="…", width=3, command=browse).grid(row=0, column=1, padx=(PAD // 2, 0))


def _save_as(parent: tk.Misc, var: tk.StringVar, title: str) -> None:
    chosen = filedialog.asksaveasfilename(
        parent=parent, title=title, defaultextension=".asc", filetypes=[("Nachricht", "*.asc")]
    )
    if chosen:
        var.set(chosen)


class HandshakeTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        presenter: HandshakePresenter,
        status: tk.StringVar,
        ask: Ask = messagebox.askyesno,
    ) -> None:
        super().__init__(parent, padding=PAD)
        self._presenter, self._status, self._ask = presenter, status, ask
        self.job: Job[Any] | None = None
        self._opened: OpenedMessage | None = None
        ttk.Label(self, text=INTRO, wraplength=2 * WRAP + 3 * PAD, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, PAD)
        )
        self.columnconfigure((0, 1), weight=1, uniform="half")
        self._build_challenge(ttk.LabelFrame(self, text="Angebot erstellen (Challenge)", padding=PAD))
        self._build_answer(ttk.LabelFrame(self, text="Nachricht öffnen und beantworten", padding=PAD))

    def _build_challenge(self, box: ttk.LabelFrame) -> None:
        box.grid(row=1, column=0, sticky="nsew", padx=(0, PAD))
        box.columnconfigure(0, weight=1)
        self.directory, self.challenge_target = tk.StringVar(self), tk.StringVar(self)
        self.challenge_png, self.challenge_result = tk.BooleanVar(self, value=True), tk.StringVar(self)
        _file_row(box, 0, "Ordner mit den angebotenen Dateien", self.directory, self._browse_directory)
        ttk.Label(
            box,
            text="Bereitgestellte Videos (YouTube-Link oder folder:<Dateiname>, je Zeile, optional)",
            wraplength=WRAP,  # sonst bestimmt diese eine Zeile die Breite beider Spalten
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(PAD, 0))
        self.videos = tk.Text(box, height=3, width=40)
        self.videos.grid(row=3, column=0, sticky="ew")
        ttk.Label(box, text="Empfänger").grid(row=4, column=0, sticky="w", pady=(PAD, 0))
        self.recipients = KeyChecklist(box)
        self.recipients.grid(row=5, column=0, sticky="w")
        ttk.Label(box, text="Signieren mit").grid(row=6, column=0, sticky="w", pady=(PAD, 0))
        self.challenge_signer = SignerChoice(box)
        self.challenge_signer.configure(width=45)
        self.challenge_signer.grid(row=7, column=0, sticky="ew")
        _file_row(
            box,
            8,
            "Speichern als (.asc)",
            self.challenge_target,
            lambda: _save_as(self, self.challenge_target, "Challenge speichern"),
        )
        ttk.Checkbutton(box, text="zusätzlich als QR-Code-Bild (.png)", variable=self.challenge_png).grid(
            row=10, column=0, sticky="w", pady=(PAD, 0)
        )
        self.challenge_button = ttk.Button(box, text="Challenge erstellen", command=self.start_challenge)
        self.challenge_button.grid(row=11, column=0, sticky="w", pady=PAD)
        ttk.Label(box, textvariable=self.challenge_result, wraplength=WRAP, justify="left").grid(
            row=12, column=0, sticky="w"
        )

    def _build_answer(self, box: ttk.LabelFrame) -> None:
        box.grid(row=1, column=1, sticky="nsew")
        box.columnconfigure(0, weight=1)
        self.message, self.message_result = tk.StringVar(self), tk.StringVar(self)
        self.response_target, self.response_result = tk.StringVar(self), tk.StringVar(self)
        self.response_png = tk.BooleanVar(self, value=True)
        _file_row(box, 0, "Nachricht (.asc oder QR-Code-Bild .png)", self.message, self._browse_message)
        self.open_button = ttk.Button(box, text="Öffnen", command=self.start_open)
        self.open_button.grid(row=2, column=0, sticky="w", pady=PAD)
        ttk.Label(box, textvariable=self.message_result, wraplength=WRAP, justify="left").grid(
            row=3, column=0, sticky="w"
        )
        self.entries = tk.Listbox(box, height=5, exportselection=False)
        self.entries.grid(row=4, column=0, sticky="ew", pady=(PAD, 0))
        ttk.Label(box, text="Antwort signieren mit").grid(row=5, column=0, sticky="w", pady=(PAD, 0))
        self.response_signer = SignerChoice(box)
        self.response_signer.configure(width=45)
        self.response_signer.grid(row=6, column=0, sticky="ew")
        _file_row(
            box,
            7,
            "Antwort speichern als (.asc)",
            self.response_target,
            lambda: _save_as(self, self.response_target, "Response speichern"),
        )
        ttk.Checkbutton(box, text="zusätzlich als QR-Code-Bild (.png)", variable=self.response_png).grid(
            row=9, column=0, sticky="w", pady=(PAD, 0)
        )
        self.response_button = ttk.Button(
            box, text="Auswahl als Response speichern", command=self.start_response, state="disabled"
        )
        self.response_button.grid(row=10, column=0, sticky="w", pady=PAD)
        ttk.Label(box, textvariable=self.response_result, wraplength=WRAP, justify="left").grid(
            row=11, column=0, sticky="w"
        )

    @property
    def busy(self) -> bool:
        return self.job is not None and self.job.running

    def set_keys(self, rows: list[KeyRow]) -> None:
        self.recipients.set_rows(rows)
        self.challenge_signer.set_rows(rows)
        self.response_signer.set_rows(rows)

    def _browse_directory(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Ordner mit den angebotenen Dateien")
        if chosen:
            self.directory.set(chosen)
            if not self.challenge_target.get():
                self.challenge_target.set(str(Path(chosen).parent / "challenge.asc"))

    def _browse_message(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Nachricht öffnen",
            filetypes=[("Nachricht oder QR-Code", "*.asc *.png"), ("Alle Dateien", "*.*")],
        )
        if chosen:
            self.message.set(chosen)

    def _confirm(self, target: Path, png: bool) -> bool | None:
        """None = abbrechen, sonst ob ueberschrieben werden darf."""
        existing = self._presenter.existing(target, png)
        if not existing:
            return False
        names = ", ".join(p.name for p in existing)
        return True if self._ask("Überschreiben?", f"{names} gibt es schon. Überschreiben?") else None

    def _run(self, task: Callable[[Progress], Any], result: tk.StringVar, done: Callable[[Any], str]) -> None:
        def on_event(event: Event) -> None:
            if isinstance(event, Finished):
                result.set(done(event.result))
            elif isinstance(event, Failed):
                result.set(event.message)
            elif isinstance(event, WasCancelled):
                result.set("Abgebrochen.")
            if isinstance(event, Finished | Failed | WasCancelled):
                self._status.set("Bereit")

        result.set("")
        self._status.set("Handshake läuft …")
        self.job = Job(task)
        watch(self, self.job, on_event)

    def start_challenge(self) -> None:
        presenter = self._presenter  # Task erfasst kein Widget (Tk nie im Worker-Thread freigeben)
        request = ChallengeRequest(
            directory=Path(self.directory.get().strip()),
            videos=tuple(self.videos.get("1.0", "end").splitlines()),
            recipients=tuple(self.recipients.checked()),
            signer=self.challenge_signer.fingerprint(),
            target=Path(self.challenge_target.get().strip()),
            png=self.challenge_png.get(),
        )
        overwrite = self._confirm(request.target, request.png)
        if overwrite is None:
            return

        def done(result: SealedResult) -> str:
            return result.summary

        self._run(lambda p: presenter.create_challenge(request, p, overwrite), self.challenge_result, done)

    def start_open(self) -> None:
        presenter = self._presenter  # Task erfasst kein Widget (Tk nie im Worker-Thread freigeben)
        path = Path(self.message.get().strip())
        self._opened = None
        self.entries.delete(0, "end")
        self.response_button.state(["disabled"])
        self._run(lambda p: presenter.open_message(path, p), self.message_result, self._show_message)

    def _show_message(self, opened: OpenedMessage) -> str:
        self._opened = opened
        fingerprint = format_fingerprint(opened.signer_fingerprint)
        sender = f"Signiert von: {opened.signer_name}\nFingerabdruck: {fingerprint}"
        if opened.kind != CHALLENGE:
            return f"Response – gewählt wurde: „{opened.selection}“\n{sender}"
        for entry in opened.entries:
            self.entries.insert("end", entry)
        if not self.response_target.get():
            self.response_target.set(str(opened.path.with_name("response.asc")))
        self.response_button.state(["!disabled"])
        return f"Challenge mit {len(opened.entries)} Einträgen – bitte einen wählen.\n{sender}"

    def start_response(self) -> None:
        presenter = self._presenter  # Task erfasst kein Widget (Tk nie im Worker-Thread freigeben)
        if self._opened is None:
            return
        selected = self.entries.curselection()  # type: ignore[no-untyped-call]
        request = ResponseRequest(
            message=self._opened,
            index=int(selected[0]) if selected else -1,
            signer=self.response_signer.fingerprint(),
            target=Path(self.response_target.get().strip()),
            png=self.response_png.get(),
        )
        overwrite = self._confirm(request.target, request.png)
        if overwrite is None:
            return

        def done(result: SealedResult) -> str:
            return result.summary

        self._run(lambda p: presenter.create_response(request, p, overwrite), self.response_result, done)
