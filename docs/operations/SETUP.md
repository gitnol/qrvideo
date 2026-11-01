# Entwicklungsumgebung Setup – Revival_2026 (QR-Code-Videokanal)

---

## Voraussetzungen

- Python ≥ 3.11, Entwicklung auf 3.13 (`uv python install 3.13`)
- [uv](https://docs.astral.sh/uv/) als Paket- und Projektverwaltung (statt pip/venv von Hand)
- Für `qrvideo` (seit I7): GnuPG ≥ 2.4.9 (`gpg --version`) für `send`/`receive`/`keys`; ffmpeg kommt über
  `imageio-ffmpeg`. zbar/`pyzbar` braucht nur der Legacy-PoC (`qrvideo` hat einen eigenen Reader, ADR-001)
- Für den YouTube-Upload (optional): eigenes Google-Cloud-Projekt mit OAuth-Client (`client_secrets.json`, nie committen)
- Für die Bibliothek `qrcodegenmod` allein: keine Credentials, kein Netz

---

## Installation

Der Projektordner liegt in NextCloud. Die venv darf **nicht** im Projektordner liegen, sonst wird sie synchronisiert.

### Windows (PowerShell)

```powershell
# dauerhaft für den Benutzer setzen
[Environment]::SetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", "$env:LOCALAPPDATA\venvs\revival_2026", "User")
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\venvs\revival_2026"

uv sync                 # legt die venv am obigen Ort an, installiert Projekt + Dev-Gruppe
uv sync --extra all     # zusätzlich Extras jit, video, crypto, youtube (für qrvideo)
uv run python -c "import qrcodegenmod; print('OK')"
uv run qrvideo --help
```

### Git Bash / Linux

```bash
export UV_PROJECT_ENVIRONMENT="$LOCALAPPDATA/venvs/revival_2026"   # Linux: z. B. ~/.local/share/venvs/revival_2026
uv sync
uv run pytest
```

Interna-Hooks pro Klon aktivieren (Repo gilt als potenziell öffentlich, `CONVENTIONS_COMMON.md` 3.1):

```bash
git config core.hooksPath tools/git-hooks
cp <docs_template>/repo-root/.internal-terms.example .internal-terms   # lokal, gitignored; Begriffe eintragen
```

---

## Externe Tools

### GnuPG

**Zweck:** Ver-/Entschlüsselung und Signatur (über `python-gnupg`) in `qrvideo` und im Legacy-PoC.

**Windows:** Gpg4win installieren. `qrvideo` sucht über `qrvideo.crypto.find_gpg_binary`: `QRVIDEO_GPG`, dann
`C:\Program Files\GnuPG\bin\gpg.exe` (bzw. `Program Files (x86)`), dann `gpg` im PATH ohne die gpg aus Git for
Windows. Der Legacy-PoC erwartet einen festen Installationspfad (`KNOWN_ISSUES.md` K3).

**Linux:**
```bash
sudo apt install gnupg
```

> Ohne GnuPG: kein Fallback — die Pipeline bricht ab; die Bibliothek `qrcodegenmod` ist nicht betroffen.

### zbar

**Zweck:** nur Legacy-PoC — QR-Codes aus Frames und PNGs lesen (`pyzbar`). Unter Windows liefern die
`pyzbar`-Wheels die DLLs mit; Linux: `sudo apt install libzbar0`.

> Ohne zbar: im Legacy-PoC kein Rückweg (Dekodieren). `qrvideo` braucht zbar nicht.

---

## Wichtige Commands

```bash
uv run pytest -m "not slow and not integration"   # Unit-Tests
uv run pytest                                      # alle Tests (inkl. slow, integration)
uv run pytest --cov                                # mit Coverage (Schwelle 80 % in pyproject.toml)
uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
uv run python bench/bench_qrcode.py --n 300        # Benchmark (seit I2)
```

---

## Konfiguration

Bibliothek: keine Konfiguration (Parameter per API). `qrvideo`: nur CLI-Argumente und Umgebungsvariablen, keine
Konfigurationsdatei — vollständige Tabelle in `architecture/CONFIGURATION.md`; Secrets siehe
`operations/SECRETS_MANAGEMENT.md`.

| Parameter | Beschreibung | Beispiel |
|-----------|-------------|---------|
| `UV_PROJECT_ENVIRONMENT` | Ort der venv außerhalb des Projektordners | `%LOCALAPPDATA%\venvs\revival_2026` |
