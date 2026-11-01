"""Optionale Numba-Beschleunigung.

Ist Numba installiert, werden die Kernel kompiliert (mit Cache auf Platte, damit
Worker-Prozesse nicht jedes Mal neu kompilieren). Ohne Numba laufen dieselben
Funktionen als normales Python, und die Aufrufer nehmen NumPy-Varianten.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar, cast

F = TypeVar("F", bound=Callable[..., object])

_DISABLED = os.environ.get("QRCODEGENMOD_DISABLE_JIT", "") not in ("", "0")

_njit: Any = None
try:
    if _DISABLED:
        raise ImportError("JIT per QRCODEGENMOD_DISABLE_JIT abgeschaltet")
    from numba import njit

    _njit = njit
except ImportError:
    pass
HAVE_NUMBA = _njit is not None


def jit(fn: F) -> F:
    """Kompiliert fn mit Numba, falls verfuegbar; sonst unveraendert zurueck."""
    if _njit is None:
        return fn
    return cast(F, _njit(cache=True, nogil=True)(fn))
