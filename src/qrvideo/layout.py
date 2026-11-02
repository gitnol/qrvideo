"""Frame-Geometrie der Thesis: 1920x1080, 3 Reihen x 5 QR-Codes Version 40, Skalierung 2, Rand 2.

Die Thesis haengte 15 QR-Bilder (je 362 px) aneinander, teilte sie in 3 Reihen, schnitt rundum
3 px ab und fuellte rechts weiss auf (POC.py erstelle_gesamtframe_v2). Damit beginnt das Modulgitter
von Slot (r, c) bei Pixel (1 + 362 r, 1 + 362 c); analyze_video.py las genau dort.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

U8 = npt.NDArray[np.uint8]
Bool = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class FrameLayout:
    width: int = 1920
    height: int = 1080
    rows: int = 3
    cols: int = 5
    modules: int = 177  # Version 40
    scale: int = 2
    border: int = 2
    crop: int = 3
    threshold: int = 128  # Thesis: Modul-Mittelwert < 128 => dunkel

    @property
    def slots(self) -> int:
        return self.rows * self.cols

    @property
    def tile(self) -> int:
        """Kantenlaenge eines QR-Bildes inklusive Rand in Pixeln (362)."""
        return (self.modules + 2 * self.border) * self.scale

    def module_origin(self, slot: int) -> tuple[int, int]:
        """Pixel (y, x) des ersten Moduls von Slot `slot` im fertigen Frame."""
        r, c = divmod(slot, self.cols)
        offset = self.border * self.scale - self.crop
        return r * self.tile + offset, c * self.tile + offset

    def compose(self, tiles: list[U8 | None]) -> U8:
        """Setzt bis zu `slots` QR-Bilder (None = weisser Slot) zu einem Frame zusammen."""
        if len(tiles) > self.slots:
            raise ValueError(f"At most {self.slots} QR codes per frame")
        canvas = np.full((self.rows * self.tile, self.width + self.crop), 255, dtype=np.uint8)
        for slot, tile in enumerate(tiles):
            if tile is None:
                continue
            if tile.shape != (self.tile, self.tile):
                raise ValueError(f"QR image has {tile.shape}, expected {(self.tile, self.tile)}")
            r, c = divmod(slot, self.cols)
            canvas[r * self.tile : (r + 1) * self.tile, c * self.tile : (c + 1) * self.tile] = tile
        return canvas[self.crop : self.crop + self.height, self.crop : self.crop + self.width].copy()

    def sample(self, frame: U8) -> tuple[Bool, npt.NDArray[np.float64]]:
        """Alle Slots abtasten: (dunkel-Matrix [slots, 177, 177], mittlere Helligkeit je Slot)."""
        if frame.shape != (self.height, self.width):
            raise ValueError(f"Frame has {frame.shape}, expected {(self.height, self.width)}")
        n, s = self.modules, self.scale
        out = np.empty((self.slots, n, n), dtype=bool)
        brightness = np.empty(self.slots, dtype=np.float64)
        for slot in range(self.slots):
            y, x = self.module_origin(slot)
            crop = frame[y : y + n * s, x : x + n * s].reshape(n, s, n, s)
            means = crop.mean(axis=(1, 3))
            out[slot] = means < self.threshold
            brightness[slot] = float(means.mean())
        return out, brightness


THESIS_LAYOUT = FrameLayout()
