"""Reiter „Empfangen“: Kanal, Video oder Verweis, Ausgabeordner, Ergebnis und Absender (Logik: receive.py)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from qrvideo.i18n import N_, _, format_number

from .jobs import Event, Failed, Finished, Job, ProgressEvent, WasCancelled
from .keys import format_fingerprint
from .receive import ReceivePresenter, ReceiveRequest, ReceiveResult
from .widgets import PAD, WRAP, ProgressPanel, open_folder, watch

# Texte per `N_` markiert, uebersetzt beim Gebrauch (ADR-006)
CHANNELS = (("youtube", N_("YouTube")), ("folder", N_("Shared folder")))
SOURCE_HINTS = {
    "youtube": N_("Choose a video file or paste a YouTube link (e.g. https://youtu.be/…)."),
    "folder": N_("Choose a video file or enter a file name from the channel folder."),
}
BROWSER_HINT = N_("optional, e.g. firefox or chrome:Profile 1")  # nur falls YouTube eine Anmeldung verlangt
CHECK_HINT = N_("If in doubt, compare the fingerprint with the sender by phone.")


def _default_output() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def _summary(result: ReceiveResult) -> str:
    text = _(
        "Done: “{name}” saved ({size} bytes).\nSigned by: {signer}\nFingerprint: {fingerprint}\n"
        "{frames} frames, {qr} QR codes read, {unreadable} unreadable."
    )
    return text.format(
        name=result.target.name,
        size=format_number(result.size),
        signer=result.signer_name,
        fingerprint=format_fingerprint(result.signer_fingerprint),
        frames=format_number(result.frames),
        qr=format_number(result.qr_codes),
        unreadable=format_number(result.unreadable),
    )


class ReceiveTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, presenter: ReceivePresenter, status: tk.StringVar) -> None:
        super().__init__(parent, padding=PAD)
        self._presenter, self._status = presenter, status
        self.job: Job[Any] | None = None
        self._done_path: Path | None = None
        self.source, self.result = tk.StringVar(self), tk.StringVar(self)
        self.output = tk.StringVar(self, value=str(_default_output()))
        self.channel, self.folder, self.browser = (
            tk.StringVar(self, value="youtube"),
            tk.StringVar(self),
            tk.StringVar(self),
        )
        self.columnconfigure(1, weight=1)

        self._step(0, _("1. Channel"))
        choice = ttk.Frame(self)
        choice.grid(row=0, column=1, sticky="w", pady=PAD)
        for value, text in CHANNELS:
            ttk.Radiobutton(choice, text=_(text), value=value, variable=self.channel).pack(
                side="left", padx=(0, PAD)
            )
        self.browser_row, self.folder_row = ttk.Frame(self), ttk.Frame(self)
        ttk.Label(self.browser_row, text=_("Browser sign-in:")).pack(side="left")
        ttk.Entry(self.browser_row, textvariable=self.browser, width=24).pack(side="left", padx=PAD)
        ttk.Label(self.browser_row, text=_(BROWSER_HINT), foreground="#555").pack(side="left")
        ttk.Label(self.folder_row, text=_("Channel folder:")).pack(side="left")
        ttk.Entry(self.folder_row, textvariable=self.folder).pack(
            side="left", fill="x", expand=True, padx=PAD
        )
        ttk.Button(self.folder_row, text=_("Choose folder …"), command=self._browse_folder).pack(side="left")
        for row in (self.browser_row, self.folder_row):
            row.grid(row=1, column=1, columnspan=2, sticky="ew")
        self._step(2, _("2. Video"))
        ttk.Entry(self, textvariable=self.source).grid(row=2, column=1, sticky="ew")
        ttk.Button(self, text=_("Choose file …"), command=self._browse_source).grid(row=2, column=2, padx=PAD)
        self.source_hint = ttk.Label(self, text=_(SOURCE_HINTS["youtube"]), foreground="#555")
        self.source_hint.grid(row=3, column=1, sticky="w")
        self._step(4, _("3. Output folder"))
        ttk.Entry(self, textvariable=self.output).grid(row=4, column=1, sticky="ew", pady=PAD)
        ttk.Button(self, text=_("Choose folder …"), command=self._browse_output).grid(
            row=4, column=2, padx=PAD
        )

        buttons = ttk.Frame(self)
        buttons.grid(row=5, column=1, sticky="w", pady=PAD)
        self.receive_button = ttk.Button(buttons, text=_("Receive"), command=self.start_receive)
        self.receive_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text=_("Cancel"), command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=PAD)
        self.progress = ProgressPanel(self)
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Label(self, textvariable=self.result, wraplength=WRAP, justify="left").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=PAD
        )
        self.open_button = ttk.Button(self, text=_("Open folder"), command=self._open, state="disabled")
        self.open_button.grid(row=8, column=0, sticky="w")
        self.hint = ttk.Label(self, text="", wraplength=WRAP, justify="left", foreground="#555")
        self.hint.grid(row=9, column=0, columnspan=3, sticky="w", pady=PAD)
        self.channel.trace_add("write", lambda *_: self._show_channel())
        self._show_channel()

    def _show_channel(self) -> None:
        """Nur die Felder des gewählten Kanals; der Hinweis unter dem Videofeld passt sich an (I32b)."""
        name = self.channel.get()
        self.folder_row.grid() if name == "folder" else self.folder_row.grid_remove()
        self.browser_row.grid() if name == "youtube" else self.browser_row.grid_remove()
        self.source_hint.configure(text=_(SOURCE_HINTS[name]) if name in SOURCE_HINTS else "")

    def _step(self, row: int, text: str) -> None:
        ttk.Label(self, text=text).grid(row=row, column=0, sticky="nw", padx=(0, PAD), pady=PAD)

    @property
    def busy(self) -> bool:
        return self.job is not None and self.job.running

    def _browse_source(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title=_("Choose video"),
            filetypes=[(_("MP4 video"), "*.mp4"), (_("All files"), "*.*")],
        )
        if chosen:
            self.source.set(chosen)

    def _browse_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title=_("Choose channel folder"))
        if chosen:
            self.folder.set(chosen)

    def _browse_output(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title=_("Choose output folder"))
        if chosen:
            self.output.set(chosen)

    def start_receive(self) -> None:
        folder = self.folder.get().strip()
        request = ReceiveRequest(
            self.source.get(),
            Path(self.output.get().strip()),
            channel=self.channel.get(),
            folder=Path(folder) if folder else None,
            browser=self.browser.get(),
        )
        try:
            self._presenter.target_for(request)  # Eingabe pruefen; ueberschrieben wird nie (I27b1)
        except ValueError as exc:
            self.result.set(str(exc))
            return
        presenter = self._presenter  # Task erfasst kein Widget: Tk-Objekte nie im Worker-Thread freigeben
        self.job = Job(lambda progress: presenter.run(request, progress))
        self._set_running(True)
        self.result.set("")
        self.hint.configure(text="")
        self._status.set(_("Receiving …"))
        watch(self, self.job, self._on_event)

    def cancel(self) -> None:
        if self.job is not None:
            self.job.cancel()
            self._status.set(_("Cancelling …"))

    def _set_running(self, running: bool) -> None:
        self.receive_button.state(["disabled"] if running else ["!disabled"])
        self.cancel_button.state(["!disabled"] if running else ["disabled"])
        self.open_button.state(["disabled"])

    def _on_event(self, event: Event) -> None:
        if isinstance(event, ProgressEvent):
            self.progress.show(event)
            return
        self._set_running(False)
        self.progress.reset()
        if isinstance(event, Finished):
            result: ReceiveResult = event.result  # type: ignore[assignment]
            self._done_path = result.target
            self.result.set(_summary(result))
            self.open_button.state(["!disabled"])
            self.hint.configure(text="\n".join(filter(None, [_(CHECK_HINT), result.warning])))
        elif isinstance(event, Failed):
            self.result.set(event.message)
        elif isinstance(event, WasCancelled):
            self.result.set(_("Cancelled. Nothing was saved."))
        self._status.set(_("Ready"))

    def _open(self) -> None:
        if self._done_path is not None:
            open_folder(self._done_path)
