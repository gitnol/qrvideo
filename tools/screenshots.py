"""Screenshots der GUI je Sprache für die Bedienungsanleitungen, reproduzierbar (ADR-006, I33j).

    uv run --with pillow python tools/screenshots.py [--lang de en es] [--workdir C:\\Temp\\qrvideo-demo]

Ablauf je Sprache: zwei Demo-Schlüsselbunde („Alice/Bob Beispiel“, `@example.test`, ohne
Passphrase, gegenseitig voll vertraut) im Arbeitsordner außerhalb des Repos; die echte GUI
(`MainWindow`) mit eigenem Schlüsselbund sendet, empfängt und führt den Handshake mit echtem
GnuPG, ffmpeg und Prozess-Pool aus; Aufnahme des Fensters in natürlicher Größe mit Pillow
`ImageGrab` (keine Projektabhängigkeit). Danach gpg-agents beenden und den Arbeitsordner löschen.
Der Arbeitsordner hat einen kurzen, neutralen Pfad, weil er in den Bildern steht.

Nur unter Windows erprobt; das Fenster liegt während der Aufnahme kurz im Vordergrund.
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import gnupg
from PIL import ImageGrab

from qrvideo.crypto import Crypto, find_gpg_binary
from qrvideo.i18n import SUPPORTED, set_language
from qrvideo_gui.app import MainWindow, _sharp_on_high_dpi
from qrvideo_gui.keys import KeyService

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
DEFAULT_WORKDIR = Path(r"C:\Temp\qrvideo-demo") if os.name == "nt" else Path("/tmp/qrvideo-demo")
TIMEOUT = 300.0
DWMWA_EXTENDED_FRAME_BOUNDS = 9  # Fensterrahmen ohne unsichtbaren Schatten (Windows 10+)

# Demo-Inhalte je Sprache: Nachname der Personen, Datei zum Senden, Eingangs- und Angebotsordner, Angebot
DEMO = {
    "de": (
        "Beispiel",
        "Quartalsbericht.xlsx",
        "Eingang",
        "Angebot",
        ("Messdaten_Oktober.csv", "Preisliste_2026.pdf", "Vertrag_Entwurf.docx"),
    ),
    "en": (
        "Example",
        "Quarterly_report.xlsx",
        "Inbox",
        "Offer",
        ("Measurements_October.csv", "Price_list_2026.pdf", "Contract_draft.docx"),
    ),
    "es": (
        "Ejemplo",
        "Informe_trimestral.xlsx",
        "Entrada",
        "Oferta",
        ("Mediciones_octubre.csv", "Lista_de_precios_2026.pdf", "Contrato_borrador.docx"),
    ),
}


@dataclass(frozen=True)
class Person:
    name: str
    home: Path
    fingerprint: str


def _new_person(binary: str, home: Path, name: str) -> tuple[Person, gnupg.GPG]:
    home.mkdir(parents=True)
    gpg = gnupg.GPG(gpgbinary=binary, gnupghome=str(home))
    params = gpg.gen_key_input(
        key_type="EDDSA",
        key_curve="ed25519",
        subkey_type="ECDH",
        subkey_curve="cv25519",
        name_real=name,
        name_email=f"{name.split()[0].lower()}@example.test",
        no_protection=True,
    )
    return Person(name, home, str(gpg.gen_key(params).fingerprint)), gpg


def _trust(binary: str, me: Person, my_gpg: gnupg.GPG, other: Person, other_gpg: gnupg.GPG) -> None:
    """Fremden Schlüssel importieren, beglaubigen und voll vertrauen (wie in Kleopatra)."""
    my_gpg.import_keys(other_gpg.export_keys(other.fingerprint))
    subprocess.run(
        [binary, "--homedir", str(me.home), "--batch", "--yes", "--quick-sign-key", other.fingerprint],
        check=True,
        capture_output=True,
    )
    my_gpg.trust_keys(other.fingerprint, "TRUST_FULLY")


def _pump(root: tk.Tk, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not done():
        if time.monotonic() > deadline:
            raise TimeoutError("GUI did not finish in time")
        root.update()
        time.sleep(0.02)
    for _ in range(10):  # letzte Zeichenvorgänge
        root.update()
        time.sleep(0.02)


def _window_bounds(root: tk.Tk) -> tuple[int, int, int, int]:
    root.update_idletasks()
    hwnd = int(root.wm_frame(), 16)
    rect = (ctypes.c_long * 4)()
    windll = getattr(ctypes, "windll", None)
    if windll is not None:
        windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, rect, ctypes.sizeof(rect))
        return rect[0], rect[1], rect[2], rect[3]
    x, y = root.winfo_rootx(), root.winfo_rooty()
    return x, y, x + root.winfo_width(), y + root.winfo_height()


def _backdrop(root: tk.Tk, bounds: tuple[int, int, int, int]) -> tk.Toplevel:
    """Weiße Fläche hinter dem Fenster: In den runden Ecken und am Rand stünde sonst der Desktop im Bild."""
    left, top, right, bottom = bounds
    backdrop = tk.Toplevel(root, background="white")
    backdrop.overrideredirect(True)
    margin = 16
    # Toplevel-Geometrie in Tk-Pixeln; mit DPI-Bewusstsein sind das physische Pixel wie bei `bounds`
    width, height = right - left + 2 * margin, bottom - top + 2 * margin
    backdrop.geometry(f"{width}x{height}+{left - margin}+{top - margin}")
    backdrop.attributes("-topmost", True)
    return backdrop


def _capture(root: tk.Tk, target: Path) -> None:
    _pump(root, lambda: True)
    backdrop = _backdrop(root, _window_bounds(root))
    _pump(root, lambda: True)
    root.attributes("-topmost", True)
    root.lift()
    _pump(root, lambda: True)
    time.sleep(0.5)  # Fensterverwaltung zeichnet Rahmen und Schatten nach
    target.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=_window_bounds(root), all_screens=True).save(target)
    root.attributes("-topmost", False)
    backdrop.destroy()
    print(f"{target.relative_to(ROOT)}")


def _window(person: Person, binary: str) -> tuple[tk.Tk, MainWindow]:
    root = tk.Tk()
    root.geometry("+40+40")  # nur die Position; die Größe bestimmt der Inhalt
    window = MainWindow(
        root, KeyService(lambda: Crypto(homedir=person.home, binary=binary)), ask=lambda t, q: True
    )
    _pump(root, lambda: bool(window.send_tab.signer_fingerprint()))
    return root, window


def _shoot_language(lang: str, binary: str, work: Path, out: Path) -> None:
    surname, document, inbox_name, offer_name, offered = DEMO[lang]
    set_language(lang)
    alice, alice_gpg = _new_person(binary, work / "gnupg-alice", f"Alice {surname}")
    bob, bob_gpg = _new_person(binary, work / "gnupg-bob", f"Bob {surname}")
    _trust(binary, alice, alice_gpg, bob, bob_gpg)
    _trust(binary, bob, bob_gpg, alice, alice_gpg)
    source = work / document
    source.write_bytes(os.urandom(30_000))
    offer = work / offer_name
    offer.mkdir()
    for name in offered:
        (offer / name).write_bytes(os.urandom(1000))
    inbox = work / inbox_name
    inbox.mkdir()

    root, window = _window(alice, binary)  # Alice: Schlüssel, Senden, Angebot
    window.notebook.select(window.keys_tab)  # type: ignore[no-untyped-call]
    _capture(root, out / "keys.png")
    tab = window.send_tab
    window.notebook.select(tab)  # type: ignore[no-untyped-call]
    tab.choose_source(source)
    tab.recipients.set_checked([bob.fingerprint])
    tab.start_send()
    _pump(root, lambda: not tab.busy and bool(tab.result.get()))
    video = Path(tab.target.get())
    _capture(root, out / "send-done.png")
    hs = window.handshake_tab
    window.notebook.select(hs)  # type: ignore[no-untyped-call]
    hs.directory.set(str(offer))
    hs.recipients.set_checked([bob.fingerprint])
    hs.challenge_target.set(str(work / "challenge.asc"))
    hs.start_challenge()
    _pump(root, lambda: not hs.busy and bool(hs.challenge_result.get()))
    _capture(root, out / "handshake-offer.png")
    root.destroy()
    gc.collect()  # Tk-Variablen jetzt im Tk-Thread freigeben, nicht im Worker (wie tests/conftest.py)

    root, window = _window(bob, binary)  # Bob: Empfangen, Angebot öffnen und Eintrag wählen
    receive = window.receive_tab
    window.notebook.select(receive)  # type: ignore[no-untyped-call]
    receive.source.set(str(video))
    receive.output.set(str(inbox))
    receive.start_receive()
    _pump(root, lambda: not receive.busy and bool(receive.result.get()))
    _capture(root, out / "receive-done.png")
    hs = window.handshake_tab
    window.notebook.select(hs)  # type: ignore[no-untyped-call]
    hs.message.set(str(work / "challenge.png"))
    hs.start_open()
    _pump(root, lambda: not hs.busy and hs.entries.size() == len(offered))
    hs.entries.selection_set(1)
    _capture(root, out / "handshake-answer.png")
    root.destroy()
    gc.collect()  # Tk-Variablen jetzt im Tk-Thread freigeben, nicht im Worker (wie tests/conftest.py)


def _cleanup(binary: str, work: Path) -> None:
    gpgconf = Path(binary).with_name("gpgconf.exe" if os.name == "nt" else "gpgconf")
    for home in work.glob("gnupg-*"):
        subprocess.run(
            [str(gpgconf), "--homedir", str(home), "--kill", "all"], check=False, capture_output=True
        )
    shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", nargs="+", choices=SUPPORTED, default=list(SUPPORTED))
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    args = parser.parse_args(argv)
    if args.workdir.exists():
        parser.error(f"{args.workdir} exists; choose an empty location (it is deleted afterwards)")
    binary = find_gpg_binary()
    _sharp_on_high_dpi()
    try:
        for lang in args.lang:
            work = args.workdir / lang
            work.mkdir(parents=True)
            try:
                _shoot_language(lang, binary, work, IMAGES / lang)
            finally:
                _cleanup(binary, work)
    finally:
        shutil.rmtree(args.workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":  # Pflicht: der Prozess-Pool des Encoders importiert das Hauptmodul neu (spawn)
    sys.exit(main(sys.argv[1:]))
