# CLI-Schnittstelle – Revival_2026 (QR-Code-Videokanal)

Seit I7 gibt es den Befehl `qrvideo` (`src/qrvideo/cli.py`, `argparse`, Einstiegspunkt in `pyproject.toml`) mit
den Unterbefehlen `encode`, `decode`, `send`, `receive`, `keys`, `download`, `upload`; er ersetzt das interaktive
Konsolenmenü des Thesis-PoC (`legacy/poc/POC.py`, bleibt unverändert). `src/qrcodegenmod/` ist eine Bibliothek ohne
eigene CLI; `bench/bench_qrcode.py` ist ein Entwicklerwerkzeug.

---

## Aufruf

```bash
# modernisierte Pipeline (seit I7; Extras video/crypto/youtube bzw. all)
uv run qrvideo [--gnupghome PFAD] <unterbefehl> ...

# Desktop-GUI (seit I20b, docs/features/GUI.md); --gnupghome wie bei qrvideo
uv run qrvideo-gui [--gnupghome PFAD]

# Benchmark (seit I2)
uv run python bench/bench_qrcode.py --n 300

# Legacy-PoC (Windows, Thesis-Stand; läuft ohne Modernisierung nicht mehr vollständig, siehe KNOWN_ISSUES.md)
python legacy/poc/POC.py
```

---

## Argument-Tabelle

`qrvideo` (Quelle: `build_parser()` in `src/qrvideo/cli.py`, Handshake-Befehle seit I26 in
`src/qrvideo/cli_handshake.py`). Die Validierung übernimmt `argparse` (Typ, `choices`,
Pflicht); weitere Prüfungen finden erst in den Unterbefehlen statt (z. B. Zieldatei existiert, gpg vorhanden).

| Argument | Typ | Pflicht | Default | Validierung | Beschreibung |
|----------|-----|---------|---------|-------------|-------------|
| `--gnupghome` (global) | Pfad | nein | Schlüsselbund des Nutzers | — | eigener GnuPG-Schlüsselbund |
| `encode INPUT -o OUTPUT` | Pfad | ja | — | — | Datei (z. B. `.gpg`) als Video kodieren |
| `decode INPUT -o OUTPUT [--legacy]` | Pfad | ja | — | — | Video zurück zur Datei; `--legacy` = Thesis-Format 2019 |
| `send INPUT -r KEY [-r KEY …] --sign KEY -o OUTPUT` | Pfad / str | ja | — | — | verschlüsseln, signieren, als Video kodieren (ohne Zwischendatei seit I13) |
| `receive INPUT [-o ZIEL] [--force]` | Pfad | INPUT ja | `-o .` | Zieldatei wird ohne `--force` nicht überschrieben; ist ZIEL ein Ordner, heißt die Datei nach dem verschlüsselt eingebetteten Namen (seit I27a, `safe_filename`), sonst nach dem Video | dekodieren, entschlüsseln, Signatur prüfen |
| `keys` | — | — | — | — | vertraute Schlüssel anzeigen |
| `challenge ORDNER -r KEY --sign KEY -o DATEI [--video VERWEIS …]` | Pfad / str | ja | — | `<kanal>:<verweis>` oder YouTube-Link/-ID über `channel_ref` (seit I29c1), geschrieben als Format v2 | Server Challenge: Dateien des Ordners anbieten (ASCII-Armor); `--png BILD` zusätzlich als QR-Code |
| `respond CHALLENGE --select N --sign KEY -o DATEI [-r KEY]` | Pfad / int | ja | `-r` = Absender der Challenge | Auswahl im Bereich, nur Challenge | Client Response mit der gewählten Datei bzw. dem Video; CHALLENGE darf `.asc` oder QR-PNG sein, `--png BILD` |
| `inspect DATEI` | Pfad | ja | — | Signatur voll vertraut | Challenge oder Response (`.asc` oder QR-PNG) entschlüsseln und anzeigen |
| `download VIDEO [-d ORDNER] [--channel youtube\|folder] [--folder ORDNER] [--cookies-from-browser BROWSER[:PROFIL]]` | str / Pfad | VIDEO ja; `--folder` bei `folder` | `-d .`, Kanal `youtube`, ohne Cookies | Verweis über den Kanal (`qrvideo.channel`, ADR-005): YouTube-URL/ID bzw. reiner Dateiname im Kanal-Ordner, nie ein Pfad; Browser wie yt-dlp (`youtube.BROWSERS`), sonst Exit 2; Cookies beim Ordner-Kanal → Exit 1 (seit I30a) | Video aus dem Kanal holen (YouTube per yt-dlp); überschreibt im Ordner-Kanal nie |
| `upload INPUT [--client-secrets DATEI] [--title TITEL] [--channel youtube\|folder] [--folder ORDNER]` | Pfad / str | INPUT ja; `--client-secrets` bei `youtube`, `--folder` bei `folder` (sonst Exit 1, seit I29b) | Kanal `youtube`; Titel = `qrvideo <8 Hex>` (seit I27a, nie der Dateiname) | Titel über `safe_filename` | YouTube: nicht gelistet hochladen, gibt `https://youtu.be/<ID>` aus — speichert YouTube das Video anders (z. B. „privat“ bei nicht verifiziertem API-Projekt), seit I30b1 ein `Hinweis:` auf stderr mit dem Weg zum Abholen; Ordner: Kopie `qrvideo-<8 Hex>.mp4`, gibt den Dateinamen aus |
| `--ecc` (encode, send) | `L/M/Q/H` | nein | `L` (seit I18) | `choices` | Fehlerkorrektur je QR-Code |
| `--parity` (encode, send) | `int` 0..50 | nein | `10` (seit I18) | `_percent` | Prozent Paritäts-QR je 10 Frames (Format v3); `0` = Format v2 |
| `--crf` (encode, send) | `int` | nein | `12` | `type=int` | x264-Qualität, 0 = verlustfrei |
| `--preset` (encode, send) | str | nein | `medium` | — | x264-Preset |
| `--workers` (encode, send) | `int` | nein | alle Kerne | `type=int` | Prozesse fürs Rendern |
| `--force` (encode, send, receive) | Schalter | nein | aus | — | vorhandene Zieldatei überschreiben |

Legacy-PoC: nimmt keine Kommandozeilenargumente entgegen (`argparse` nur intern für den YouTube-Upload).
Signer-Fingerprint und Passphrase liest `main()` seit I5 aus `QRVIDEO_SIGN_FINGERPRINT` und `QRVIDEO_PASSPHRASE`.

---

## Laufmodi

`qrvideo` hat keine Laufmodi außer den Unterbefehlen (Tabelle oben). Die folgenden Modi betreffen nur den
Legacy-PoC; der Handshake ist seit I8a als `challenge`/`respond`/`inspect` portiert.

| Modus | Aktivierung | Verhalten |
|-------|------------|-----------|
| Hauptmenü | Start von `POC.py` | Auswahl Client (1), Server (2), Beenden (99) |
| Servermodus | Menü 2 | Empfänger wählen, Dateien verschlüsseln, Video erzeugen, auf YouTube hochladen, „Server Challenge"-QR-Code schreiben, „Client Response" einlesen |
| Clientmodus | Menü 1 | „Server Challenge" einlesen (PNG oder eingefügter Text), Dateien auswählen, „Client Response" schreiben, Video per YouTube-ID laden, dekodieren, entschlüsseln |

---

## Exit-Codes

`qrvideo` (seit I7, `main()` in `src/qrvideo/cli.py`):

| Code | Bedeutung | Wann |
|------|-----------|------|
| `0` | Erfolg | Unterbefehl vollständig durchgelaufen |
| `1` | Fehler | `ContainerError`, `ValueError`, `OSError` oder `RuntimeError` (u. a. `GpgError`, `UntrustedSignatureError`, gpg/Zieldatei-Konflikt); Meldung `Fehler: …` auf stderr |
| `2` | Ungültige Argumente | von `argparse` selbst (`SystemExit(2)`, Usage auf stderr) |

Ctrl+C beendet mit Exit `130` und „Abgebrochen" auf stderr; andere unerwartete Exceptions (Programmierfehler)
fängt `main()` bewusst nicht ab. Legacy-PoC: beendet sich mit `sys.exit(0)` auch bei Fehlern
(fehlende Schlüsselparameter, falsche Passphrase).

---

## Konfigurationsaufbau (Ist-Stand seit I7)

```
CLI-Argumente (argparse.Namespace) + Umgebungsvariablen (QRVIDEO_GPG, QRVIDEO_PASSPHRASE, …)
    ↓
cmd_<unterbefehl>(args) — baut VideoSettings (frozen Dataclass) bzw. Crypto(homedir=…)
    ↓
Pipeline (verschlüsseln → chunk → QR → Frame → Video bzw. Rückweg)
```

Es gibt kein zentrales `build_config()` und kein Gesamt-Konfigurationsobjekt; die Unterbefehle reichen die Werte als
Parameter weiter. Umgebungsvariablen liest der Code an der Stelle des Bedarfs (`cli._passphrase`,
`crypto.find_gpg_binary`, `qrcodegenmod._jit`), siehe `CONFIGURATION.md`.

---

## Beispielaufrufe

```bash
# Legacy-PoC über die Batch-Datei der Abgabe (Windows)
legacy\poc\_STARTE_POC.bat

# Datei verschlüsselt und signiert als Video, Empfang mit Signaturprüfung
uv run qrvideo send bericht.xlsx -r <KeyID> --sign <KeyID> -o bericht.mp4
uv run qrvideo receive bericht.mp4 -o .

# Thesis-Video von 2019 dekodieren
uv run qrvideo decode altes_thesis_video.mp4 -o alt.pgp --legacy

# Tests (seit I2)
uv run pytest
```

---

## Bekannte Validierungsfallstricke

- **Python Chained Comparisons:** `if 0 > x > MAX:` ist immer `False` (logisch unmöglich).
  Korrekt: `if not (0 <= x <= MAX):` — diese Falle bei allen Bereichs-Validierungen prüfen.
- **Pfad-Expansion:** `Path(args.source).expanduser().resolve()` vor Validierung aufrufen.
  Sonst scheitert `source.exists()` bei `~`-Pfaden auf manchen Systemen.
- **Arbeitsordner relativ zum CWD:** Der Legacy-PoC legt `files_*`-Ordner relativ zum aktuellen Verzeichnis an und
  lädt `.npy` ebenfalls relativ zum CWD — Start aus einem anderen Ordner schlägt fehl. `qrcodegenmod` berechnet die
  Tabellen seit I2 beim Import (kein `.npy`), `qrvideo` arbeitet nur mit übergebenen Pfaden.
