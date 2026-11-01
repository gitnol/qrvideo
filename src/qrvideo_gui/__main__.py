"""`python -m qrvideo_gui` - mit Guard, weil der Prozess-Pool unter Windows das Hauptmodul neu importiert."""

from __future__ import annotations

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
