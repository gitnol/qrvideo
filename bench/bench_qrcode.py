"""Benchmark: ms pro QR-Code (2100 Zeichen, Version 40, ECC LOW, Maske 1) fuer alle Varianten.

Aufruf:  uv run python bench/bench_qrcode.py [--n 300] [--json bench/results.json]
Die Variante "ohne Numba" laeuft in einem eigenen Prozess (QRCODEGENMOD_DISABLE_JIT=1).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import string
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ALPHABET = string.ascii_letters + string.digits + "+/="


def make_texts(n: int) -> list[str]:
    rnd = random.Random(1)
    return ["".join(rnd.choice(ALPHABET) for _ in range(2100)) for _ in range(n)]


def measure(fn: Callable[[str], object], texts: list[str], repeats: int = 3) -> float:
    fn(texts[0])  # Aufwaermen (JIT, Caches)
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        for t in texts:
            fn(t)
        best = min(best, (time.perf_counter() - start) / len(texts) * 1000)
    return best


def bench_new(texts: list[str]) -> float:
    import qrcodegenmod as q

    return measure(lambda t: q.QrCode.encode_text(t, q.Ecc.LOW, **q.THESIS_PARAMS).to_image(2, 2), texts)


def bench_legacy(texts: list[str]) -> float:
    os.chdir(ROOT / "legacy")  # Thesis-Stand laedt seine .npy relativ zum Arbeitsverzeichnis
    sys.path.insert(0, str(ROOT / "legacy"))
    import qrcodegenmod as legacy  # noqa: PLC0415

    def run(t: str) -> np.ndarray:
        arr = legacy.QrCode.encode_text(t, legacy.QrCode.Ecc.LOW).get_module_as_numpy(2)
        return (~np.repeat(np.repeat(arr, 2, axis=0), 2, axis=1)).astype(np.uint8) * 255

    return measure(run, texts)


def bench_upstream(texts: list[str]) -> float:
    import qrcodegen as ref

    def run(t: str) -> object:
        segs = ref.QrSegment.make_segments(t)
        return ref.QrCode.encode_segments(segs, ref.QrCode.Ecc.LOW, 40, 40, 1)

    return measure(run, texts, repeats=1)


VARIANTS = {"upstream": bench_upstream, "legacy": bench_legacy, "new": bench_new}


def run_variant(name: str, n: int, extra_env: dict[str, str] | None = None) -> float:
    env = {**os.environ, **(extra_env or {})}
    out = subprocess.run(
        [sys.executable, __file__, "--variant", name, "--n", str(n)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return float(out.stdout.strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--floor-ms", type=float, help="Ratchet: Exit 1, wenn 'mit Numba' langsamer ist")
    args = parser.parse_args()

    if args.variant:  # Kindprozess: genau eine Variante messen
        print(VARIANTS[args.variant](make_texts(args.n if args.variant != "upstream" else 20)))
        return

    results = {
        "Original upstream (qrcodegen 1.8.0)": run_variant("upstream", args.n),
        "Thesis qrcodegenmod 2019": run_variant("legacy", args.n),
        "qrcodegenmod 2026 ohne Numba": run_variant("new", args.n, {"QRCODEGENMOD_DISABLE_JIT": "1"}),
        "qrcodegenmod 2026 mit Numba": run_variant("new", args.n),
    }
    base = next(iter(results.values()))
    for label, ms in results.items():
        print(f"{label:40s} {ms:8.3f} ms/QR   {base / ms:6.1f}x")
    if args.json:
        meta = {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "cpu": platform.processor(),
            "n": args.n,
            "date": time.strftime("%Y-%m-%d %H:%M"),
        }
        args.json.write_text(json.dumps({"meta": meta, "ms_per_qr": results}, indent=2), encoding="utf-8")
    measured = results["qrcodegenmod 2026 mit Numba"]
    if args.floor_ms is not None and measured > args.floor_ms:
        sys.exit(f"Ratchet verletzt: {measured:.3f} ms/QR > Floor {args.floor_ms} ms/QR")


if __name__ == "__main__":
    main()
