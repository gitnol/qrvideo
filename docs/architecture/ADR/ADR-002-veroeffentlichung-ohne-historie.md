# ADR-002: Veröffentlichung nur als frischer Stand ohne Git-Historie

**Status:** Accepted
**Datum:** 2026-10-26

## 1. Kontext & Problem

Der Import des Thesis-PoC (Commit `781ef21`) enthält in `legacy/poc/POC.py` eine teilweise maskierte
Passphrase-Konstante und Schlüssel-IDs bzw. Fingerprints der Thesis-Testschlüssel. I5 hat beides aus dem Arbeitsbaum
entfernt (Passphrase und Signaturschlüssel kommen jetzt aus `QRVIDEO_PASSPHRASE` und `QRVIDEO_SIGN_FINGERPRINT`).
Die alten Werte bleiben aber in der Historie. Das Repo hat keinen Remote; es gilt wegen des MIT-Upstreams als
potenziell öffentlich (`CONVENTIONS_COMMON.md` 3.1).

## 2. Betrachtete Alternativen

* Historie mit `git filter-repo` umschreiben
* Bei Veröffentlichung einen frischen Stand ohne Historie erzeugen; lokale Historie bleibt unverändert (gewählt)
* Nie veröffentlichen

## 3. Entscheidung

Eine Veröffentlichung erfolgt ausschließlich als neues Repo aus dem aktuellen Arbeitsbaum, z. B.
`git archive HEAD | tar -x -C <neues-verzeichnis>` und dort ein einzelner Initial-Commit. Die lokale Historie wird
nicht umgeschrieben. Vor der Veröffentlichung läuft der Interna-Scan (`REFLECTION.md` Schritt 1) über den neuen
Stand.

## 4. Begründung

* `filter-repo` ändert alle Commit-Hashes; `STATE.md`, `KNOWN_ISSUES.md` und das CHANGELOG verweisen auf sie. Das
  Umschreiben ist schwer umkehrbar und würde die Nachvollziehbarkeit der Wiederbelebung zerstören.
* Die lokale Historie verlässt den Rechner nicht (kein Remote); das Risiko entsteht erst bei einer Veröffentlichung,
  und genau dort setzt die Entscheidung an.
* Der Thesis-Stand bleibt über `legacy/` im veröffentlichten Stand erhalten, nur ohne die entfernten Werte.

## 5. Konsequenzen

* **Positiv:** Hashes in der Doku bleiben gültig; keine destruktive Operation; klare Regel für den Moment der
  Veröffentlichung.
* **Negativ/Risiken:** Wer das lokale Repo kopiert (z. B. über die NextCloud-Synchronisation), bekommt die
  Historie mit. Der Schlüssel aus der Thesis ist deshalb als kompromittiert zu behandeln: neue Passphrase bzw.
  neuer Schlüssel (Aufgabe des Schlüsselinhabers, nicht automatisierbar).
