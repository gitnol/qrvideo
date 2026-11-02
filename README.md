<p align="center"><img src="docs/images/logo.svg" width="112" alt="QR-Code-Video-Kanal: Logo"></p>

<h1 align="center">Thesis Revival 2026</h1>

<p align="center"><b>Dateien verschlüsselt als Video aus QR-Codes übertragen – über YouTube oder einen gemeinsamen Ordner.</b></p>

<p align="center">
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-%E2%89%A5%203.11-3776AB?logo=python&amp;logoColor=white" alt="Python ≥ 3.11"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-16a34a" alt="MIT"></a>
  <a href="#sprachen"><img src="https://img.shields.io/badge/Sprachen-DE%20%C2%B7%20EN%20%C2%B7%20ES-0d9488" alt="Sprachen: DE, EN, ES"></a>
  <img src="https://img.shields.io/badge/crypto-GnuPG-0b1f3a" alt="GnuPG">
</p>

<p align="center"><a href="README.en.md">English</a> · <a href="README.es.md">Español</a></p>

Wiederbelebung einer Bachelor-Thesis von 2019: Dateien werden mit GnuPG verschlüsselt und signiert, als Video
aus QR-Codes kodiert, über YouTube oder einen gemeinsamen Ordner übertragen und beim Empfänger wieder
zurückgewonnen. 2026 von Grund auf modernisiert: schneller, verkraftet ganze verlorene Bilder, mit
Bedienoberfläche und Kommandozeile in drei Sprachen.

**Erste Schritte:** Installation und Bedienung Schritt für Schritt, mit Bildern, in der
[Bedienungsanleitung](docs/BEDIENUNGSANLEITUNG.md).

## Auf einen Blick

<p align="center"><img src="docs/images/de/stats.svg" alt="Kennzahlen"></p>

<p align="center"><img src="docs/images/de/pipeline.svg" alt="Ablauf: Datei → GnuPG → QR-Video → Kanal → Datei"></p>

<p align="center"><img src="docs/images/de/speed.svg" alt="Zeit pro QR-Code: Original, Thesis 2019, 2026"></p>

## Architektur

<p align="center"><img src="docs/images/de/architecture.svg" alt="Architektur: qrvideo-gui und qrvideo CLI → Kern qrvideo → qrcodegenmod; extern GnuPG, ffmpeg, yt-dlp, YouTube Data API, gemeinsamer Ordner"></p>

| Teil | Ort |
|---|---|
| Moderne Bibliothek `qrcodegenmod` (Python ≥ 3.11) | `src/qrcodegenmod/` |
| Übertragung `qrvideo` (Befehl `qrvideo`) | `src/qrvideo/` |
| Bedienoberfläche (Befehl `qrvideo-gui`) | `src/qrvideo_gui/` |
| Thesis-Stand 2019 (unverändert) | `legacy/` |
| Bedienungsanleitung | [`docs/BEDIENUNGSANLEITUNG.md`](docs/BEDIENUNGSANLEITUNG.md) (English: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md), español: [`docs/GUIA_DE_USUARIO.md`](docs/GUIA_DE_USUARIO.md)) |
| Architektur, Entscheidungen (ADR), Bedrohungsmodell | [`docs/architecture/`](docs/architecture/), [`docs/security/`](docs/security/THREAT_MODEL.md) |

## Schnellstart

Voraussetzungen: [uv](https://docs.astral.sh/uv/) (holt bei Bedarf Python ≥ 3.11) und für Senden und
Empfangen GnuPG ≥ 2.4.9 (unter Windows Gpg4win). ffmpeg kommt über `imageio-ffmpeg` mit.

```powershell
git clone https://github.com/gitnol/qrvideo.git
cd qrvideo
uv sync --all-extras
uv run qrvideo-gui                     # Fenster öffnen
uv run pytest                          # Tests
uv run python bench/bench_qrcode.py    # Tempo messen
```

Wird der Ordner synchronisiert (z. B. per Cloud), gehört die virtuelle Umgebung per
`UV_PROJECT_ENVIRONMENT` an einen Ort außerhalb.

Als Bibliothek:

```python
import qrcodegenmod as q

qr = q.QrCode.encode_text("Hallo Thesis", q.Ecc.LOW)
img = qr.to_image(scale=2, border=2)  # uint8, dunkel = 0, hell = 255
```

## Bedienoberfläche (`qrvideo-gui`)

Für alle, die keine Kommandozeile nutzen möchten: Fenster mit den Reitern Senden, Empfangen, Handshake und
Schlüssel, auf Deutsch, Englisch oder Spanisch (Menü „Sprache“, `--lang`). Schritt für Schritt, auch für die
Einrichtung von GnuPG:
[Bedienungsanleitung](docs/BEDIENUNGSANLEITUNG.md) (technische Beschreibung: [`docs/features/GUI.md`](docs/features/GUI.md)).

```powershell
uv run qrvideo-gui
```

## Dateien übertragen (`qrvideo`)

Voraussetzungen: GnuPG ≥ 2.4.9 (unter Windows Gpg4win), vertraute Schlüssel für Absender und Empfänger.
Die Passphrase fragt gpg-agent ab; `QRVIDEO_PASSPHRASE` nur für unbeaufsichtigte Läufe. Sprache der Ausgaben:
`--lang de|en|es` oder `QRVIDEO_LANG`, sonst die des Systems.

```powershell
uv run qrvideo keys                                              # vertraute Schlüssel
uv run qrvideo send bericht.xlsx -r <KeyID> --sign <KeyID> -o bericht.mp4   # Format v3: ECC L, 10 % Parität
uv run qrvideo send bericht.xlsx -r <KeyID> --sign <KeyID> -o bericht.mp4 --parity 0 --ecc M  # Format v2
uv run qrvideo upload bericht.mp4 --client-secrets client_secret.json   # nicht gelistet
uv run qrvideo download https://youtu.be/<ID> -d eingang
uv run qrvideo download https://youtu.be/<ID> -d eingang --cookies-from-browser firefox   # privates Video
uv run qrvideo upload bericht.mp4 --channel folder --folder \\server\austausch   # statt YouTube: gemeinsamer Ordner
uv run qrvideo download qrvideo-<8 Hex>.mp4 --channel folder --folder \\server\austausch -d eingang
uv run qrvideo receive eingang/<ID>.mp4 -o eingang   # Datei heißt wieder wie beim Absender (Name reist verschlüsselt)
uv run qrvideo decode thesis_video_2019.mp4 -o alt.pgp --legacy  # Videos im Thesis-Format
uv run qrvideo challenge angebot/ -r <KeyID> --sign <KeyID> -o challenge.asc --png challenge.png
uv run qrvideo respond challenge.png --select 0 --sign <KeyID> -o response.asc
```

| Kennzahl (gemessen 2026-10-26) | Thesis 2019 | 2026 |
|---|---|---|
| QR-Code erzeugen (V40, 2100 Zeichen) | 3,32 ms | 0,25 ms |
| Nutzbytes je QR-Code (ECC M) | 1575 (Base64) | 2331 (binär) |
| Fehlertoleranz über Frames | keine | Standard (ECC L, 10 % Parität): 1 verlorener Frame je 10 Frames, dabei 8,9 % kürzeres Video als v2 mit ECC M |
| Original-YouTube-Video der Thesis lesen | pyzbar + Korrektur | eigener Reader, 0 Fehlschläge, 1,4 s |

Hinweis für eigene Skripte unter Windows: Der Encoder nutzt einen Prozess-Pool, das aufrufende Skript braucht
`if __name__ == "__main__":`.

## Sprachen

Bedienoberfläche und Kommandozeile sprechen Deutsch, Englisch und Spanisch. Die Quelltexte im Code sind englisch;
jede Sprache ist ein `gettext`-Katalog unter `src/qrvideo/locale/<sprache>/LC_MESSAGES/qrvideo.po` (ADR-006). Ein
Test prüft, dass jeder Text in jeder Sprache übersetzt ist, die Platzhalter `{name}` übereinstimmen und die
`.mo`-Dateien aktuell sind.

Neue Sprache ergänzen (z. B. Französisch, `fr`):

1. `"fr"` in `SUPPORTED` (`src/qrvideo/i18n.py`) und `LANGUAGES` (`tools/i18n_catalog.py`) eintragen, den Namen in
   `LANGUAGE_NAMES` (`src/qrvideo_gui/app.py`); für Zahlen einen Eintrag in `_NUMBERS` (`i18n.py`).
2. `uv run python tools/i18n_catalog.py update` legt `fr/LC_MESSAGES/qrvideo.po` mit allen Texten leer an.
3. Die `.po` übersetzen (von Hand oder mit Poedit) und `update` erneut ausführen; das kompiliert die `.mo`.
4. `uv run pytest tests/test_i18n_catalog.py` meldet, was fehlt.
5. Screenshots: `uv run --with pillow python tools/screenshots.py --lang fr` (vorher Demo-Daten der Sprache in
   `DEMO` ergänzen).

Die spanischen Texte sind nicht von Muttersprachlern geprüft; Korrekturen an der `.po` sind willkommen.

## Dank an Project Nayuki

Herzstück dieses Projekts ist `qrcodegenmod`, ein Fork der hervorragenden Bibliothek
[**QR Code generator library**](https://github.com/nayuki/QR-Code-generator) von
[Project Nayuki](https://www.nayuki.io/page/qr-code-generator-library) (MIT-Lizenz), Basis-Commit
[`6e088f7`](https://github.com/nayuki/QR-Code-generator/commit/6e088f7) vom 2019-09-13.

Nayukis Bibliothek ist ein Vorbild dafür, wie man einen Standard umsetzt: vollständig nach ISO/IEC 18004, in
mehreren Sprachen mit identischem Verhalten, ohne Abhängigkeiten und so klar geschrieben, dass sich jeder Schritt
(Segmente, Reed-Solomon, Masken, Strafpunkte) direkt nachvollziehen lässt. Genau diese Lesbarkeit hat die Thesis
2019 erst möglich gemacht – auf ihrem sauberen Fundament ließen sich die Optimierungen gezielt einbauen. Auch die
Modernisierung 2026 stützt sich auf sie: Die offizielle Version `qrcodegen` 1.8.0 dient in den Tests als Orakel,
`qrcodegenmod` erzeugt für jede Version, ECC-Stufe und Maske Bit für Bit dieselben QR-Codes.

Vielen Dank an Nayuki für diese großartige Arbeit und dafür, sie frei zur Verfügung zu stellen.
