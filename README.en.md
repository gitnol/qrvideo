# Thesis Revival 2026

*Deutsche Fassung: [README.md](README.md) · Versión en español: [README.es.md](README.es.md)*

Revival of a 2019 bachelor thesis on exchanging data through videos made of QR codes:
encrypt files with GnuPG, encode them as a video of QR codes, transfer it via YouTube and recover the file.

**Getting started:** installation and step-by-step use, with screenshots, in the
[User Guide](docs/USER_GUIDE.md).

| Part | Location |
|---|---|
| Modern library `qrcodegenmod` (Python ≥ 3.11) | `src/qrcodegenmod/` |
| Transfer tool `qrvideo` (command `qrvideo`) | `src/qrvideo/` |
| Desktop interface (command `qrvideo-gui`) | `src/qrvideo_gui/` |
| Thesis code from 2019 (unchanged) | `legacy/` |
| User guide | [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) (German: [`docs/BEDIENUNGSANLEITUNG.md`](docs/BEDIENUNGSANLEITUNG.md), Spanish: [`docs/GUIA_DE_USUARIO.md`](docs/GUIA_DE_USUARIO.md)) |
| Architecture, decisions (ADR), threat model (German) | [`docs/architecture/`](docs/architecture/), [`docs/security/`](docs/security/THREAT_MODEL.md) |

## Thanks to Project Nayuki

At the heart of this project is `qrcodegenmod`, a fork of the excellent
[**QR Code generator library**](https://github.com/nayuki/QR-Code-generator) by
[Project Nayuki](https://www.nayuki.io/page/qr-code-generator-library) (MIT licence), base commit
[`6e088f7`](https://github.com/nayuki/QR-Code-generator/commit/6e088f7) from 2019-09-13.

Nayuki's library is a model of how to implement a standard: complete according to ISO/IEC 18004, with identical
behaviour across several languages, free of dependencies and written so clearly that every step (segments,
Reed-Solomon, masks, penalty scores) can be followed directly. That clarity is what made the 2019 thesis possible
in the first place – its clean foundation allowed the optimisations to be added in a targeted way. The 2026
modernisation relies on it as well: the official `qrcodegen` 1.8.0 serves as the test oracle, and `qrcodegenmod`
produces bit-identical QR codes for every version, error-correction level and mask.

Many thanks to Nayuki for this great work and for making it freely available.

The project was developed following an internal documentation process (status, reflections, changelog). Those
project logs are not part of this repository; references to them in `docs/` point to that internal material.

## Quick start

The virtual environment lives outside the repository (useful if the folder is synchronised):

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\venvs\revival_2026"
uv sync --all-extras
uv run pytest
uv run python bench/bench_qrcode.py
```

```python
import qrcodegenmod as q

qr = q.QrCode.encode_text("Hello thesis", q.Ecc.LOW)
img = qr.to_image(scale=2, border=2)  # uint8, dark = 0, light = 255
```

## Desktop interface (`qrvideo-gui`)

For everyone who prefers not to use the command line: a window with the tabs Send, Receive, Handshake and Keys,
in English, German or Spanish (menu “Language”, `--lang`). Step by step, including the GnuPG setup:
[User Guide](docs/USER_GUIDE.md).

```powershell
uv run qrvideo-gui
```

## Transferring files (`qrvideo`)

Requirements: GnuPG ≥ 2.4.9 (on Windows: Gpg4win), trusted keys for sender and recipient.
gpg-agent asks for the passphrase; use `QRVIDEO_PASSPHRASE` only for unattended runs. Output language:
`--lang de|en|es` or `QRVIDEO_LANG`, otherwise the system language.

```powershell
uv run qrvideo keys                                              # trusted keys
uv run qrvideo send report.xlsx -r <KeyID> --sign <KeyID> -o report.mp4   # format v3: ECC L, 10 % parity
uv run qrvideo send report.xlsx -r <KeyID> --sign <KeyID> -o report.mp4 --parity 0 --ecc M  # format v2
uv run qrvideo upload report.mp4 --client-secrets client_secret.json   # unlisted
uv run qrvideo download https://youtu.be/<ID> -d inbox
uv run qrvideo download https://youtu.be/<ID> -d inbox --cookies-from-browser firefox   # private video
uv run qrvideo upload report.mp4 --channel folder --folder \\server\exchange   # shared folder instead of YouTube
uv run qrvideo download qrvideo-<8 hex>.mp4 --channel folder --folder \\server\exchange -d inbox
uv run qrvideo receive inbox/<ID>.mp4 -o inbox   # file gets the sender's name back (name travels encrypted)
uv run qrvideo decode thesis_video_2019.mp4 -o old.pgp --legacy  # videos in the thesis format
uv run qrvideo challenge offer/ -r <KeyID> --sign <KeyID> -o challenge.asc --png challenge.png
uv run qrvideo respond challenge.png --select 0 --sign <KeyID> -o response.asc
```

| Metric (measured 2026-10-26) | Thesis 2019 | 2026 |
|---|---|---|
| Generate a QR code (V40, 2100 characters) | 3.32 ms | 0.25 ms |
| Payload bytes per QR code (ECC M) | 1575 (Base64) | 2331 (binary) |
| Fault tolerance across frames | none | default (ECC L, 10 % parity): 1 lost frame per 10 frames, with an 8.9 % shorter video than v2 with ECC M |
| Read the thesis' original YouTube video | pyzbar + correction | own reader, 0 failures, 1.4 s |

Note for your own scripts on Windows: the encoder uses a process pool, so the calling script needs
`if __name__ == "__main__":`.

## Languages

The desktop interface and the command line speak English, German and Spanish. The source strings in the code are
English; each language is a `gettext` catalog in `src/qrvideo/locale/<language>/LC_MESSAGES/qrvideo.po`
(ADR-006). A test checks that every string is translated in every language, that the `{name}` placeholders match
and that the `.mo` files are up to date.

Adding a language (e.g. French, `fr`):

1. Add `"fr"` to `SUPPORTED` (`src/qrvideo/i18n.py`) and `LANGUAGES` (`tools/i18n_catalog.py`) and its name to
   `LANGUAGE_NAMES` (`src/qrvideo_gui/app.py`); for numbers, an entry in `_NUMBERS` (`i18n.py`).
2. `uv run python tools/i18n_catalog.py update` creates `fr/LC_MESSAGES/qrvideo.po` with all strings empty.
3. Translate the `.po` (by hand or with Poedit) and run `update` again; it compiles the `.mo`.
4. `uv run pytest tests/test_i18n_catalog.py` reports what is missing.
5. Screenshots: `uv run --with pillow python tools/screenshots.py --lang fr` (first add demo data for the language
   to `DEMO`).

The Spanish texts have not been reviewed by a native speaker; corrections to the `.po` file are welcome.
