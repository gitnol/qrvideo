"""qrcodegenmod - schneller QR-Code-Generator aus der Bachelor-Thesis 2019, modernisiert 2026.

Fork der QR Code generator library von Project Nayuki (MIT), Basis-Commit 6e088f7 (2019-09-13):
https://github.com/nayuki/QR-Code-generator - Dank an Nayuki fuer die klare, vorbildliche Umsetzung des
Standards, auf der diese Bibliothek aufbaut. Die offizielle Version `qrcodegen` ist in den Tests das Orakel
fuer Bit-Gleichheit.
"""

from ._jit import HAVE_NUMBA
from .qrcode import DataTooLongError, Ecc, QrCode
from .segment import Mode, QrSegment

__all__ = ["HAVE_NUMBA", "DataTooLongError", "Ecc", "Mode", "QrCode", "QrSegment"]
__version__ = "2.0.0.dev0"

# Einstellungen der Thesis: immer Version 40, feste Maske 1 (Aenderung 1), ECC LOW
THESIS_PARAMS = {"minversion": 40, "maxversion": 40, "mask": 1}
