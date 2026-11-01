# ADR-003: Format v3 — selbstbeschreibende Daten-QR und äußerer Erasure-Code über Frames

**Status:** Accepted
**Datum:** 2026-10-27

## 1. Kontext & Problem

Format v2 (ADR-001) schützt jeden QR-Code nur mit dem inneren Reed-Solomon-Code der QR-Norm. Die Kanalmessung I17a
(`bench/bench_channel.py`, Zahlen in `STATE.md`) zeigt zwei Ausfallarten, die der innere Code nicht heilen kann:

* **Kopf-QR:** Auf YouTube (2026, ECC M) erreichte der schlechteste Block des Kopf-QR 13 von 14 korrigierbaren
  Bytes, Daten-QR nur 3/14. 394 von 489 Kopf-Fehlern lagen auf den 30 Codewörtern, die sich zwischen Frames ändern —
  der übrige Kopf ist statisch. In v2 kostet ein unlesbarer Kopf alle 14 Daten-QR seines Frames, weil nur der Kopf
  den Frame-Index trägt.
* **Ganze Frames:** Eine bitratenbegrenzte Zweitkodierung (x264, 80/120 Mbit/s) zerstörte genau einen Frame am
  Videoende vollständig.

Zudem soll die ECC der Daten-QR von M (2331 Bytes) auf L (2953 Bytes, +27 %) sinken können.

## 2. Betrachtete Alternativen

* v2 beibehalten, nur ECC höher stellen (kostet Nutzlast, heilt keinen verlorenen Frame)
* Fountain-Code (LT/Raptor) über alle Symbole (ratenlos, aber mehr Overhead bei kleinen Dateien, deutlich mehr Code)
* Systematischer Reed-Solomon-Erasure-Code (Cauchy-Matrix über GF(256)) über Gruppen von Daten-QR (gewählt)
* Paritäts-QR „diagonal“ über Frames und Slots verteilen

## 3. Entscheidung

Format v3 (`src/qrvideo/container.py`):

* Jeder Daten-QR beginnt mit 8 Bytes `Symbolindex (u32) | CRC32 (u32)` über Index und Daten; Nutzbytes je QR =
  QR-Kapazität − 8 (ECC L: 2945). Daten-QR sind damit ohne den Kopf ihres Frames einzuordnen; ein CRC-Fehler (stille
  Fehlkorrektur des inneren Codes) gilt als Auslöschung.
* Kopf-QR (Slot 0, immer ECC M): `QRV3 | Frame | Frames | Länge | Chunkgröße | ECC | k | m | SHA-256` (59 Bytes),
  aufgefüllt bis zur vollen Kapazität (2331 Bytes) mit `SHAKE-128(Kopf)` — der Strom hängt über den Frame-Index vom
  Frame ab, der Kopf-QR wechselt dadurch vollständig wie ein Daten-QR.
* Äußerer Code: Gruppen aus k Daten- und m Paritätssymbolen (k ≥ 1, k + m ≤ 255), globale Symbolfolge Gruppe für
  Gruppe; Gruppen liegen an Framegrenzen (Standard 10 Frames = 140 Symbole), damit ein verlorener Frame genau eine
  Gruppe trifft. Paritätssymbole stehen am Ende ihrer Gruppe, nicht diagonal.
* v2 bleibt lesbar und über `--parity 0` wählbar; der Decoder erkennt das Format am Magic des Kopfes. Nachtrag I18: Nach der Live-Messung I17e ist v3 mit ECC L und 10 % Parität Standard von CLI und GUI.
* Nachtrag I17d — Nachlauf: v3 wiederholt die letzten 3 Frames. Eine bitratenbegrenzte Zweitkodierung zerstörte in der Nachbildung 2–3 Frames kurz vor dem Videoende, mehr als eine Gruppe mit m = 14 heilt; mit 3 Frames Nachlauf waren 6/6 Fälle bei 80 Mbit/s lesbar, ohne 0/6 (CHANGELOG I17d).

## 4. Begründung

* Gemessen statt vermutet: Die Ausfälle sind Kopf-QR und ganze Frames, nicht verstreute Bitfehler in Daten-QR. Ein
  Erasure-Code mit bekannten Positionen genügt — die Positionen liefern Symbolindex und CRC; Berlekamp-Massey über
  Frames ist unnötig.
* Ein Cauchy-RS-Code ist MDS: Beliebige k von k + m Symbolen genügen. Die Lage der Paritätssymbole ist daher für die
  Ausfalltoleranz gleichgültig; eine diagonale Verteilung brächte nichts. Entscheidend ist, dass korrelierte Ausfälle
  (ein Frame, ein Slot über alle Frames) höchstens m Symbole je Gruppe treffen — dafür sorgen Gruppengröße und m.
* Die Multiplikationstabelle über GF(256) existiert bereits (`qrcodegenmod._tables.MULTIPLY_TABLE`, gleiche
  Körperdarstellung wie der innere Code); kein neues Paket.
* 8 Bytes je QR (0,27 %) sind billiger als ein Kopf, der für jeden Frame überleben muss.

## 5. Konsequenzen

* **Positiv:** Ein unlesbarer Kopf kostet keine Daten mehr, solange irgendein Kopf im Video lesbar ist; mit m ≥ 14
  heilt jede Gruppe einen ganzen verlorenen Frame; stille Fehlkorrekturen führen nicht mehr zu falschen Bytes, sondern
  zu Auslöschungen; ECC L wird mit Parität vertretbar (bei G = 10, m = 14: 126 × 2945 = 371 070 statt
  140 × 2331 = 326 340 Nutzbytes je Gruppe, +13,7 %).
* **Negativ/Risiken:** Kopf-QR ist mit dem Füllstrom so teuer zu lesen wie ein Daten-QR; Symbolindizes verraten die
  Lage der Nutzlast nicht mehr als v2 (Frame-Zähler waren schon sichtbar); YouTube-Verhalten mit ECC L ist erst nach
  dem Live-Test (I17e) belegt; k + m ≤ 255 begrenzt die Gruppe auf 18 Frames.
