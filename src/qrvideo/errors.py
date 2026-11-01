"""Fehlerklassen von `qrvideo` ohne weitere Abhaengigkeiten.

Eigenes Modul, weil `container` und `erasure` dieselbe Klasse brauchen und sich sonst gegenseitig importierten
(bis I26 importierte `container.plan_frames_v3` deshalb `erasure` erst in der Funktion).
"""

from __future__ import annotations


class ContainerError(ValueError):
    """Kopf oder Nutzlast passen nicht zum Format v2 bzw. v3."""
