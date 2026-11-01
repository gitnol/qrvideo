# ADR-004: Desktop-GUI mit Tkinter/ttk und Tk-freien Presentern

**Status:** Accepted
**Datum:** 2026-10-27

## 1. Kontext & Problem

`qrvideo` ist nur über die Kommandozeile bedienbar (Unterbefehle, KeyIDs als Argumente). Die Zielgruppe der GUI sind
Menschen ohne Kommandozeilen-Kenntnis unter Windows: Datei wählen, Empfänger ankreuzen, Fortschritt sehen, Ergebnis
öffnen. Lange Vorgänge (Rendern mit Prozess-Pool, ffmpeg, gpg, yt-dlp) dürfen die Oberfläche nicht blockieren und
müssen abbrechbar sein. Gleichzeitig ändert eine parallele Session (I17) Containerformat und CLI; die GUI darf die
Kernmodule unter `src/qrvideo/` und `src/qrcodegenmod/` nicht anfassen.

## 2. Betrachtete Alternativen

* **Tkinter/ttk** (Standardbibliothek, Tk 8.6, Windows-Theme „vista“) — gewählt
* **PySide6/Qt**: modernes Aussehen, aber ~150 MB zusätzliche Abhängigkeit, LGPL-Pflichten bei Weitergabe, eigener
  Event-Loop und Thread-Regeln
* **Web-Oberfläche** (lokaler HTTP-Server + Browser, z. B. NiceGUI/Flask): offener Port auf dem Rechner, neue
  Angriffsfläche (CSRF auf localhost), mehrere neue Abhängigkeiten, Dateiauswahl im Browser liefert keine Pfade
* **wxPython / Dear PyGui / Toga**: neue Abhängigkeit ohne Vorteil gegenüber Tk für wenige Formulare

## 3. Entscheidung

Neues Paket `src/qrvideo_gui/` mit Tkinter/ttk, Einstiegspunkt `qrvideo-gui` (Console-Script). Aufbau nach
Model-View-Presenter:

* **Presenter** (`send.py`, `receive.py`, `handshake.py`, `keys.py`) enthalten die Logik ohne Tk-Import: Eingaben
  prüfen, Zielpfade über `qrvideo.paths.safe_filename` bilden, Überschreiben erkennen, `qrvideo`-Funktionen aufrufen.
  Abhängigkeiten (Crypto, Download) werden als Fabrik übergeben → mit Fakes testbar.
* **Hintergrund-Jobs** (`jobs.py`): ein Thread je Vorgang, Fortschritt und Ergebnis über eine `queue.Queue`, die das
  Tk-Fenster per `after()` abholt (Tk ist nicht threadsicher). Abbrechen setzt ein `threading.Event`; die zählenden
  Wrapper um den Frame-Generator (Senden) bzw. den Frame-Leser (Empfangen) werfen beim nächsten Frame `Cancelled`.
* **Fehlertexte** (`errors.py`): Ausnahmen werden in verständliche deutsche Meldungen übersetzt; Tracebacks gehen
  nur ins Log.
* **Views** (`*_view.py`, `app.py`): nur Widgets und Verdrahtung.

## 4. Begründung

* Keine neue Abhängigkeit (`docs/principles/STDLIB_FIRST.md`); läuft mit dem vorhandenen `uv`-Setup, Tk ist in den
  python.org- und uv-Builds für Windows enthalten (geprüft: Tk 8.6 in der Projekt-venv).
* Wenige Formulare mit Dateiauswahl, Checkliste, Fortschrittsbalken — dafür reicht ttk.
* Kein Netzwerk-Port: Die GUI ist ein lokaler Prozess wie die CLI, das Bedrohungsmodell bleibt gleich.
* Presenter ohne Tk lassen sich mit pytest ohne Display testen; die View bleibt dünn.
* Fortschritt ohne Kernänderung: `qrvideo.videoio.write_video` nimmt jeden Frame-Iterator, `qrvideo.container.plan_frames`
  liefert die Gesamtzahl, `qrvideo.decoder.decode_frames` nimmt jeden Frame-Iterator.

## 5. Konsequenzen

* **Positiv:** keine Abhängigkeit, kleiner Code, testbare Logik, die CLI bleibt unverändert.
* **Negativ/Risiken:** Tk wirkt weniger modern; YouTube-Download und ein einzelner gpg-Aufruf sind nicht mitten im
  Vorgang abbrechbar (Abbruch greift danach); der Signaturschlüssel wird aus den vertrauten Schlüsseln gewählt, weil
  `Crypto` (Kernmodul) keine Liste geheimer Schlüssel anbietet; Tests der Views brauchen ein Display (Smoke-Test wird
  sonst übersprungen).
