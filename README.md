# Thesis Revival 2026

Wiederbelebung einer Bachelor-Thesis von 2019 zum Datenaustausch über Videos aus QR-Codes:
Dateien mit GnuPG verschlüsseln, als Video aus QR-Codes kodieren, über YouTube übertragen und zurückgewinnen.

| Teil | Ort |
|---|---|
| Moderne Bibliothek `qrcodegenmod` (Python ≥ 3.11) | `src/qrcodegenmod/` |
| Übertragung `qrvideo` (Befehl `qrvideo`) | `src/qrvideo/` |
| Bedienoberfläche (Befehl `qrvideo-gui`) | `src/qrvideo_gui/` |
| Thesis-Stand 2019 (unverändert) | `legacy/` |
| Bedienungsanleitung | `docs/BEDIENUNGSANLEITUNG.md` |
| Architektur, Entscheidungen (ADR), Bedrohungsmodell | `docs/architecture/`, `docs/security/` |

`qrcodegenmod` ist ein Fork von [nayuki/QR-Code-generator](https://github.com/nayuki/QR-Code-generator) (MIT),
Basis-Commit `6e088f7` vom 2019-09-13.

Die Entwicklung lief nach einem internen Doku-Prozess (Arbeitsstand, Reflexionen, Changelog). Diese
Projektprotokolle sind nicht Teil des Repos; Verweise in `docs/` auf solche Dateien beziehen sich darauf.

## Schnellstart

Die virtuelle Umgebung liegt wegen der NextCloud-Synchronisation außerhalb des Repos:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\venvs\revival_2026"
uv sync --all-extras
uv run pytest
uv run python bench/bench_qrcode.py
```

```python
import qrcodegenmod as q

qr = q.QrCode.encode_text("Hallo Thesis", q.Ecc.LOW)
img = qr.to_image(scale=2, border=2)  # uint8, dunkel = 0, hell = 255
```

## Bedienoberfläche (`qrvideo-gui`)

Für alle, die keine Kommandozeile nutzen möchten: Fenster mit den Reitern Senden, Empfangen, Handshake und
Schlüssel. Schritt für Schritt, auch für die Einrichtung von GnuPG: `docs/BEDIENUNGSANLEITUNG.md`
(technische Beschreibung: `docs/features/GUI.md`).

```powershell
uv run qrvideo-gui
```

## Dateien übertragen (`qrvideo`)

Voraussetzungen: GnuPG ≥ 2.4.9 (unter Windows Gpg4win), vertraute Schlüssel für Absender und Empfänger.
Die Passphrase fragt gpg-agent ab; `QRVIDEO_PASSPHRASE` nur für unbeaufsichtigte Läufe.

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
