"""Hauptfenster `qrvideo-gui`: Reiter und Statuszeile.

Start ueber das Console-Script `qrvideo-gui` oder `python -m qrvideo_gui`.

Unter Windows startet der Encoder einen Prozess-Pool (spawn): Die Kindprozesse importieren das Hauptmodul neu,
deshalb laeuft `main()` nur ueber den Einstiegspunkt bzw. hinter `if __name__ == "__main__":` (`__main__.py`).
"""

from __future__ import annotations

import argparse
import logging
import tkinter as tk
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .handshake import HandshakePresenter
from .handshake_view import HandshakeTab
from .jobs import Event, Failed, Finished, Job
from .keys import OWN_TRUST, TRUST_TEXT, KeyRow, KeyService, format_fingerprint
from .receive import ReceivePresenter
from .receive_view import ReceiveTab
from .send import SendPresenter
from .send_view import SendTab
from .widgets import watch

TITLE = "qrvideo – Dateien als QR-Code-Video übertragen"
PAD = 8
MIN_WIDTH, MIN_HEIGHT = 960, 700

KEYS_HELP = (
    "Hier stehen alle Schlüssel, denen Sie voll vertrauen. Nur an diese Personen können Sie senden, und nur "
    "Videos, die eine dieser Personen signiert hat, werden angenommen. Schlüssel importieren und beglaubigen "
    "Sie mit Kleopatra (Teil von Gpg4win); danach hier „Neu laden“."
)


class KeysTab(ttk.Frame):
    """Reiter „Schlüssel“: vertraute Schlüssel als Tabelle."""

    # Spaltenbreite = Breite eines typischen Inhalts in der aktuellen Schrift (feste Pixel waeren bei hoher
    # DPI zu schmal, Screenshot I24); der Name bekommt den Rest. Keine Spalte Schluessel-ID: sie ist das Ende
    # des Fingerabdrucks
    COLUMNS = (
        ("trust", "Vertrauen", TRUST_TEXT[OWN_TRUST]),
        ("fingerprint", "Fingerabdruck", format_fingerprint("0" * 40)),
    )

    def __init__(
        self,
        parent: tk.Misc,
        keys: KeyService,
        status: tk.StringVar,
        on_rows: Callable[[list[KeyRow]], None] = lambda rows: None,
    ) -> None:
        super().__init__(parent, padding=PAD)
        self._keys, self._status, self._on_rows = keys, status, on_rows
        ttk.Label(self, text=KEYS_HELP, wraplength=760, justify="left").pack(anchor="w", pady=(0, PAD))
        self.table = ttk.Treeview(self, columns=["name", *(c for c, _, _ in self.COLUMNS)], show="headings")
        self.table.heading("name", text="Name")
        self.table.column("name", width=120, stretch=True)
        font = tkfont.nametofont("TkDefaultFont")
        for column, text, sample in self.COLUMNS:
            self.table.heading(column, text=text)
            self.table.column(column, width=font.measure(sample) + 3 * PAD, stretch=False)
        self.table.pack(fill="both", expand=True)
        self.reload_button = ttk.Button(self, text="Neu laden", command=self.reload)
        self.reload_button.pack(anchor="e", pady=(PAD, 0))

    def reload(self) -> None:
        self.reload_button.state(["disabled"])
        self._status.set("Schlüssel werden geladen …")
        keys = self._keys  # Task erfasst kein Widget: Tk-Objekte nie im Worker-Thread freigeben
        watch(self, Job(lambda progress: keys.rows()), self._on_event)

    def _on_event(self, event: Event) -> None:
        if isinstance(event, Finished):
            rows: list[KeyRow] = event.result  # type: ignore[assignment]
            self.show(rows)
            self._on_rows(rows)
            self._status.set(f"{len(rows)} vertraute Schlüssel")
        elif isinstance(event, Failed):
            self._status.set(event.message)
        self.reload_button.state(["!disabled"])

    def show(self, rows: list[KeyRow]) -> None:
        self.table.delete(*self.table.get_children())
        for row in rows:
            self.table.insert("", "end", values=(row.name, row.trust, format_fingerprint(row.fingerprint)))


Ask = Callable[[str, str], bool]


class MainWindow:
    """Reiter Senden, Empfangen, Handshake, Schlüssel; die geladenen Schlüssel gehen an alle Reiter."""

    def __init__(self, root: tk.Tk | tk.Toplevel, keys: KeyService, ask: Ask = messagebox.askyesno) -> None:
        self._root, self._ask = root, ask
        root.title(TITLE)
        root.minsize(MIN_WIDTH, MIN_HEIGHT)
        root.protocol("WM_DELETE_WINDOW", self.close)
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        ttk.Style(root).configure("Treeview", rowheight=linespace + 6)  # sonst Unterlaengen abgeschnitten
        self.status = tk.StringVar(root, value="Bereit")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        ttk.Label(root, textvariable=self.status, anchor="w", relief="sunken", padding=(PAD, 2)).pack(
            fill="x", side="bottom"
        )
        self.send_tab = SendTab(self.notebook, SendPresenter(keys), self.status)
        self.receive_tab = ReceiveTab(self.notebook, ReceivePresenter(keys), self.status)
        self.handshake_tab = HandshakeTab(self.notebook, HandshakePresenter(keys), self.status)
        self.keys_tab = KeysTab(self.notebook, keys, self.status, on_rows=self._share_rows)
        self.notebook.add(self.send_tab, text="Senden")
        self.notebook.add(self.receive_tab, text="Empfangen")
        self.notebook.add(self.handshake_tab, text="Handshake")
        self.notebook.add(self.keys_tab, text="Schlüssel")
        self.keys_tab.reload()
        self._fit()

    def _share_rows(self, rows: list[KeyRow]) -> None:
        for tab in (self.send_tab, self.handshake_tab):
            tab.set_keys(rows)
        self._fit()  # Schlüsselnamen verbreitern die Empfängerlisten

    def _fit(self) -> None:
        """Mindestgröße = Platzbedarf des größten Reiters, höchstens der Bildschirm.

        Feste 960 × 700 reichten bei 150 % Anzeige nicht (Bedarf ca. 1380 × 790): Kleiner gezogen, schnitt das
        Fenster Beschriftungen und den Knopf „Auswahl als Response speichern“ ab.
        """
        root = self._root
        root.update_idletasks()
        width = min(max(MIN_WIDTH, root.winfo_reqwidth()), root.winfo_screenwidth())
        height = min(max(MIN_HEIGHT, root.winfo_reqheight()), root.winfo_screenheight())
        root.minsize(width, height)

    def close(self) -> bool:
        """Fenster schließen; läuft ein Vorgang, erst nachfragen und ihn abbrechen."""
        busy = [
            tab.job
            for tab in (self.send_tab, self.receive_tab, self.handshake_tab)
            if tab.job is not None and tab.job.running
        ]
        if busy and not self._ask("Vorgang läuft", "Ein Vorgang läuft noch. Abbrechen und beenden?"):
            return False
        for job in busy:
            job.cancel()
        self._root.destroy()
        return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="qrvideo-gui", description=TITLE)
    parser.add_argument(
        "--gnupghome", type=Path, help="eigener GnuPG-Schlüsselbund (Standard: der des Nutzers)"
    )
    return parser.parse_args(argv)


def _sharp_on_high_dpi() -> None:
    """Ohne DPI-Bewusstsein skaliert Windows das Fenster unscharf hoch."""
    import ctypes

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return
    try:
        windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        logging.getLogger(__name__).debug("DPI-Bewusstsein nicht verfügbar (Windows vor 8.1)")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from qrvideo.crypto import Crypto

    _sharp_on_high_dpi()
    root = tk.Tk()
    MainWindow(root, KeyService(lambda: Crypto(homedir=args.gnupghome)))
    root.mainloop()
    return 0
