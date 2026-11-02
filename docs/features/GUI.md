# Feature: Desktop-GUI `qrvideo-gui`

---

## Zweck

Bedienung von `qrvideo` ohne Kommandozeile unter Windows: Datei senden, Video empfangen, Handshake, vertraute
Schlüssel ansehen. Zielgruppe sind Menschen ohne Kommandozeilen-Kenntnis (seit I20b, Entscheidung ADR-004).

Start: `uv run qrvideo-gui` (optional `--gnupghome <Ordner>` für einen eigenen Schlüsselbund,
`--lang de|en|es` für die Sprache) oder `python -m qrvideo_gui`.

Sprache (seit I33i, ADR-006): Deutsch, Englisch, Spanisch. Menü „Sprache“ speichert die Wahl in
`%APPDATA%\qrvideo\settings.json` (sonst `$XDG_CONFIG_HOME/qrvideo/settings.json`); sie gilt nach einem Neustart.
Vorrang beim Start: `--lang` → `QRVIDEO_LANG` → gespeicherte Wahl → Sprache des Systems → Englisch. Ist
`QRVIDEO_LANG` gesetzt, überstimmt sie das Menü.

---

## Technologie / Abhängigkeiten

- Tkinter/ttk aus der Standardbibliothek (Tk 8.6), keine neue Abhängigkeit
- `src/qrvideo_gui/`: `jobs.py` (Hintergrund-Thread, Fortschritt, Abbruch), `errors.py` (Fehlertexte in der gewählten Sprache),
  `keys.py` (vertraute Schlüssel, Tk-frei), `widgets.py` (Job-Ereignisse im Tk-Thread abholen), `app.py`
  (Hauptfenster, Reiter „Schlüssel“, `main`), `__main__.py`; seit I21 `send.py` (Logik Senden, Tk-frei) und
  `send_view.py` (Reiter „Senden“), `widgets.py` mit Empfänger-Häkchen, Fortschrittsbalken, „Ordner öffnen“;
  seit I22 `receive.py` (Logik Empfangen, Tk-frei) und `receive_view.py` (Reiter „Empfangen“); seit I23
  `handshake.py` (Logik Handshake, Tk-frei) und `handshake_view.py` (Reiter „Handshake“)
- Ruft nur vorhandene Funktionen aus `src/qrvideo/` auf; die Kernmodule bleiben unverändert

---

## Bildschirmaufbau

| Reiter | Inhalt | Stand |
|---|---|---|
| Schlüssel | Tabelle der voll/ultimativ vertrauten Schlüssel (Name, Vertrauen, Fingerabdruck in Vierergruppen; Spaltenbreiten aus der Schrift berechnet, seit I24 ohne eigene Spalte Schlüssel-ID), „Neu laden“, Hinweis auf Kleopatra | seit I20b |
| Senden | 1. Datei → 2. Empfänger ankreuzen → 3. eigener Signaturschlüssel (vorbelegt) → 4. Zielvideo (Vorschlag `qrvideo-<8 Hex>.mp4` daneben, seit I27b2 neutral — der Originalname reist verschlüsselt mit, Threat T1) → „Senden“/„Abbrechen“ → Fortschritt „Frame n von N“ → Ergebnis, „Ordner öffnen“, Hinweis YouTube Studio „Nicht gelistet“ | seit I21 |
| Empfangen | 1. Kanal (seit I32b): „YouTube“ mit optionaler Browser-Anmeldung `BROWSER[:PROFIL]` (yt-dlp `cookiesfrombrowser`, wie `--cookies-from-browser`) oder „Gemeinsamer Ordner“ mit Kanal-Ordner; es erscheinen nur die Felder des gewählten Kanals → 2. Videodatei oder Verweis im Kanal (YouTube-Link bzw. Dateiname im Kanal-Ordner; holt das Video über die Kanal-Schnittstelle, ADR-005, in den Ausgabeordner; eine lokale Datei braucht keinen Kanal) → 3. Ausgabeordner (Vorgabe: Downloads) → „Empfangen“/„Abbrechen“ → Fortschritt „Frames gelesen: n“ → Ergebnis mit Dateiname (seit I27b1 der verschlüsselt mitgereiste Originalname, sonst der Videoname; ist er belegt, `name (2).endung` — nie überschrieben), Größe, Signaturgeber, Fingerabdruck in Vierergruppen, gelesenen/unlesbaren QR-Codes, „Ordner öffnen“; Hinweis auf veraltetes FFmpeg | seit I22 |
| Handshake | links „Angebot erstellen“: Ordner mit Dateien, optionale Videos (YouTube-Link oder seit I29c2 `<kanal>:<verweis>`, z. B. `folder:<Dateiname>`; angezeigt als `youtube:<ID>` bzw. `folder:<Datei>`), Empfänger, Signatur, Ziel `.asc` (+ QR-Code-Bild `.png`); rechts „Nachricht öffnen und beantworten“: `.asc` oder `.png` öffnen → Absender und Fingerabdruck, Liste der Einträge → Eintrag wählen → Response an den Absender speichern | seit I23 |

Das Fenster lässt sich nicht kleiner ziehen als der größte Reiter braucht (bei 150 % Anzeige ca. 1380 × 790).
Unten eine Statuszeile; Fehler erscheinen im Reiter als Satz, nie als Traceback. Überschreiben eines vorhandenen
Videos nur nach Rückfrage, empfangene Dateien nie (freier Name); Schließen während eines Vorgangs fragt nach und bricht ihn ab. Das Rendern nutzt alle
Kerne bis auf einen (die Oberfläche bleibt bedienbar). Format und Qualität wie `qrvideo send`: seit I18 Format v3
mit ECC L und 10 % Parität, crf 12.

---

## Konfigurierbare Parameter (CLI)

| CLI-Argument | Default | Validierungsregel | Beschreibung |
|-------------|---------|------------------|-------------|
| `--gnupghome` | Schlüsselbund des Nutzers | Pfad | eigener GnuPG-Schlüsselbund (Tests, Demo) |

---

## Kritische Patterns

- Presenter/Logik ohne Tk-Import (`keys.py`, später `send.py`, `receive.py`, `handshake.py`) — testbar ohne Display
- Widgets nur im Tk-Thread anfassen; der Hintergrund-Thread meldet über `Job` (Queue), `widgets.watch` holt per
  `after()` ab
- Ausnahmen nie roh anzeigen: `errors.friendly_message`; unbekannte Ausnahmen nur ins Log
- Passphrase nie abfragen oder speichern: gpg-agent/pinentry fragt selbst
- Dateinamen nur über `qrvideo.paths.safe_filename` — auch der eingebettete Name ist fremde Eingabe (seit I27b1);
  Videos nur nach Rückfrage überschreiben, empfangene Dateien nie

---

## Bekannte Einschränkungen

| Einschränkung | Ursache | Status |
|---------------|---------|--------|
| Eigener Schlüssel = ultimativ vertrauter Schlüssel | `Crypto` (Kernmodul) liefert keine Liste geheimer Schlüssel | Akzeptiert (ADR-004); nach dem Merge mit I17 ggf. `Crypto.secret_keys()` |
| Abbruch greift bei gpg und YouTube-Download erst nach dem Aufruf | ein Aufruf ist nicht unterbrechbar | Akzeptiert (ADR-004) |
| Ältere Videos (vor I27a bzw. aus der GUI vor I27b2) tragen keinen Namen — die Datei heißt dann nach dem Video (über YouTube: nach der Video-ID) | Name reist erst seit I27a verschlüsselt mit | Akzeptiert (Rückfall) |
| YouTube-Download zeigt keinen Fortschritt | `youtube.download` bietet keinen Fortschritts-Hook | Akzeptiert (unbestimmter Balken) |
| Konsolenfenster neben der GUI | Console-Script statt `gui-scripts`: gpg/ffmpeg öffnen unter `pythonw` eigene Konsolen | Offen |

---

## Bekannte Fallstricke

- Zweites `tk.Tk()` im selben Prozess findet unter Windows sporadisch `tk.tcl` nicht → Tests nutzen ein `Tk` je
  Sitzung und `Toplevel` je Test (`tests/test_gui_app.py`)
- Prozess-Pool unter Windows (spawn): GUI nur über den Einstiegspunkt starten, nicht per Import mit Seiteneffekt
- Methoden von Reitern nicht `send` nennen: `ttk.Frame` erbt `tk.Misc.send` (Tk-Befehl `send`); mypy meldet es
- Den Frame-Generator bei Abbruch selbst schließen: Nur so endet der Prozess-Pool sofort und nicht erst per GC
- Hintergrund-Tasks dürfen keine Widgets erfassen, sonst gibt der Worker-Thread Tk-Objekte frei
  („main thread is not in main loop“); Tests räumen nach `destroy()` mit `gc.collect()` auf (LESSONS L8)

---

## Teststrategie

- Zugehörige Testdateien: `tests/test_gui_jobs.py`, `tests/test_gui_errors.py`, `tests/test_gui_app.py`,
  `tests/test_gui_send.py`, `tests/test_gui_receive.py`, `tests/test_gui_handshake.py`; gemeinsame Attrappen `tests/gui_fakes.py`, Tk-Fixtures in `tests/conftest.py`
- Kritische Testfälle: Abbruch nach genau einem Schritt; Fehlertexte ohne Klassennamen/Traceback; eigene Schlüssel
  zuerst; Smoke-Test Hauptfenster mit Fake-Crypto und ohne GnuPG; Senden: Fortschritt je Frame mit Gesamtzahl aus
  `plan_frames`, Überschreiben nur mit Bestätigung, Abbruch schließt die Frame-Quelle (Prozess-Pool); Empfangen:
  nicht vertraute Signatur oder Abbruch schreibt nichts, feindlicher Video- oder eingebetteter Name → sicherer Zielname im Ausgabeordner, belegter Name → `(2)`, `(3)` …, Link → Download
  in den Ausgabeordner; Handshake: Challenge als `.asc` und PNG (echt über `qrpng`), PNG öffnet wie Text,
  Response geht an den Absender, ungültige Auswahl/Video-Verweis/nicht vertraute Signatur abgelehnt
- Ende-zu-Ende (seit I24, `-m integration`): `tests/test_gui_roundtrip.py` — Senden → Empfangen und Handshake über
  die Presenter mit echtem GnuPG (getrennte Schlüsselbunde Alice/Bob/Carol), Prozess-Pool und ffmpeg;
  Mutationsprüfung 4/4 getötet
- Was nicht automatisiert getestet wird: Aussehen (per Screenshot geprüft, siehe unten), Tastaturbedienung,
  pinentry-Dialog, echter YouTube-Download

### Screenshots erneuern (seit I33j)

```powershell
uv run --with pillow python tools/screenshots.py            # alle Sprachen; --lang de en es wählt aus
```

Legt je Sprache Demo-Schlüsselbunde „Alice/Bob Beispiel“ (`@example.test`, ohne Passphrase) unter
`C:\Temp\qrvideo-demo` an (Pfad steht in den Bildern, daher kurz und neutral; darf nicht existieren), steuert die
echte GUI (Senden, Empfangen, Handshake mit GnuPG, Prozess-Pool und ffmpeg) und speichert
`docs/images/<sprache>/{keys,send-done,receive-done,handshake-offer,handshake-answer}.png` in natürlicher
Fenstergröße. Eine weiße Fläche hinter dem Fenster verhindert, dass in den runden Ecken der Desktop erscheint.
Danach werden die gpg-agents beendet und der Ordner gelöscht. Während der Aufnahme liegen die Fenster kurz im
Vordergrund; nur unter Windows erprobt.
