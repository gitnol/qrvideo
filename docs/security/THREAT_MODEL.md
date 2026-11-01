# Threat Model & Mitigationen – Revival_2026 (QR-Code-Videokanal)

---

Leitfragen zum Finden von Bedrohungen: `security/THREAT_MODEL_GUIDE.md` (vom Template gepflegt).
Öffentliches oder potenziell öffentliches Repo: keine internen Hosts, Versionen oder Betroffenheiten konkreter Systeme —
die gehören nach `docs/local/` (`CONVENTIONS_COMMON.md` 3.1).

Stand: 2026-10-26 (Init, abgeleitet aus `legacy/`). Security-Currency-Befunde: `security/DEPENDENCY_AUDIT.md`.
Beim Lesen des Codes wurden keine an Agenten gerichteten Anweisungstexte gefunden.

## 1. Unverschlüsselte Metadaten im Transportkanal (T1)

**Gefahr:** Der Inhalt ist verschlüsselt, aber Dateiname und Empfänger-KeyIDs stehen im Klartext im Video-Dateinamen
und werden beim Upload als YouTube-Titel/-Beschreibung übernommen (`POC.py`
`menue_v2_servermodus_upload_to_youtube`: Titel/Beschreibung aus dem Dateinamen). Jeder mit Link sieht, wer
Empfänger ist und was übertragen wird (Verkehrsanalyse). Der Code-Kommentar in `QRCrypt.__init__` erwähnt zudem,
dass die Signatur Rückschlüsse auf den Absender zulässt.

**Mitigation:**
- Seit I4: Format v2 (und v3 seit I17b) überträgt keine Dateinamen im Video (binärer Kopf, ADR-001/ADR-003).
- Seit I27a: `Crypto.encrypt` setzt `--throw-keyids` — in der Nachricht stehen statt der Empfänger-KeyIDs nur
  Nullen (Orakel `gpg --list-packets`, Test `test_recipients_are_hidden`); das gilt auch für Handshake-Nachrichten.
  Sichtbar bleibt die Zahl der Empfänger. Kosten: der Empfänger probiert alle eigenen geheimen Schlüssel (bei
  mehreren passphrasegeschützten Schlüsseln mehrere Abfragen); Kleopatra hatte 2025 Berichten zufolge Probleme
  mit solchen Nachrichten (Websuche 2026-10-27)
- Seit I27a: `send` bettet den Originalnamen verschlüsselt ein (`--set-filename`, Literal-Paket); `receive` nennt
  die Datei danach (über `safe_filename`, fremde Eingabe — Test `test_receive_sanitizes_the_embedded_file_name`).
  `upload` ohne `--title` vergibt einen zufälligen Titel `qrvideo <8 Hex>` statt des Dateinamens. Der Name im
  Literal-Paket ist nicht von der Signatur gedeckt — ein Mitempfänger könnte ihn beim Weiterverschlüsseln ändern;
  er dient nur als Vorschlag für den Dateinamen
- Seit I27b1/I27b2: Die GUI schlägt einen zufälligen Videonamen `qrvideo-<8 Hex>.mp4` vor, bettet den Originalnamen
  verschlüsselt ein und nennt empfangene Dateien danach. Beim CLI-`send` wählt der Nutzer den Videonamen (`-o`)

**Restrisiko:** Hoch (Legacy) / Niedrig (`qrvideo` seit I27: Empfänger verborgen, Name verschlüsselt, neutrale
Video- und Titelvorschläge; beim CLI bleibt der Videodateiname Nutzerwahl) – Existenz, Größe und Zeitpunkt der
Übertragung bleiben sichtbar.

---

## 2. YouTube als Transportkanal (T2)

**Gefahr:** Unlisted-Videos sind für jeden mit Link abrufbar; YouTube re-encodiert (Kompressionsverluste bei ECC LOW
→ unlesbare QR-Codes), kann Videos sperren/löschen (ToS: Video ohne Bildinhalt im üblichen Sinn) und Formate ändern
(`youtube_dl` ist bereits tot). Verfügbarkeit und Integrität des Kanals liegen außerhalb unserer Kontrolle.

**Mitigation:**
- Vertraulichkeit/Integrität ausschließlich über GnuPG (verschlüsselt + signiert), nie über den Kanal
- Seit I4/I6: v2-Kopf mit Frame-Index, Frame-Anzahl, Länge und SHA-256 — fehlende Chunks oder falsche Prüfsumme →
  `ContainerError`; der Decoder mittelt 2×2 Pixel je Modul, Reed-Solomon korrigiert im eigenen Reader
- Seit I17/I18 (Standard): Format v3 — CRC32 je Daten-QR macht stille Fehlkorrekturen zu Auslöschungen, ein
  äußerer Erasure-Code ersetzt bis zu 14 fehlende Daten-QR je 10 Frames (ADR-003); live auf YouTube bytegenau
  (I17e). Kein Schutz gegen Absicht: CRC32 ist keine Signatur, Echtheit bleibt Sache von GnuPG
- Seit I4: lokale Roundtrip-Tests ohne YouTube (`tests/test_qrvideo_video.py`); seit I29 (ADR-005) ist der Kanal
  austauschbar: `--channel folder` legt das Video in einen gemeinsamen Ordner — Ausweg, wenn YouTube sperrt oder
  ausfällt (seit I29c1 nennt auch der Handshake Videos mit Kanal); Videos nach Empfang löschen

**Restrisiko:** Mittel – Verfügbarkeit von YouTube nicht garantierbar (seit I29 mit Ausweichkanal); Vertraulichkeit
hängt an GnuPG.

---

## 3. Vertrauen auf GnuPG-Ownertrust und Prüfungen per `assert` (T3)

**Gefahr:** Ob eine Nachricht akzeptiert wird, entscheidet der Trust-Level im lokalen Keyring
(`QRCrypt.decrypt_text_message`, `decrypt_file`: `trust_level >= TRUST_FULLY`). Ein falsch vertrauter Schlüssel
genügt für gefälschte Challenges/Dateien. Alle Prüfungen sind `assert`s — mit `python -O` entfallen sie komplett;
ein bare `except` beim Lesen der Signaturinfo verschluckt Fehler.

**Mitigation:**
- Seit I7 (`qrvideo.crypto`): Prüfungen per `raise` (`GpgError`, `UntrustedSignatureError`), Signatur zwingend,
  Trust ≥ FULLY, Verschlüsseln nur für vertraute Empfänger; `receive` zeigt Signaturgeber und Fingerprint an. Ein
  Abgleich gegen eine Liste erwarteter Absender ist nicht umgesetzt (offen)
- Ownertrust bewusst setzen (Fingerprint out-of-band verifizieren); GnuPG ≥ 2.4.9 (`DEPENDENCY_AUDIT.md`)

**Restrisiko:** Hoch (Legacy, `assert`) / Mittel (`qrvideo`) – Trust-Entscheidung bleibt beim Nutzer.

---

## 4. Untrusted Eingaben aus dekodierten QR-Codes, Videos und eingefügten PGP-Nachrichten (T4)

**Gefahr:** Der Empfänger verarbeitet Videos aus dem Netz (ffmpeg-Decoder mit bekannten Speicherfehler-CVEs),
QR-Inhalte beliebiger Länge und per `input()` eingefügte PGP-Blöcke (`menue_v2_*_manual_input`). Der Inhalt eines
Management-QR-Codes wird nach dem Entschlüsseln an festen Trennzeichen zerlegt (`decrypt_signed_qrcode_content`)
ohne Formatprüfung; Fehler werden per bare `except` übergangen.

**Mitigation:**
- Seit I4/I7: Format v2 mit Längen-, Index- und SHA-256-Prüfung (`qrvideo.container`); `receive` entschlüsselt
  und prüft die Signatur, bevor Klartext geschrieben wird; Frames mit falscher Auflösung → `ValueError`
  (`qrvideo.layout`); `qrvideo` hat keine Texteingabe per `input()`
- imageio-ffmpeg/FFmpeg aktuell halten (`IMAGEIO_FFMPEG_EXE`, Risiko in `STATE.md`)
- Offen: Größenlimit für die Anzahl Frames bzw. die Nutzlast

**Restrisiko:** Mittel – Decoder-Bugs in FFmpeg bleiben ein Restrisiko bei fremden Videos (zbar nur im
Legacy-PoC).

---

## 5. Pfad-Traversal über Dateinamen aus fremden QR-Codes (T5)

**Gefahr:** Dateinamen der Dateiliste stammen aus dem (entschlüsselten) Management-QR-Code bzw. aus Video-/GPG-Dateinamen
und werden mit `os.path.join` an Zielordner gehängt (`decrypt_file`, `startup_multithreading`). Ein Name wie
`..\..\Autostart\x.bat` oder ein absoluter Pfad schreibt außerhalb des Arbeitsordners.

**Mitigation:**
- I7 umgesetzt: `qrvideo.paths.safe_filename` (nur Basisname, Steuer-/Pfadzeichen ersetzt, reservierte Windows-Namen
  entschärft); `qrvideo receive` überschreibt keine vorhandene Datei ohne `--force`. Format v2 überträgt keine
  Dateinamen mehr im Video.
- Tests: `tests/test_qrvideo_cli.py::test_safe_filename` (`..`, absolute Pfade, Laufwerk, `CON`, Steuerzeichen),
  `tests/test_qrvideo_crypto.py::test_cli_send_and_receive` (kein Überschreiben)
- Seit I29a: Verweise im Ordner-Kanal sind reine Dateinamen (`safe_filename(ref) == ref`, sonst `ValueError`) —
  `../x`, absolute Pfade, Laufwerke und reservierte Namen verlassen den Kanal-Ordner nie; Abholen überschreibt nie
  (`tests/test_qrvideo_channel.py`)

**Restrisiko:** Hoch (Legacy-PoC) / Gering (`qrvideo`).

---

## 6. Code-Ausführung über manipulierte `.npy`-Lookup-Tabellen (T6)

**Gefahr:** `legacy/qrcodegenmod.py` lädt fünf Tabellen mit `numpy.load(..., allow_pickle=True)` relativ zum
Arbeitsverzeichnis. Wer eine `.npy` im CWD platzieren kann, führt beim Import beliebigen Code aus (Pickle, vgl.
CVE-2019-6446).

**Mitigation:**
- Seit I2: `src/qrcodegenmod/` berechnet die Tabellen beim Import (kein `.npy`, kein Pickle); `legacy/` bleibt
  unverändert
- `allow_pickle=True` per Konvention verboten (`CONVENTIONS.md` §4)

**Restrisiko:** Hoch (Legacy-Modul) / Gering (`qrcodegenmod` 2.0).

---

## 7. Credential-Exposition (Passphrase, OAuth) (T7)

**Gefahr:** Eine GnuPG-Passphrase steht als Konstante im versionierten Legacy-Code (`legacy/poc/POC.py`, `main()`,
Zeile ~1801, teilweise maskiert; Wert wird hier bewusst nicht zitiert). OAuth-Client (`client_secrets.json`) und
Token (`*-oauth2.json`) liegen im Programmordner und könnten mitcommittet werden.

**Mitigation:**
- I5: Konstante entfernen, Passphrase über gpg-agent/pinentry oder Umgebung; Schlüssel als kompromittiert behandeln;
  Historie vor Veröffentlichung bereinigen (ADR)
- `.gitignore` für OAuth-Dateien; seit I7 Token unter `%APPDATA%\qrvideo\youtube-token.json`, Client per
  `--client-secrets`; `operations/SECRETS_MANAGEMENT.md`

- GUI (seit I20b): fragt keine Passphrase ab und speichert keine — gpg-agent/pinentry übernimmt; die GUI liest
  `QRVIDEO_PASSPHRASE` bewusst nicht
- Seit I30a: `download --cookies-from-browser` lässt yt-dlp die Anmeldung eines Browsers lesen (das ist eine
  Sitzung des Google-Kontos). Nur auf ausdrücklichen Wunsch, nie Standard, nie beim Ordner-Kanal; `qrvideo`
  speichert und protokolliert die Cookies nicht, yt-dlp nutzt sie für diesen einen Abruf. Empfehlung: ein eigenes
  Browserprofil nur für den Empfang

**Restrisiko:** Mittel seit I5 — der Arbeitsbaum ist bereinigt, die lokale Git-Historie enthält das Secret weiter
(ADR-002: nur ohne Historie veröffentlichen; Schlüsselrotation beim Schlüsselinhaber).

---

## Hinweise

- Dieses Dokument wird bei jeder neuen Funktion geprüft, die externe Eingaben verarbeitet
  oder auf sensible Ressourcen zugreift — anhand der Leitfragen in `security/THREAT_MODEL_GUIDE.md`.
- Neue Bedrohungen als ADR dokumentieren wenn sie eine Architekturentscheidung auslösen.
