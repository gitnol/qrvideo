# ADR-001: Containerformat v2 und eigener QR-Reader statt pyzbar

**Status:** Accepted
**Datum:** 2026-10-26

## 1. Kontext & Problem

Die Thesis (2019) übertrug ASCII-armored GnuPG-Text in Chunks à 2100 Zeichen. Slot 0 jedes Frames enthielt einen
pro Frame neu mit GnuPG verschlüsselten und signierten Status (ein `gpg`-Prozess pro Frame). Gelesen wurde mit pyzbar:
Ausschnitt binarisieren (2×2-Mittelwert, Schwelle 128), weißen Rand anfügen, pyzbar sucht die Finder-Muster erneut.
Der Decoder ignorierte Slot 0 („später implementieren"), Reihenfolge und Lücken wurden nicht geprüft. Pyzbar braucht
eine native zbar-DLL.

## 2. Betrachtete Alternativen

* Thesis-Format beibehalten (Armor-Text, verschlüsselter Status pro Frame, pyzbar)
* Binäre Nutzlast, Klartext-Kopf mit Zählern und SHA-256, pyzbar zum Lesen
* Binäre Nutzlast, Klartext-Kopf, eigener Reader auf der bekannten Modul-Matrix (gewählt)

## 3. Entscheidung

Format v2 (`src/qrvideo/container.py`): Rohbytes der `.gpg`-Datei in V40-QR-Codes (ECC MEDIUM: 2331 Bytes je QR),
Slot 0 enthält einen 55-Byte-Kopf `QRV2 | Frame | Frames | Länge | Chunkgröße | ECC | SHA-256`. Gelesen wird mit
`qrcodegenmod.reader` direkt aus der abgetasteten Modul-Matrix. Thesis-Videos bleiben über `decode_video(legacy=True)`
lesbar.

## 4. Begründung

* Gemessen: Das Original-YouTube-Video der Thesis (90 Frames, 1197 Daten-QR) wird mit dem eigenen Reader ohne einen
  einzigen Fehlschlag und bytegenau zur damaligen `.pgp` dekodiert (`tests/test_qrvideo_video.py`); Reed-Solomon
  korrigierte dabei 45 172 Bytes. Die Thesis-Geometrie ist fest, eine Bildsuche ist unnötig.
* Binär statt Base64: 2331 statt 1575 Nutzbytes pro QR bei gleicher ECC-Stufe (+48 %). Die Thesis-Chunks à 2100
  Zeichen wurden durch `boostecl` ohnehin auf ECC MEDIUM gehoben.
* Der Kopf muss nicht verschlüsselt sein: Er enthält nur Zähler, Länge und Hash; Vertraulichkeit und Echtheit
  liefert die signierte, verschlüsselte Nutzlast. Pro Frame entfällt ein `gpg`-Aufruf.
* Der Kopf erlaubt, was die Thesis als TODO vermerkte: doppelte/vertauschte Frames einordnen, Lücken melden, Ergebnis
  per SHA-256 prüfen.

## 5. Konsequenzen

* **Positiv:** keine native zbar-Abhängigkeit; Lückenerkennung; mehr Nutzlast; schnelleres Encoding.
* **Negativ/Risiken:** Der Reader setzt die feste Geometrie voraus (kein Abfotografieren vom Bildschirm); Frame-
  Zähler und Größe der Nutzlast sind im Video sichtbar (vorher verschlüsselt); v2-Videos sind mit dem Thesis-PoC
  nicht lesbar.
