# Externe Abhängigkeiten – Revival_2026 (QR-Code-Videokanal)

---

## Laufzeit-Pakete (pip)

Quelle: `pyproject.toml` (`dependencies` und Extras `jit`, `video`, `crypto`, `youtube`, `all`; Pakete
`qrcodegenmod` seit I2, `qrvideo` seit I4/I7). Exakte Stände stehen in `uv.lock`. `legacy/poc/` importiert zusätzlich
die Altpakete der Thesis (u. a. `pyzbar`, `youtube_dl`, `oauth2client`); sie sind nicht Teil von `pyproject.toml`.

| Paket | Version | Zweck | Risiko bei Ausfall |
|-------|---------|-------|-------------------|
| `numpy` | `≥ 2.0` (gemessen 2.5.4) | Matrizen, Lookup-Tabellen, `packbits`, Frame-Zusammenbau | Bibliothek und PoC laufen nicht |
| `python-gnupg` | `≥ 0.5.4` (gelockt 0.5.7), Extra `crypto` | Wrapper um das `gpg`-Binary: verschlüsseln, signieren, entschlüsseln, Trust prüfen | PoC kann nichts ver-/entschlüsseln |
| `imageio-ffmpeg` | `≥ 0.5` (gelockt 0.6.0, FFmpeg 7.1 gebündelt), Extra `video` | ffmpeg-Pipe zum Schreiben und Lesen der MP4 | keine Videoerzeugung/-analyse |
| `yt-dlp` | `≥ 2026.7.4` (gelockt 2026.10.21), Extra `youtube` | Download der Videos (ersetzt das tote `youtube_dl`) | kein Download |
| `google-api-python-client` + `google-auth-oauthlib` | `≥ 2.150` / `≥ 1.2` (gelockt 1.5.0), Extra `youtube` | YouTube-Upload (ersetzt `oauth2client`) | kein Upload; lokaler Roundtrip bleibt möglich |

### Optionale pip-Pakete

| Paket | Version | Zweck | Ohne dieses Paket |
|-------|---------|-------|-------------------|
| `numba` | `≥ 0.60` (gemessen 0.68), Extra `jit` | JIT für Reed-Solomon und Masken-Bewertung | NumPy-Fallback, langsamer, bit-identisch |

---

## Entwicklungs-/Test-Pakete

| Paket | Zweck |
|-------|-------|
| `pytest` | Test-Framework |
| `pytest-cov` | Coverage-Messung (≥ 80 %) |
| `qrcodegen` (`==1.8.0`, nayuki) | Testorakel: Referenzimplementierung für Bit-Gleichheit |
| `ruff` | Linter + Formatter |
| `mypy` | Typprüfung (strict, Gate 3); `src/qrcodegenmod/py.typed` markiert das Paket als typisiert |
| `numba` | in der Dev-Gruppe, damit Tests den JIT-Pfad abdecken |
| `import-linter` (`>=2.15`) | Schichtregel als Gate 5 (`lint-imports`, Contract in `pyproject.toml`), seit I25; zieht grimp, click, rich (mit markdown-it-py, mdurl, pygments) und typing-extensions nach |
| `pillow` (nur ad hoc, **keine** Projektabhängigkeit) | Bildschirmaufnahme in `tools/screenshots.py` (seit I33j), geladen per `uv run --with pillow`; nicht in `pyproject.toml`/`uv.lock` |

---

## Externe Binaries

| Tool | Zweck | Fallback bei Abwesenheit | Verfügbarkeits-Prüfung |
|------|-------|--------------------------|------------------------|
| `gpg` (GnuPG 2.x) | Kryptografie (über `python-gnupg`, `qrvideo.crypto`) | keiner — Pflicht für `send`/`receive`/`keys` | seit I7 `qrvideo.crypto.find_gpg_binary` (Reihenfolge unten); Legacy: harter Windows-Pfad |
| `ffmpeg` | Video-Encoding/-Decoding (libx264, 30 fps) | keiner — Pflicht für Videoerzeugung | über `imageio-ffmpeg` mitgeliefert, überschreibbar mit `IMAGEIO_FFMPEG_EXE` |
| `zbar` (DLL/Shared Library) | QR-Dekodierung für `pyzbar` — nur Legacy-PoC | `qrvideo` braucht es nicht (eigener Reader seit I6, ADR-001) | Import von `pyzbar` schlägt fehl |

### Lookup-Reihenfolge für Binaries (Ist-Stand seit I7)

`gpg` — `qrvideo.crypto.find_gpg_binary()`:

1. Umgebungsvariable `QRVIDEO_GPG` (muss auf eine Datei zeigen, sonst `GpgError`)
2. unter Windows die GnuPG-Installation (`C:\Program Files\GnuPG\bin\gpg.exe`, dann `Program Files (x86)`)
3. `gpg` im PATH — außer der gpg aus Git for Windows (Pfad mit `\git\usr\bin\`, eigener Schlüsselbund)
4. sonst `GpgError("gpg nicht gefunden …")`

`ffmpeg` — `imageio-ffmpeg` (`IMAGEIO_FFMPEG_EXE`, sonst das gebündelte Binary).

Ein Projektordner `tools/bin/` für lokale Binaries wird nicht verwendet (`tools/` enthält `git-hooks/` und Python-Werkzeuge, siehe `PROJECT_LAYOUT.md`).

---

## Externe Services

| Service | Adresse | Zweck | Fallback |
|---------|---------|-------|---------|
| YouTube Data API v3 | Google-API (OAuth 2.0) | Upload der Videos als „unlisted" (`qrvideo upload`, seit I7; Live-Test fehlt, `BACKLOG.md`) | lokaler Dateiaustausch der MP4 |
| YouTube (Web) | Video-URL / ID | Download der Videos per `yt-dlp` | lokaler Dateiaustausch der MP4 |

Die Bibliothek `qrcodegenmod` greift nicht aufs Netz.

---

## Systemabhängigkeiten

| Ressource | Version / Pfad | Zweck |
|-----------|---------------|-------|
| Python | ≥ 3.11 (Entwicklung 3.13) | moderne Typannotationen, `tomllib`; Numba-/NumPy-2-Wheels |
| venv | `%LOCALAPPDATA%\venvs\revival_2026` (via `UV_PROJECT_ENVIRONMENT`) | außerhalb des NextCloud-Ordners, damit der Sync die venv nicht erfasst |
| Tk 8.6 (`tkinter`) | in den python.org- und uv-Builds für Windows enthalten | GUI `qrvideo-gui` (seit I20b, ADR-004); ohne Tk startet nur die GUI nicht |
| PoC-Arbeitsordner | `files_*` relativ zum Arbeitsverzeichnis (Legacy) | Ein-/Ausgang verschlüsselter Dateien, Videos, Challenge/Response-PNGs |

---

## Upgrade-Hinweise

- **numpy / numba:** Numba unterstützt jeweils nur ein Fenster von NumPy- und Python-Versionen — beide gemeinsam
  heben und danach Bit-Gleichheitstests + `bench/` laufen lassen.
- **qrcodegen (Orakel):** fest gepinnt; ein Update kann Ausgaben ändern (andere Maskenwahl o. Ä.) — nur bewusst heben.
- **yt-dlp:** wird häufig aktualisiert, weil YouTube sich ändert; regelmäßig heben.
- **Externe Binaries:** GnuPG-Statusausgaben (von `python-gnupg` geparst) und ffmpeg-Parameter können sich bei
  Major-Updates ändern — Roundtrip-Test nach jedem Update.
