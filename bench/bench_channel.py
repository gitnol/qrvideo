"""Kanalmessung: Bytefehler je Reed-Solomon-Block nach H.264, ECC L gegen M, volle und fast leere Frames.

Die Referenz ist das unkomprimierte Original: Plan und QR-Codes sind deterministisch, also wird jeder Slot
neu gerendert und Codewort fuer Codewort mit dem abgetasteten Video verglichen. Gezaehlt wird damit auch dort,
wo der Reader scheitert (dort kennt `DecodeReport.corrected_bytes` keine Zahl). Ausfall = ein Block hat mehr
Bytefehler, als er korrigieren kann (ECC-Bytes je Block / 2).

Aufrufe:
  uv run python bench/bench_channel.py            # Raster ECC L/M x crf, danach YouTube-Nachbildung
  uv run python bench/bench_channel.py --video v.mp4 --payload p.bin --ecc M   # vorhandenes Video auswerten
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import numpy.typing as npt

import qrcodegenmod as q
from qrcodegenmod import _tables
from qrcodegenmod._layout import mask_pattern, version_layout
from qrcodegenmod.reader import _block_indices
from qrvideo.container import CHUNK_BYTES, DATA_SLOTS, header_payload, plan_frames, plan_frames_v3
from qrvideo.encoder import TAIL_FRAMES, iter_frames
from qrvideo.layout import THESIS_LAYOUT
from qrvideo.videoio import VideoSettings, read_video, write_video

ECC = {"L": q.Ecc.LOW, "M": q.Ecc.MEDIUM}
_V40 = {"minversion": 40, "maxversion": 40, "boostecl": False}


def codewords(modules: npt.NDArray[np.bool_], mask: int = 1) -> npt.NDArray[np.uint8]:
    """Verschraenkter Codewortstrom eines V40-QR (wie im Reader, ohne Korrektur)."""
    positions = version_layout(40).data_positions
    raw = _tables.num_raw_data_modules(40) // 8
    positions = positions[: raw * 8]
    bits = modules.reshape(-1)[positions] ^ mask_pattern(177, mask).reshape(-1)[positions]
    return np.packbits(bits)


@dataclass
class Stats:
    qr: int = 0
    failed: int = 0
    byte_errors: list[int] = field(default_factory=list)  # je QR, Summe ueber Bloecke
    block_max: list[int] = field(default_factory=list)  # je QR, schlechtester Block
    capacity: int = 0  # korrigierbare Bytes je Block

    def add(self, errors: list[int], capacity: int) -> None:
        self.qr += 1
        self.capacity = capacity
        self.byte_errors.append(sum(errors))
        self.block_max.append(max(errors))
        self.failed += max(errors) > capacity

    def row(self) -> str:
        if not self.qr:
            return "-"
        mean = np.mean(self.byte_errors)
        worst = max(self.block_max)
        return (
            f"{self.qr:4d} QR  Bytefehler/QR mittel {mean:6.1f} max {max(self.byte_errors):4d}  "
            f"schlechtester Block {worst:3d}/{self.capacity} ({worst / self.capacity:4.0%})  "
            f"Ausfaelle {self.failed}"
        )


def reference(
    payload: bytes, ecl: q.Ecc, parity: int | None = None
) -> list[list[tuple[npt.NDArray[np.uint8], q.Ecc]]]:
    """Je Frame und belegtem Slot: Referenz-Codewoerter und ECC-Stufe (Slot 0 = Kopf, immer M).

    `parity` None = Format v2, sonst v3 mit m Paritaetssymbolen je Gruppe und Nachlauf wie im Encoder.
    """
    if parity is None:
        plans = plan_frames(payload, ecl, DATA_SLOTS)
    else:
        plans = plan_frames_v3(payload, ecl, DATA_SLOTS, parity)
        plans += plans[-TAIL_FRAMES:]
    frames = []
    for plan in plans:
        items = [(header_payload(plan.header), q.Ecc.MEDIUM), *((c, ecl) for c in plan.chunks)]
        frames.append(
            [(codewords(q.QrCode.encode_binary(d, e, mask=1, **_V40).modules), e) for d, e in items]
        )
    return frames


def measure(video: Path, payload: bytes, ecl: q.Ecc, parity: int | None = None) -> dict[str, Stats]:
    """Statistik getrennt nach Kopf-QR, Daten-QR voller Frames und Daten-QR des letzten (duennen) Frames."""
    ref = reference(payload, ecl, parity)
    out = {"Kopf": Stats(), "Daten voll": Stats(), "Daten duenn": Stats()}
    for index, frame in enumerate(read_video(video)):
        modules, _ = THESIS_LAYOUT.sample(frame)
        sparse = len(ref[index]) <= DATA_SLOTS // 2
        for slot, (expected, e) in enumerate(ref[index]):
            got = codewords(modules[slot])
            blocks, eccl = _block_indices(40, e.ordinal)
            errors = [int(np.count_nonzero(got[idx] != expected[idx])) for idx in blocks]
            key = "Kopf" if slot == 0 else ("Daten duenn" if sparse else "Daten voll")
            out[key].add(errors, eccl // 2)
    return out


def sparse_payload(ecl: q.Ecc, full_frames: int, last_chunks: int, seed: int) -> bytes:
    """Zufallsnutzlast: `full_frames` volle Frames, dann ein Frame mit `last_chunks` Daten-QR."""
    size = (full_frames * DATA_SLOTS + last_chunks) * CHUNK_BYTES[ecl] - 100
    return random.Random(seed).randbytes(size)


def transcode(source: Path, target: Path, bitrate: str) -> None:
    """YouTube-Nachbildung: zweite H.264-Kodierung mit begrenzter Bitrate."""
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(source), "-c:v", "libx264"]
    cmd += ["-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bitrate, "-preset", "medium", str(target)]
    subprocess.run(cmd, check=True)


def report(label: str, stats: dict[str, Stats]) -> None:
    print(label)
    for key, value in stats.items():
        print(f"  {key:12s} {value.row()}")
    sys.stdout.flush()


def grid(crfs: list[int], bitrates: list[str], full_frames: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for name, ecl in ECC.items():
            payload = sparse_payload(ecl, full_frames, 1, seed=17)
            for crf in crfs:
                video = Path(tmp) / f"{name}_{crf}.mp4"
                write_video(video, iter_frames(payload, ecl, workers=4), VideoSettings(crf=crf))
                report(f"ECC {name}, crf {crf}", measure(video, payload, ecl))
            source = Path(tmp) / f"{name}_{crfs[0]}.mp4"
            for rate in bitrates:
                again = Path(tmp) / f"{name}_{rate}.mp4"
                transcode(source, again, rate)
                report(
                    f"ECC {name}, crf {crfs[0]} + zweite Kodierung {rate}bit/s", measure(again, payload, ecl)
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--video", type=Path, help="vorhandenes Video auswerten")
    parser.add_argument("--parity", type=int, help="Video im Format v3 mit m Paritaetssymbolen je Gruppe")
    parser.add_argument("--payload", type=Path, help="Originalnutzlast zum Video")
    parser.add_argument("--ecc", choices=ECC, default="M")
    parser.add_argument("--crf", type=int, nargs="+", default=[12, 23, 30, 35])
    parser.add_argument("--bitrate", nargs="+", default=["80M", "40M", "20M", "10M"])
    parser.add_argument("--frames", type=int, default=10, help="volle Frames vor dem duennen letzten Frame")
    args = parser.parse_args()
    if args.video:
        if not args.payload:
            parser.error("--video braucht --payload")
        report(str(args.video), measure(args.video, args.payload.read_bytes(), ECC[args.ecc], args.parity))
        return 0
    grid(args.crf, args.bitrate, args.frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())
