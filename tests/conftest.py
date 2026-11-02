from __future__ import annotations

import gc
import random
import string
import tkinter as tk
from collections.abc import Iterator

import numpy as np
import pytest
import qrcodegen as ref

import qrcodegenmod as mod
from qrvideo.i18n import set_language

ECC_PAIRS = [
    (mod.Ecc.LOW, ref.QrCode.Ecc.LOW),
    (mod.Ecc.MEDIUM, ref.QrCode.Ecc.MEDIUM),
    (mod.Ecc.QUARTILE, ref.QrCode.Ecc.QUARTILE),
    (mod.Ecc.HIGH, ref.QrCode.Ecc.HIGH),
]

BASE64_ALPHABET = string.ascii_letters + string.digits + "+/="


def ref_matrix(qr: ref.QrCode) -> np.ndarray:
    n = qr.get_size()
    return np.array([[qr.get_module(x, y) for x in range(n)] for y in range(n)], dtype=bool)


def assert_same(ours: mod.QrCode, theirs: ref.QrCode) -> None:
    assert ours.get_version() == theirs.get_version()
    assert ours.get_mask() == theirs.get_mask()
    assert ours.get_error_correction_level().ordinal == theirs.get_error_correction_level().ordinal
    np.testing.assert_array_equal(ours.modules, ref_matrix(theirs))


@pytest.fixture(autouse=True)
def german_ui(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests laufen auf Deutsch (die Pruefungen vor ADR-006 nennen deutsche Texte), egal wie der Rechner
    eingestellt ist: `QRVIDEO_LANG` fuer die CLI, `set_language` fuer direkte Aufrufe.

    Andere Sprachen setzt ein Test selbst; danach wieder Deutsch, damit kein Test den naechsten bestimmt.
    """
    monkeypatch.setenv("QRVIDEO_LANG", "de")
    set_language("de")
    yield
    set_language("de")


@pytest.fixture
def rng() -> random.Random:
    return random.Random(20191218)  # fester Startwert, reproduzierbare Zufallstexte


def armored_chunk(rng: random.Random, length: int = 2100) -> str:
    """Text wie ein Chunk aus einer ASCII-armored PGP-Datei."""
    return "".join(rng.choice(BASE64_ALPHABET) for _ in range(length))


@pytest.fixture(scope="session")
def tk_session() -> Iterator[tk.Tk]:
    """Ein Tcl-Interpreter je Testlauf: ein zweites tk.Tk() findet unter Windows sporadisch tk.tcl nicht."""
    try:
        session = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"kein Display für Tk: {exc}")
    session.withdraw()
    yield session
    session.destroy()


@pytest.fixture
def root(tk_session: tk.Tk) -> Iterator[tk.Toplevel]:
    window = tk.Toplevel(tk_session)
    window.withdraw()
    yield window
    window.destroy()
    # Tk-Variablen des Fensters hängen in Referenzzyklen; räumt sie der zyklische GC später in einem
    # Worker-Thread ab, ruft Variable.__del__ Tcl aus dem falschen Thread ("main thread is not in main
    # loop") und blockiert den Job. Deshalb hier im Tk-Thread aufräumen.
    gc.collect()
