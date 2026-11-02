# ADR-006: Mehrsprachigkeit mit `gettext` und Katalogen im Paket

**Status:** Accepted
**Datum:** 2026-11-02

## 1. Kontext & Problem

Alle sichtbaren Texte von GUI (`qrvideo_gui`, rund 150) und CLI (`qrvideo`, rund 150 einschließlich Fehlermeldungen
und Hilfetexten) sind fest auf Deutsch, die CLI zudem in ASCII-Umschrift („Schluessel“). Der Nutzer wünscht ein
mehrsprachiges Werkzeug mit Deutsch, Englisch und Spanisch, weitere Sprachen sollen folgen, und je Sprache saubere
Screenshots für die Doku. Die technische Wahl liegt bei uns.

Eine Kopplung blockiert das Übersetzen: `qrvideo_gui/errors.py` ordnet `GpgError` über deutsche Textanfänge des Kerns
zu (`GPG_MISSING = "gpg nicht gefunden"` usw.). Wird der Kern übersetzt, greift die Zuordnung nicht mehr, und die GUI
zeigt statt eines Hinweises auf Gpg4win nur „GnuPG meldet einen Fehler“.

## 2. Betrachtete Alternativen

* **A: `gettext` der Standardbibliothek mit `.po`/`.mo` im Paket** — Quelltexte (msgids) englisch, je Sprache eine
  `.po`-Datei, daraus kompilierte `.mo`-Dateien als Paketdaten; Extrahieren und Kompilieren mit einem kleinen
  Skript in `tools/`.
* **B: wie A, Werkzeug Babel** als Dev-Abhängigkeit (`pybabel extract/update/compile`).
* **C: eigene Python-Wörterbücher** je Sprache (`MESSAGES["es"]["…"]`).
* **D: Laufzeitbibliothek** (z. B. `python-i18n`, Fluent).

## 3. Entscheidung

Alternative A.

* **Modul `qrvideo.i18n`** (Kern, damit CLI und GUI es nutzen dürfen; Schichtregel `qrvideo_gui → qrvideo`):
  `_()`, `ngettext()`, `N_()` (nur Markierung für Konstanten, übersetzt wird beim Gebrauch), `set_language()`,
  `resolve_language()`, `format_number()`. Eine Textdomäne `qrvideo` für beide Pakete.
* **Kataloge:** `src/qrvideo/locale/<sprache>/LC_MESSAGES/qrvideo.po` und `.mo`, ausgeliefert mit dem Wheel
  (hatchling nimmt Nicht-Python-Dateien der Paketordner mit). Sprachen: `de`, `en`, `es`. Neue Sprache = eine
  `.po`-Datei anlegen, kompilieren, Kürzel in `SUPPORTED` eintragen.
* **msgids englisch.** Deutsch wandert nach `de.po`. Die CLI bekommt dabei echte Umlaute statt der ASCII-Umschrift
  (bewusste, einzige sichtbare Änderung für deutsche Nutzer: Spanisch braucht ohnehin `á`, `ñ` auf der Konsole).
* **Werkzeug `tools/i18n_catalog.py`** (nur Standardbibliothek): `extract` sucht per `ast` alle Aufrufe von `_`,
  `N_`, `ngettext` mit Zeichenkettenliteral in `src/qrvideo` und `src/qrvideo_gui`, `update` gleicht die `.po`
  ab (neue Einträge leer, veraltete entfernt), `compile` schreibt die `.mo` deterministisch.
* **Gate (Test in Gate 4):** Für jede Sprache gilt: msgids im Code = msgids in der `.po`, kein leeres `msgstr`,
  gleiche Platzhalter `{name}` in msgid und msgstr, `.mo` = frisch kompilierte `.po`; `_()` nur mit Literal.
* **Sprachwahl, Vorrang absteigend:** CLI-Option `--lang` → Umgebungsvariable `QRVIDEO_LANG` → in der GUI
  gespeicherte Wahl (Einstellungsdatei im Benutzerprofil, I33i) → Sprache des Betriebssystems → Englisch.
  Nicht unterstützte Kürzel fallen auf die nächste Quelle zurück, `de_AT` → `de`.
* **Zahlen:** `format_number` mit eigener kleiner Tabelle (Tausender- und Dezimaltrennzeichen je Sprache, Spanisch
  nach CLDR erst ab fünf Stellen gruppiert) statt `locale.setlocale` (prozessweit, unter Windows mit anderen Namen).
* **Fehlerzuordnung zuerst:** `GpgError` bekommt Unterklassen (`GpgNotFoundError`, `EncryptError`, `DecryptError`,
  `RecipientsError`); die GUI ordnet per `isinstance` zu, nie mehr per Text (I33b, vor jeder Übersetzung).
* **Nicht übersetzt:** Protokollmeldungen (`logging`, Entwickler, englisch), Meldungen für Programmierfehler
  (interne Invarianten), `legacy/`.

## 4. Begründung

* STDLIB_FIRST: `gettext` ist der Standard für Python-Programme, kennt Pluralformen und Rückfall auf den msgid,
  und `.po` ist das Format, das Übersetzer und Werkzeuge (Poedit, Weblate) kennen — wichtig für „weitere Sprachen
  folgen“ und Muttersprachler-Korrekturen. C erfindet beides neu, D bringt eine Laufzeitabhängigkeit.
* B gegen A: Babel wäre nur Werkzeug; das eigene Skript braucht rund 150 Zeilen, keine neue Abhängigkeit
  (kein Lock-Update, kein Security-Sweep), und die Prüfung der Platzhalter und der `.mo`-Aktualität schreibt man
  ohnehin selbst. Wird das Skript zur Last, ist der Wechsel zu Babel ohne Formatänderung möglich.
* Englische msgids: Rückfall bei fehlender Übersetzung ist dann Englisch, die Lingua franca der übrigen Sprachen.
* Unterklassen statt Fehlercodes: Das Projekt nutzt bereits spezifische Klassen (`UntrustedSignatureError`,
  `architecture/ERROR_HANDLING.md`); bestehende `except GpgError` fangen weiterhin alles.

## 5. Konsequenzen

* **Positiv:** Neue Sprache ohne Codeänderung außer dem Kürzel; Übersetzungsfehler (fehlend, Platzhalter falsch,
  `.mo` veraltet) fallen im Gate auf. GUI-Fehlertexte hängen nicht mehr am Wortlaut des Kerns.
* **Negativ/Risiken:** Sprache ist prozessweiter Zustand (`set_language`), wie bei `gettext` üblich; Tests setzen
  sie per Fixture (Standard Deutsch, damit bestehende Prüfungen gelten). Texte in Modulkonstanten müssen mit `N_`
  markiert und beim Gebrauch übersetzt werden, sonst bleiben sie in der Startsprache. Ausnahmetexte entstehen in
  der Sprache zum Zeitpunkt des Auslösens. Spanisch ist ohne Muttersprachler-Prüfung geschrieben (Hinweis in der
  Doku). Die GUI wechselt die Sprache erst nach Neustart.
