# Feature: QR-Video-Übertragung

---

## Zweck

Eine Datei wird GnuPG-verschlüsselt und signiert für 1..n vertraute Empfänger als Video aus QR-Codes kodiert, über
einen Kanal übertragen — YouTube (unlisted, Standard) oder seit I29 einen gemeinsamen Ordner (ADR-005) — und beim
Empfänger wieder zur Originaldatei zusammengesetzt und entschlüsselt.
Nutzer: Sender (`qrvideo send`, `upload`) und Empfänger (`qrvideo download`, `receive`), seit I7; im Legacy-PoC
Server- bzw. Clientmodus des Konsolenmenüs.

---

## Technologie / Abhängigkeiten

- `qrcodegenmod` 2.0: QR-Matrizen V40 / Maske 1 erzeugen und (`reader`) aus abgetasteten Modulen lesen
- `src/qrvideo/`: `layout.py` (Frame-Geometrie), `container.py` (Format v2), `encoder.py` (Prozess-Pool),
  `videoio.py` (ffmpeg-Pipe über `imageio-ffmpeg`, libx264, yuv420p, 30 fps), `decoder.py` (v2 und Thesis-Videos)
- seit I7: `crypto.py` (`python-gnupg` + GnuPG), `youtube.py` (Download per `yt-dlp`, Upload per YouTube Data API
  mit `google-auth-oauthlib`), seit I29 `channel.py` (Kanal-Schnittstelle), `paths.py` (`safe_filename`), `cli.py` (Befehl `qrvideo`), `cli_handshake.py` (Handshake-Befehle, seit I26)
- pyzbar und OpenCV entfallen (ADR-001)

---

## Datenstrukturen

Frame-Geometrie (Thesis, v2 und v3 identisch, `qrvideo.layout.FrameLayout`); Modulgitter von Slot (r, c) beginnt
bei Pixel (1 + 362 r, 1 + 362 c). Der Block beschreibt das **Thesis-Format v1** (2019, nur noch `decode --legacy`);
v2 und v3 ersetzen Text-Chunks und Management-QR, siehe unten:

```python
CHUNK_LEN: int = 2100            # Zeichen ASCII-Armor pro Daten-QR-Code
QR_VERSION, ECC, MASK = 40, "LOW", 1
QR_SCALE, QR_BORDER = 2, 2       # Pixel pro Modul, Rand in Modulen
GRID_ROWS, GRID_COLS = 3, 5      # 15 QR-Codes pro Frame
FRAME_SHAPE = (1080, 1920)       # Graustufen uint8
# v1: Position 0 jedes Frames: Management-QR-Code (verschlüsselt + signiert):
#   Framezähler, Dateiliste/Video-Links; Positionen 1..14: Daten-Chunks, leere Plätze weiß
```

Format v2 (`qrvideo.container`, ADR-001): Slot 0 = 55-Byte-Kopf
`QRV2 | Frame (u32) | Frames (u32) | Länge (u64) | Chunkgröße (u16) | ECC (u8) | SHA-256`, Slots 1..14 = Rohbytes
der `.gpg`-Datei, je QR bis zu 2331 Bytes (ECC MEDIUM; LOW 2953, QUARTILE 1663, HIGH 1273).

Format v3 (ADR-003, seit I17b): Kopf `QRV3 | Frame | Frames | Länge | Chunkgröße | ECC | k | m | SHA-256`, aufgefüllt mit
`SHAKE-128(Kopf)` auf 2331 Bytes (ECC M); jeder Daten-QR beginnt mit `Symbolindex (u32) | CRC32 (u32)`,
danach bis zu Kapazität − 8 Bytes (ECC L: 2945). Daten-QR sind ohne den Kopf ihres Frames einzuordnen; CRC-Fehler
gelten als Auslöschung. Symbolfolge Gruppe für Gruppe: k Daten-, dann m Paritätssymbole.
Seit I17d: `--parity <Prozent>` (10 → k = 126, m = 14 je 10 Frames) schreibt v3, seit I18 Standard mit ECC L; die
letzten 3 Frames werden als Nachlauf wiederholt. Je Gruppe heilt der Decoder bis zu m fehlende Daten-QR
(unlesbar, CRC falsch, Frame fehlt); darüber meldet er „Gruppe g: … Datensymbole fehlen“.

Handshake (`qrvideo.handshake`, seit I8a): JSON `{"v": 2, "kind": "challenge", "files": [...], "videos": [...]}` bzw.
`{"v": 2, "kind": "response", "selection": "..."}`, verschlüsselt und signiert als ASCII-Armor; Felder werden
per Name gelesen (K10 kann nicht auftreten), Dateinamen über `safe_filename`. Seit I29c1 (ADR-005) schreibt
`qrvideo` Version 2: Videos als `<kanal>:<verweis>` (`youtube:<Video-ID>`, `folder:<Dateiname>`), geprüft vom
genannten Kanal (`qrvideo.channel.parse_channel_ref`); eine Auswahl mit Doppelpunkt muss ein solcher Verweis sein,
sonst ist sie ein Dateiname. Version 1 (nackte YouTube-IDs, I8a–I29b) bleibt lesbar und wird zu `youtube:<ID>`;
ältere `qrvideo`-Stände (I8a–I29b) lesen Version 2 nicht.
Seit I8b zusätzlich als QR-PNG (`qrvideo.qrpng`: ECC MEDIUM, kleinste Version, Skalierung 4, Rand 4); gelesen
werden nur pixelgenau gerenderte Bilder (Modulgröße aus dem Finder-Muster), kein Abfotografieren.

Handshake-Artefakte (Thesis): „Server Challenge" (Dateiliste, Links) und „Client Response" (Auswahl) als verschlüsselte,
signierte QR-Code-PNGs, übertragbar über beliebige Kanäle; alternativ als eingefügter PGP-Text.

---

## Kritische Patterns

- Erst entschlüsseln und Signatur/Trust prüfen, dann den Inhalt parsen — nie umgekehrt.
- Dateinamen aus fremden Inhalten nur als sanitisierter Basisname verwenden (`security/THREAT_MODEL.md` T5).
- Frame-Layout und Chunk-Länge müssen auf Sender- und Empfängerseite identisch sein; Änderungen sind ein
  Formatwechsel (ADR, Versionsfeld im Management-QR-Code).
- `qrcodegenmod`-Änderungen nur mit grünem Orakel-Vergleich (Bit-Gleichheit).

---

## Bekannte Einschränkungen

| Einschränkung | Ursache | Status |
|---------------|---------|--------|
| Download/Upload gegen das echte YouTube ungetestet | `youtube_dl`/`oauth2client` seit I7 durch `yt-dlp`/`google-auth-oauthlib` ersetzt, nur mit Attrappe getestet | Offen (Backlog: Live-Test) |
| Videodateiname wählt der Nutzer | seit I27a: Empfänger verborgen, Originalname verschlüsselt, zufälliger Upload-Titel; `send -o` nimmt den Namen, den der Nutzer angibt | Akzeptiert (CLI); die GUI schlägt seit I27b2 einen zufälligen Namen vor |
| Ohne Fehlertoleranz über Frames mit `--parity 0` | v2 erkennt fehlende Frames nur; der Standard v3 heilt bis zu m Ausfälle je Gruppe, live auf YouTube bytegenau (I17e) | Akzeptiert (v2 nur noch auf Wunsch) |
| Reader braucht die feste Geometrie | keine Bildsuche (ADR-001) | Akzeptiert |
| Prozess-Pool unter Windows (spawn) | Aufrufer braucht `if __name__ == "__main__":` | Akzeptiert, dokumentiert |

---

## Bekannte Fallstricke

- YouTube re-encodiert immer; Grauwerte von Schwarz/Weiß verschieben sich (BT.709, 16–235) — der Decoder mittelt
  2×2 Pixel je Modul und binarisiert bei 128 (wie `analyze_video.youtube_qrcode_korrektur`); Reed-Solomon korrigiert
  den Rest (Thesis-Video: Ø 35 Bytes je QR).
- Verlustfreies H.264 (`crf 0`) gibt es nur im Profil `high444` — deshalb setzte die Thesis es zu yuv420p.
- Legacy-PoC: `imageio.mimwrite` gibt bestimmte `-x264-params` nicht korrekt an ffmpeg weiter (Kommentar in
  `write_video_file_segment`); `qrvideo.videoio` schreibt seit I4 direkt über die ffmpeg-Pipe.
- Legacy-PoC: Signatur-/Trust-Prüfung per `assert` entfällt mit `python -O` (`KNOWN_ISSUES.md` K5); `qrvideo.crypto`
  prüft seit I7 per `raise` (`UntrustedSignatureError`).

---

## Teststrategie

- Zugehörige Testdateien: `tests/test_equivalence.py`, `tests/test_reader.py`, `tests/test_qrvideo_frames.py`,
  `tests/test_qrvideo_video.py` (Marker `integration`, enthält das Original-YouTube-Video der Thesis als Orakel),
  `tests/test_qrvideo_crypto.py` (Marker `integration`, temporärer Schlüsselbund), `tests/test_qrvideo_cli.py`
- Kritische Testfälle: Bit-Gleichheit gegen `qrcodegen`; Chunking inkl. Rest; Management-QR an Position 0; lokaler
  Roundtrip byte-gleich; nicht vertraute Signatur wird abgelehnt; Pfad-Traversal-Namen werden auf den Basisnamen entschärft (`safe_filename`)
- Live (manuell, `QRVIDEO_LIVE=1`): Thesis-Video seit I9a, v2-Video nach manuellem Upload seit I9b; der
  API-Upload ist ungetestet (Backlog)
