# Konfiguration – Revival_2026 (QR-Code-Videokanal)

Wo Werte herkommen, in welcher Reihenfolge sie überschreiben, und wie sie
validiert werden. Verbindet sich mit den Prinzipien [[EXPLICIT_OVER_IMPLICIT]]
und [[FAIL_FAST]].

---

## Quellen-Hierarchie (Präzedenz, höchste zuerst)

1. **CLI-Argumente** (`--option value`, `qrvideo` seit I7)
2. **Umgebungsvariablen** (`QRVIDEO_GPG`, `QRVIDEO_PASSPHRASE`, `QRVIDEO_LANG`, `IMAGEIO_FFMPEG_EXE`, `QRCODEGENMOD_DISABLE_JIT`,
   `UV_PROJECT_ENVIRONMENT`; Tabelle unten)
3. **Code-Defaults** (Konstanten, Default-Argumente)

Eine Konfigurationsdatei gibt es nur für die GUI: `settings.json` im Benutzerprofil (seit I33i,
`qrvideo_gui.settings`) mit der im Menü „Sprache“ gewählten Sprache; Rang zwischen Umgebungsvariable und System,
fehlend oder kaputt = ignoriert. Sonst liest das Programm nur das
OAuth-Token unter `%APPDATA%\qrvideo\` bzw. die per `--client-secrets` übergebene Datei. CLI-Argumente und
Umgebungsvariablen überschneiden sich derzeit nicht (kein Schlüssel ist aus beiden Quellen setzbar).

---

## Validierung beim Laden

- Werte werden **einmal beim Programmstart** geladen und in einem
  **unveränderlichen** Konfigurationsobjekt abgelegt:
  - Python: `frozen=True` Dataclass oder `pydantic.BaseSettings`
  - C#: `record` mit `init`-only Properties, via `IOptions<T>`
  - PowerShell: `Set-Variable -Option ReadOnly` schützt nur die Variable — Inhalte zusätzlich
    unveränderlich halten (z. B. `[System.Collections.ObjectModel.ReadOnlyDictionary]`)
- **Nach dem Laden darf kein ungültiger Zustand mehr möglich sein** (Fail Fast).
- Typkonvertierung (str → int/bool/Path/Uri) findet **beim Laden** statt,
  nicht bei jedem Lesezugriff.
- Bereichsvalidierungen (`MIN ≤ x ≤ MAX`), Existenzprüfungen (Pfade, URLs),
  Format-Checks (Regex, ISO-Datum) gehören in den Lade-Pfad.

---

## Secrets gehören NICHT in normale Konfigurationsdateien

- Secrets immer über eine sichere Quelle: Env-Variablen, Secrets-Manager,
  Credential Store, DPAPI, KeyVault.
- Details: `docs/operations/SECRETS_MANAGEMENT.md`.
- Versionierte Konfigurationsdateien enthalten **nie** Secrets. Einzige Datei-Quelle für Secrets ist die lokale,
  ignorierte `.env` für dev/test (`docs/operations/SECRETS_MANAGEMENT.md`, Präzedenz Punkt 4); sie steht in
  `.gitignore` (siehe `docs/BOOTSTRAP.md`).

---

## Konfigurationsobjekt — Verwendung

- Funktionen erhalten Konfigwerte als **Parameter** (Default-Argument),
  nicht über globalen Zugriff. Siehe [[EXPLICIT_OVER_IMPLICIT]].
- Das vollständige Konfigurationsobjekt wird **einmal** im Einstiegspunkt
  gebaut (`build_config()` / `IConfiguration` / `Read-Config`) und an die
  Anwendungsschicht weitergereicht.
- Module der Domänenschicht **kennen das Konfigurationsobjekt nicht** —
  sie bekommen die für sie relevanten Werte als Parameter.

---

## Konfigurations-Tabelle (Pflicht ausfüllen)

| Schlüssel | Typ | Default | Quelle(n) | Beschreibung |
|---|---|---|---|---|
| `UV_PROJECT_ENVIRONMENT` | Pfad | kein (Pflicht für Entwickler) | ENV | Ort der venv **außerhalb** des NextCloud-Ordners, empfohlen `%LOCALAPPDATA%\venvs\revival_2026` |
| QR-Parameter (Version, Maske) | `int` | V40 / Maske 1 | Code-Konstante (`qrvideo.encoder`) | Feste Geometrie ist Voraussetzung für den Reader (ADR-001) |
| ECC-Stufe der Daten-QR | Enum | L (2953 Bytes je QR, in v3 abzüglich 8 Bytes Präfix) seit I18, vorher M | CLI `--ecc L/M/Q/H`, GUI fest | steht im Kopf-QR, der Decoder liest sie mit |
| Parität über Frames | `int` (Prozent) | 10 (m = 14 je 10 Frames, Format v3) seit I18 | CLI `--parity 0..50`, GUI fest | 0 = Format v2; `qrvideo.encoder.DEFAULT_PARITY_PERCENT`, ADR-003 |
| Frame-Layout | `FrameLayout` | 3 × 5, Skalierung 2, Rand 2, 1920×1080 | Code-Konstante (`qrvideo.layout`) | identisch zur Thesis |
| Video-Qualität | `int` / `str` | crf 12, preset medium, 30 fps | CLI `--crf`, `--preset` | crf 0 = verlustfrei (Profil high444) |
| Worker-Anzahl | `int` | alle Kerne | CLI `--workers` | Prozess-Pool beim Rendern |
| `QRVIDEO_GPG` | Pfad | GnuPG-Installation, sonst `gpg` im PATH ohne die gpg aus Git | ENV | `qrvideo.crypto.find_gpg_binary` |
| `--gnupghome` | Pfad | Schlüsselbund des Nutzers | CLI | eigener Schlüsselbund, z. B. für Tests |
| `--lang` / `QRVIDEO_LANG` (/ GUI-`settings.json`) | `de`, `en`, `es` | Sprache des Systems (Windows: Sprache der Oberfläche), sonst `en` | CLI / ENV / Datei (nur GUI) | Sprache der Nutzertexte (ADR-006, seit I33d); nicht unterstützte Werte fallen auf die nächste Quelle zurück |
| `QRVIDEO_PASSPHRASE` | Secret | nicht gesetzt → gpg-agent/pinentry | ENV | nur für unbeaufsichtigte Läufe (`operations/SECRETS_MANAGEMENT.md`) |
| `IMAGEIO_FFMPEG_EXE` | Pfad | gebündeltes FFmpeg aus `imageio-ffmpeg` | ENV | aktuelles System-FFmpeg erzwingen (gebündelt: 7.1, siehe `security/DEPENDENCY_AUDIT.md`) |
| `QRCODEGENMOD_DISABLE_JIT` | `0/1` | `0` | ENV | Numba abschalten, NumPy-Fallback |
| Transportkanal | `youtube`/`folder` | `youtube` | CLI `--channel` (download, upload); GUI fest YouTube | ADR-005, `qrvideo.channel.make_channel` |
| Browser-Cookies für den Download | `BROWSER[:PROFIL]` | aus | CLI `download --cookies-from-browser` | seit I30a, nur YouTube; yt-dlp liest die Anmeldung des Browsers lokal, z. B. für private Videos |
| Kanal-Ordner | Pfad | — | CLI `--folder` | nur für `--channel folder`; z. B. Sync- oder Netzwerkordner, den Sender und Empfänger teilen |
| OAuth-Client | Datei | — | CLI `--client-secrets` | nur YouTube-Upload; aus der Google Cloud Console, nie im Repo |
| OAuth-Token | Datei | `%APPDATA%\qrvideo\youtube-token.json` | FILE | außerhalb des Programmordners (`qrvideo.youtube.default_token_path`) |

Ist-Stand: Es gibt kein zentrales Konfigurationsobjekt und kein `build_config()`. Die CLI reicht Werte als
Parameter weiter (Video-Werte als `VideoSettings`, frozen Dataclass in `qrvideo.videoio`); Umgebungsvariablen werden
an der Stelle des Bedarfs gelesen (`qrvideo.cli._passphrase`, `qrvideo.crypto.find_gpg_binary`,
`qrcodegenmod._jit`, `qrvideo.youtube.default_token_path` liest `APPDATA`). Das weicht von den Abschnitten oben ab —
offene Entscheidung, siehe `BACKLOG.md` bzw. Reflexion.

---

## Anti-Pattern

- **Werte direkt aus `os.environ` / `Environment.GetEnvironmentVariable` /
  `$env:VAR` mitten in der Geschäftslogik lesen.** Versteckte Abhängigkeit.
- **Konfiguration zur Laufzeit mutieren** (z.B. `config.timeout = 30` in
  einem Service). Immutabilität bricht. Test-Setup ist die Ausnahme — dort
  über DI/Override-Mechanismus, nicht durch Mutation.
- **Magic Defaults im Code** (`timeout=30` in jeder Funktion neu) statt
  zentralem Wert im Konfigurationsobjekt.

---

## Pflege

Trigger (siehe `KICKOFF.md` Phase 3a): neue Konfig-Quelle / neuer Schlüssel /
geänderte Präzedenz → diese Datei eintragen, Validierung implementieren,
Tabelle aktualisieren.
