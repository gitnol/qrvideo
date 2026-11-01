# ADR-005: Austauschbarer Transportkanal hinter einer Kanal-Schnittstelle

**Status:** Accepted
**Datum:** 2026-10-27

## 1. Kontext & Problem

Der Videokanal ist bisher fest YouTube: `qrvideo.youtube` (yt-dlp, YouTube Data API), direkt aufgerufen von
`qrvideo download`/`upload` und vom GUI-Reiter „Empfangen“ (`youtube.download`); der Handshake führt Videos nur als
YouTube-IDs. YouTube ist fragil (Nutzungsbedingungen, Kompression, API-Freigabe für Uploads, Sperren nicht
verifizierter Projekte; `BACKLOG.md`). Kodieren und Dekodieren arbeiten seit I4/I7 ohnehin auf lokalen Videodateien —
nur das Bereitstellen und Abholen des Videos hängt an YouTube. Ein zweiter Kanal (z. B. ein gemeinsamer
Sync-Ordner wie NextCloud, ein anderer Hoster, später Bildschirm-zu-Kamera) soll ohne Eingriff in CLI-Logik,
GUI-Presenter oder Containerformat ergänzt werden können.

## 2. Betrachtete Alternativen

* **A: So lassen** — jeder neue Kanal bekommt eigene Unterbefehle und eigene Sonderfälle im GUI-Presenter.
* **B: Kanal-Schnittstelle (`typing.Protocol`) mit Adaptern** — `qrvideo.channel` definiert, was ein Kanal kann
  (Verweis erkennen, Video abholen, Video bereitstellen, Verweis anzeigen); `YouTubeChannel` umhüllt das bestehende
  `qrvideo.youtube`, `FolderChannel` legt Videos in einem gemeinsamen Ordner ab. CLI und GUI hängen nur an der
  Schnittstelle, der Kanal wird gewählt bzw. injiziert.
* **C: Plugin-System über Entry-Points** — Kanäle als installierbare Pakete, zur Laufzeit entdeckt.
* **D: Allgemeines Speicher-Backend (fsspec o. Ä.)** — beliebige URLs, neue Abhängigkeit.

## 3. Entscheidung

Alternative B. `qrvideo.channel` enthält das Protokoll `Channel` und zwei Adapter:

* `YouTubeChannel(client_secrets=None)` — Verweis = Video-ID (URL wird erkannt), Abholen per yt-dlp, Bereitstellen
  per YouTube Data API (nur mit `client_secrets`; sonst lädt der Nutzer selbst in YouTube Studio hoch).
* `FolderChannel(root)` — Verweis = Dateiname in `root`; Bereitstellen kopiert atomar unter neutralem Namen hinein,
  Abholen kopiert heraus. Ein Verweis darf `root` nie verlassen (nur ein Dateiname, über `safe_filename` geprüft).

Die CLI wählt den Kanal mit `--channel youtube|folder` (Standard `youtube`, Verhalten unverändert); der GUI-Presenter
„Empfangen“ bekommt einen `Channel` statt einer Download-Funktion. Der Handshake bleibt vorerst bei YouTube-IDs: ein
kanalneutraler Verweis ändert das Nachrichtenformat (Version 2) und folgt als eigenes Inkrement.

## 4. Begründung

* Es gibt genau einen echten und einen zweiten, sofort nützlichen Kanal; ein Plugin-System (C) löst ein Problem, das
  dieses Projekt nicht hat, und vergrößert die Angriffsfläche (fremder Code beim Start).
* D bringt eine Abhängigkeit für einen Fall, den `shutil` abdeckt, und verwischt die Kanal-Besonderheiten (YouTube
  braucht 1080p-Formatwahl und OAuth, kein generisches „open URL“).
* `typing.Protocol` passt zu den bestehenden Nahtstellen (`CryptoLike`, injizierte Funktionen in den Presentern,
  ADR-004): Tests setzen Attrappen ein, ohne Netz.
* Der Ordner-Kanal ist der kleinste zweite Kanal, an dem sich die Schnittstelle beweisen muss, und praktisch: Sender
  und Empfänger teilen oft schon einen Sync-Ordner. Er läuft offline und ist vollständig testbar.

## 5. Konsequenzen

* **Positiv:** Neue Kanäle = neue Klasse + Eintrag in `make_channel` und `CHANNEL_NAMES`; CLI und GUI bleiben unberührt. YouTube-Ausfälle
  (Sperre, ToS) haben einen Ausweg ohne Codeänderung. Die YouTube-Abhängigkeiten bleiben optional (`[youtube]`).
* **Negativ/Risiken:** Der Ordner-Kanal transportiert ein Video, das man auch direkt (ohne QR) teilen könnte — sein
  Wert ist Austauschbarkeit und Test der Schnittstelle, nicht die QR-Robustheit. Metadaten (Threat T1): Dateiname
  im Ordner ist neutral (`qrvideo-<8 Hex>.mp4`), Zeitstempel und Größe bleiben sichtbar wie bei YouTube.
  Der Handshake ist bis zum Folge-Inkrement noch an YouTube gebunden (seit I29c1 nicht mehr, Abschnitt 6).

## 6. Nachtrag (I29c1, 2026-10-28)

Der Handshake schreibt seit I29c1 Nachrichtenformat Version 2: Videos als `<kanal>:<verweis>`, geprüft ohne den Kanal
zu öffnen (`parse_channel_ref`; der Kanal-Ordner des Absenders ist dem Empfänger unbekannt). Version 1 bleibt lesbar.
Damit hängt kein Teil des Ablaufs mehr fest an YouTube.
