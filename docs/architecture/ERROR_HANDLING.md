# Fehlerbehandlung – Revival_2026 (QR-Code-Videokanal)

Wo und wie Fehler erkannt, propagiert, behandelt und gemeldet werden.
Konsolidiert Regeln, die sonst in `CONVENTIONS.md`, `principles/FAIL_FAST.md`,
`principles/CONTRACTS.md` und `principles/LOGGING.md` verstreut sind.

---

## Exception-/Fehler-Hierarchie

- **Eine projektspezifische Basis-Exception** als Wurzel:
  - Python: `class [Project]Error(Exception)`
  - C#: `public class [Project]Exception : Exception`
  - PowerShell: terminating errors via `throw` mit klarer `Message` und ggf. `ErrorRecord`-Kategorie

- **Spezifische Unterklassen** je Fehlerursache, z.B.:
  `ValidationError`, `AuthenticationError`, `AuthorizationError`,
  `ResourceNotFound`, `ExternalServiceError`, `ConfigurationError`.

- **Niemals nackte `Exception` / `Error` werfen.** Nackte Exceptions verhindern
  gezielte Behandlung an der Boundary.

---

## Boundary vs. interne Fehler

| Ebene | Verhalten |
|---|---|
| **Boundary** (CLI, HTTP, externer Aufruf) | Fehler in Nutzer-/Caller-freundliches Format konvertieren (Exit-Code, HTTP-Status, JSON-Antwort). Niemals interne Tracebacks zurückgeben. |
| **Anwendung / Domäne** | Spezifische Exceptions **werfen**, nicht abfangen. Verantwortung an Boundary delegieren. |
| **Infrastruktur** (Repositories, Adapter) | Stack-/Bibliotheks-spezifische Fehler in projektspezifische konvertieren (z.B. `IntegrityError` → `EntityAlreadyExists`). Damit „leakt" kein ORM- oder HTTP-Spezifikum nach oben. |

---

## Was geloggt und was gerethrowt wird

- **Boundary** fängt → loggt → konvertiert in Antwortformat. Das Level richtet sich nach der Art des Fehlers
  (Level-Semantik: `docs/principles/LOGGING.md`):
  - **unerwartet** (Programmierfehler, Sicherheitsnetz, Infrastruktur ausgefallen) → `ERROR` mit vollem Stacktrace
    (`exc_info=True` / `_logger.LogError(ex, …)`);
  - **erwartet, fachlich** (ungültige Eingabe, Ressource nicht gefunden, Rechte fehlen) → `WARNING` ohne
    Stacktrace — sonst erzeugt jeder Robustheitstest ein `ERROR`.
- **Mittelschichten** lassen Fehler durch — **kein doppeltes Logging** desselben Fehlers.
- **Niemals `except: pass` / leeres `catch {}` ohne Logging.** Wird ein Fehler bewusst
  ignoriert, wird er auf `DEBUG` (reine Information) bzw. `WARNING` (Zustand ist auffällig) geloggt und der
  Grund kommentiert (`LOGGING.md`).

---

## Retry-Strategien

- Nur retryen, wenn die Operation **idempotent** ist (oder das System sie idempotent macht).
- Klare Obergrenze: `MAX_RETRIES = N`, exponentielles Backoff mit Jitter.
- **Keine geschachtelten Retry-Schleifen** auf derselben Operation (z. B. Token-Abruf mit eigenem
  Retry innerhalb eines Request-Retrys: der Token-Fehler darf nicht vom äußeren Retry aufgefangen werden).
- Authentifizierungsfehler **niemals retryen** ohne Token-Invalidierung dazwischen.
- Tritt ein nicht-retryable Fehler auf (z.B. HTTP 400, `ValidationError`) → sofort propagieren.

---

## Feindliche Eingaben — kein Absturz an Systemgrenzen

Alles, was von außen kommt, ist feindlich: Dateien und Fremdformate, CLI-Parameter,
Konfiguration, API- und DB-Antworten, Aufrufe durch Agenten/Tools. Ergebnis ist **immer
ein behandelbarer Fehler** (projektspezifische Exception → Boundary-Konvertierung), nie
ein Prozessabsturz, ein hängender Prozess oder verlorene Nutzerdaten.

> Abgrenzung zu [[FAIL_FAST]]: Fail Fast bricht die **Operation** früh und laut ab.
> Diese Regel sorgt dafür, dass dabei nicht der **Prozess** oder die Arbeit des Nutzers
> mitgerissen wird. Abgrenzung zu [[UNTRUSTED_DOCUMENT_CONTENT]]: dort geht es um fremden
> Inhalt im LLM-Prompt (Injection/Fälschung), hier um die Robustheit des Prozesses.

- **Eingabe-abgeleitete Zahlen prüfen:** Indizes und Längen vor dem Zugriff, Größen vor
  der Allokation begrenzen, Division durch null und NaN/Unendlich abfangen, Überläufe
  vermeiden.
- **Rekursion und Schleifen begrenzen** (Tiefenlimit oder Besucht-Menge) — Eingaben
  können tief verschachtelt oder zyklisch sein.
- **Schreiben atomar:** in eine Temp-Datei **im selben Verzeichnis** schreiben, dann
  umbenennen (`os.replace` / `File.Replace` / `Move-Item -Force`). Scheitert der
  Schreibvorgang, bleibt die Originaldatei unverändert.
- **Letztes Sicherheitsnetz** an der äußersten Boundary (Befehls-Dispatch, Import/Export):
  fängt einen entkommenen Fehler, loggt ihn mit Stacktrace, meldet ihn verständlich und
  erhält den Arbeitsstand. Ein Netz, kein Freibrief für unbehandelte Fehlerpfade.
- **Jeder Crash-Fix bringt einen kleinen synthetischen Regressionstest mit**, der vor dem
  Fix nachweislich abgestürzt ist (behaviorales Rot, `KICKOFF.md` Phase 2).
- **Robustheitstest über alle Einstiegspunkte**, sobald es eine zentrale Eingangsschicht
  gibt (CLI-Befehle, Endpunkte, exportierte Cmdlets): jeden Einstiegspunkt mit feindlichen
  Parametern aufrufen (leer, falscher Typ, außerhalb des Bereichs, riesig) und nur einen
  Fehler — keinen Absturz, keinen Hänger (Timeout) — akzeptieren. Die Liste der
  Einstiegspunkte wird **automatisch ermittelt** (Registry, Reflection, Modul-Export),
  damit neue Einstiegspunkte ohne Zutun mitgeprüft werden.

---

## Konvertierungstabelle (Pflicht ausfüllen)

Ist-Stand seit I7. Nur die CLI `qrvideo` ist eine Boundary; HTTP gibt es nicht. Der Code nutzt kein `logging`:
die CLI schreibt `Fehler: <Meldung>` auf stderr, ohne Traceback (`principles/LOGGING.md`).

| Interne Exception | CLI Exit-Code | HTTP-Status | Log-Level | Bemerkung |
|---|---|---|---|---|
| `qrvideo.errors.ContainerError(ValueError)` (auch als `qrvideo.container.ContainerError`) | `1` | — | stderr | kein lesbarer v2-/v3-Kopf, Frame-Index außerhalb, Gruppe ungültig, Chunks fehlen, „Gruppe g: … Datensymbole fehlen, nur … Paritätssymbole“ (v3), Länge oder SHA-256 falsch; CRC-Fehler eines v3-Daten-QR zählt nur als Ausfall im `DecodeReport` |
| `qrvideo.crypto.GpgError(RuntimeError)` | `1` | — | stderr | gpg nicht gefunden, Empfänger fehlt/nicht vertraut, Ver-/Entschlüsseln fehlgeschlagen |
| Meldungstexte (seit I33e, ADR-006) | — | — | — | Nutzer-sichtbare Texte über `qrvideo.i18n._` in der Sprache zum Zeitpunkt des Auslösens; `ValueError` für Programmierfehler (Geometrie in `layout`, Gruppenparameter in `erasure`, `parity_symbols`) englisch und unübersetzt |
| `qrvideo.crypto.GpgNotFoundError(GpgError)` | `1` | — | stderr | kein gpg gefunden (GUI: Hinweis auf Gpg4win); seit I33b |
| `qrvideo.crypto.RecipientsError(GpgError)` | `1` | — | stderr | Empfänger fehlen oder nicht voll vertraut; seit I33b |
| `qrvideo.crypto.EncryptError(GpgError)` / `DecryptError(GpgError)` | `1` | — | stderr | gpg konnte nicht ver- bzw. entschlüsseln; seit I33b |
| `qrvideo.crypto.UntrustedSignatureError(GpgError)` | `1` | — | stderr | keine gültige oder nicht voll vertraute Signatur; Klartext wird nicht geschrieben |
| `qrcodegenmod.DataTooLongError(ValueError)` | `1` | — | stderr | Daten passen nicht in den QR-Code |
| `ValueError` (u. a. `qrvideo.layout`, `qrvideo.videoio`, `qrvideo.youtube.parse_video_id`, `qrvideo.channel`) | `1` | — | stderr | ungültige Geometrie, keine Frames, keine Video-ID; seit I29/I30: Verweis kein Dateiname im Kanal-Ordner, `upload` ohne `--client-secrets` bzw. `--folder`, `--cookies-from-browser` beim Ordner-Kanal |
| `qrvideo.handshake.HandshakeError(ValueError)` | `1` | — | stderr | Handshake-Nachricht kein JSON, unbekannte Formatversion (lesbar: 1, 2) oder Nachrichtenart, falsche Feldtypen, ungültiges Video bzw. Auswahl (Format v2, seit I29c1) |
| `OSError` (u. a. `FileNotFoundError`, `FileExistsError` bei `receive` ohne `--force`) | `1` | — | stderr | Dateisystem, fehlende Videodatei |
| `qrcodegenmod.reader.QrDecodeError(ValueError)` | indirekt `1` | — | Zähler im `DecodeReport` | im Decoder je Slot abgefangen und als „unlesbar" gezählt; fehlen dadurch Chunks (v2), mehr als m Symbole einer Gruppe (v3) bzw. gibt es überhaupt unlesbare QR (`--legacy`), folgt `ContainerError` |
| `qrcodegenmod._rs_decode.ReedSolomonError(ValueError)` | — | — | — | im Reader in `QrDecodeError` umgewandelt |
| ungültige Argumente (`argparse`) | `2` | — | stderr (Usage) | `SystemExit` aus `argparse`; auch unbekannter Browser bei `--cookies-from-browser` (seit I30a) |
| `KeyboardInterrupt` (Ctrl+C) | `130` | — | stderr „Abgebrochen" | seit Fix nach I5 (`tests/test_qrvideo_cli.py::test_ctrl_c_exits_130`) |
| andere Exceptions (z. B. `TypeError`) | Python-Default | — | Traceback | Programmierfehler, bewusst nicht abgefangen |
| GUI (`qrvideo_gui.jobs.Job`, seit I20a): jede `Exception` im Hintergrund-Thread | — (Meldung im Fenster) | — | `ERROR` mit Traceback ins Log (Konsole) | Boundary der GUI: `qrvideo_gui.errors.friendly_message` macht daraus einen Satz in der gewählten Sprache (ADR-006), zugeordnet nur per Ausnahme-Klasse; unbekannte Ausnahmen zeigen nur „Unerwarteter Fehler“ |
| `qrvideo_gui.jobs.Cancelled(Exception)` | — | — | kein Log | Abbrechen-Knopf; wird beim nächsten Fortschrittsschritt geworfen, `write_video` entfernt dann die halbe Datei |

---

## Projektspezifische Festlegungen

- `qrcodegenmod` behält die Upstream-API: `DataTooLongError(ValueError)` bei zu langen Daten, `ValueError` bei
  ungültigen Argumenten — kompatibel zu nayuki/`qrcodegen`, damit Aufrufer beide austauschen können. Der Reader wirft
  `QrDecodeError(ValueError)`, intern `ReedSolomonError(ValueError)`.
- `qrvideo` (seit I4/I7): keine gemeinsame Basis-Exception. Eigene Klassen sind `ContainerError(ValueError)`,
  `GpgError(RuntimeError)` mit den Unterklassen aus der Tabelle (die GUI ordnet nur per Klasse zu, nie per Text, ADR-006); sonst Standard-Exceptions. Die CLI fängt
  `ContainerError, ValueError, OSError, RuntimeError` und gibt Exit `1`. Das weicht von der Regel „eine
  projektspezifische Basis-Exception" oben ab. **Entscheidung (Reflexion 2026-10-26):** bewusst so belassen — ein
  kleines CLI-Werkzeug mit einer Boundary; die Standard-Basisklassen genügen, eine eigene Hierarchie wäre ohne
  Konsumenten (`principles/YAGNI.md`).
- Der Legacy-PoC nutzt `assert` als Fehlerbehandlung und bare `except` — mit `python -O` entfallen alle Prüfungen,
  darunter die Signatur-/Trust-Prüfung. In `qrvideo` abgelöst (seit I4/I7, Prüfungen per `raise`); `legacy/` bleibt
  unverändert (`KNOWN_ISSUES.md`).

---

## Anti-Pattern

- **`raise Exception("...")`** statt einer spezifischen Klasse.
- **Catch-and-rethrow ohne Mehrwert** (`except Foo: raise Foo`) — entfernen.
- **Boundary, die Stacktraces an den Aufrufer zurückgibt** (`HTTP 500` mit
  Python-Traceback im Body). Sicherheitsrisiko + UX-Risiko.
- **Stilles Wegfangen** in der Mitte des Aufruf-Stacks (`except: pass`) —
  Fail-Fast wird ausgehebelt.

---

## Pflege

Trigger (siehe `KICKOFF.md` Phase 3a): neue Exception-Klasse / neue Boundary
/ neue Retry-Stelle → diese Datei + Konvertierungstabelle aktualisieren.
