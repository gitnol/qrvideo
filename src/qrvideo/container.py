"""Containerformat v2: Nutzdaten binaer in QR-Codes, pro Frame ein Kopf-QR in Slot 0.

Thesis (v1): ASCII-armored Text in Chunks a 2100 Zeichen; Slot 0 enthielt einen pro Frame per
GnuPG verschluesselten Status. v2: Rohbytes (bei ECC MEDIUM 2331 Bytes je QR, +48 % Nutzlast)
und ein kleiner Klartext-Kopf. Vertraulichkeit und Echtheit liefert die signierte, verschluesselte
Nutzlast selbst; der Kopf enthaelt nur Zaehler, Laenge und SHA-256 der Nutzlast.

v3 (ADR-003): Jeder Daten-QR traegt vorn seinen globalen Symbolindex und eine CRC32 und ist damit ohne
den Kopf seines Frames einzuordnen; eine stille Fehlkorrektur des inneren Codes wird zur Ausloeschung. Der
Kopf-QR wird mit einem frameabhaengigen Strom aufgefuellt - fast statisch war er auf YouTube das schwaechste
Glied (Messung I17a). Der Kopf nennt die Gruppe des aeusseren Erasure-Codes: k Daten- und m Paritaetssymbole.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass

from qrcodegenmod import Ecc

from .erasure import encode_parity
from .errors import ContainerError as ContainerError  # Name bleibt hier erhalten (vor I26 hier definiert)

MAGIC = b"QRV2"
MAGIC_V3 = b"QRV3"
_HEADER = struct.Struct(">4sIIQHB32s")  # magic, frame, frames, length, chunk, ecc, sha256
_HEADER_V3 = struct.Struct(">4sIIQHBBB32s")  # wie v2, dazu k und m der Gruppe vor dem SHA-256
_SYMBOL = struct.Struct(">II")  # globaler Symbolindex, CRC32 ueber Index und Daten
SYMBOL_PREFIX = _SYMBOL.size

# Groesste Byte-Nutzlast eines V40-QR-Codes je ECC-Stufe (4 Bit Modus + 16 Bit Zaehler abgezogen)
CHUNK_BYTES = {Ecc.LOW: 2953, Ecc.MEDIUM: 2331, Ecc.QUARTILE: 1663, Ecc.HIGH: 1273}
DATA_SLOTS = 14  # Daten-QR je Frame (15 Slots, Slot 0 = Kopf)
MAX_FRAMES = 1_000_000  # ca. 9 h Video bei 30 fps; Schutz vor manipulierten Koepfen (Code-Review #2)
MAX_GROUP = 255  # k + m verschiedene Stuetzstellen der Cauchy-Matrix ueber GF(256)
GROUP_SYMBOLS = 10 * DATA_SLOTS  # Standardgruppe: 10 Frames, ein verlorener Frame trifft genau eine Gruppe


@dataclass(frozen=True)
class FrameHeader:
    frame_index: int
    frame_count: int
    payload_length: int
    chunk_bytes: int
    ecc_ordinal: int
    sha256: bytes
    version: int = 2
    group_data: int = 0  # v3: Datensymbole k je Gruppe
    group_parity: int = 0  # v3: Paritaetssymbole m je Gruppe

    def pack(self) -> bytes:
        fields = (self.frame_index, self.frame_count, self.payload_length, self.chunk_bytes, self.ecc_ordinal)
        if self.version == 3:
            return _HEADER_V3.pack(MAGIC_V3, *fields, self.group_data, self.group_parity, self.sha256)
        return _HEADER.pack(MAGIC, *fields, self.sha256)

    @staticmethod
    def unpack(data: bytes) -> FrameHeader:
        """v2: genau 55 Bytes; v3: Kopf am Anfang des aufgefuellten Kopf-QR."""
        if data.startswith(MAGIC_V3) and len(data) >= _HEADER_V3.size:
            _, idx, count, length, chunk, ecc, k, m, digest = _HEADER_V3.unpack_from(data)
            header = FrameHeader(idx, count, length, chunk, ecc, digest, 3, k, m)
        elif data.startswith(MAGIC) and len(data) == _HEADER.size:
            header = FrameHeader(*_HEADER.unpack(data)[1:])
        else:
            raise ContainerError("Kein v2- oder v3-Kopf")
        header.validate()
        return header

    def validate(self) -> None:
        if self.frame_index >= self.frame_count:
            raise ContainerError(f"Frame-Index {self.frame_index} ausserhalb von {self.frame_count}")
        if self.frame_count > MAX_FRAMES:
            raise ContainerError(f"Frame-Anzahl {self.frame_count} ueber dem Limit {MAX_FRAMES}")
        prefix = SYMBOL_PREFIX if self.version == 3 else 0
        valid = {e.ordinal: size - prefix for e, size in CHUNK_BYTES.items()}
        if valid.get(self.ecc_ordinal) != self.chunk_bytes:
            raise ContainerError(
                f"Chunkgroesse {self.chunk_bytes} passt nicht zur ECC-Stufe {self.ecc_ordinal}"
            )
        k, m = self.group_data, self.group_parity
        if self.version == 3 and not (k >= 1 and k + m <= MAX_GROUP):
            raise ContainerError(f"Gruppe k={k}, m={m} ungueltig (k >= 1, k + m <= {MAX_GROUP})")
        if self.symbol_count() > self.frame_count * DATA_SLOTS:
            raise ContainerError(f"Laenge {self.payload_length} passt nicht in {self.frame_count} Frames")

    def symbol_count(self) -> int:
        """Daten-QR insgesamt: Chunks, in v3 zuzueglich m Paritaetssymbolen je Gruppe."""
        chunks = -(-self.payload_length // self.chunk_bytes)
        if self.version != 3:
            return chunks
        return chunks + -(-chunks // self.group_data) * self.group_parity


@dataclass(frozen=True)
class FramePlan:
    header: FrameHeader
    chunks: tuple[bytes, ...]


def plan_frames(payload: bytes, ecl: Ecc = Ecc.MEDIUM, data_slots: int = DATA_SLOTS) -> list[FramePlan]:
    """Zerlegt die Nutzlast in Frames: je Frame ein Kopf und bis zu `data_slots` Chunks."""
    chunk = CHUNK_BYTES[ecl]
    chunks = [payload[i : i + chunk] for i in range(0, len(payload), chunk)] or [b""]
    count = -(-len(chunks) // data_slots)
    digest = hashlib.sha256(payload).digest()
    return [
        FramePlan(
            FrameHeader(i, count, len(payload), chunk, ecl.ordinal, digest),
            tuple(chunks[i * data_slots : (i + 1) * data_slots]),
        )
        for i in range(count)
    ]


def assemble(header: FrameHeader, chunks: dict[int, bytes]) -> bytes:
    """Setzt Chunks (Index -> Daten) zusammen und prueft Laenge und SHA-256."""
    expected = max(1, -(-header.payload_length // header.chunk_bytes))
    present = sorted(
        k for k in chunks if 0 <= k < expected
    )  # nur echte Chunks, nie bis zur behaupteten Laenge
    if len(present) < expected:
        first = next((i for i, k in enumerate(present) if i != k), len(present))
        raise ContainerError(f"{expected - len(present)} Chunks fehlen, erster fehlender: {first}")
    payload = b"".join(chunks[i] for i in range(expected))
    if len(payload) != header.payload_length:
        raise ContainerError(f"Laenge {len(payload)} statt {header.payload_length}")
    if hashlib.sha256(payload).digest() != header.sha256:
        raise ContainerError("SHA-256 der Nutzlast stimmt nicht")
    return payload


def header_payload(header: FrameHeader) -> bytes:
    """Inhalt des Kopf-QR: v2 die 55 Bytes, v3 aufgefuellt mit einem aus dem Kopf abgeleiteten Strom.

    Der Strom haengt ueber den Frame-Index vom Frame ab; so aendert sich der ganze Kopf-QR von Frame zu Frame
    wie ein Daten-QR, statt bis auf wenige Module stillzustehen.
    """
    packed = header.pack()
    if header.version != 3:
        return packed
    return packed + hashlib.shake_128(packed).digest(CHUNK_BYTES[Ecc.MEDIUM] - len(packed))


def pack_symbol(index: int, data: bytes) -> bytes:
    """v3-Daten-QR: Symbolindex und CRC32 (ueber Index und Daten) vor den Daten."""
    head = index.to_bytes(4, "big")
    return _SYMBOL.pack(index, zlib.crc32(data, zlib.crc32(head))) + data


def unpack_symbol(raw: bytes) -> tuple[int, bytes]:
    if len(raw) < SYMBOL_PREFIX:
        raise ContainerError(f"Daten-QR zu kurz ({len(raw)} Bytes)")
    index, crc = _SYMBOL.unpack_from(raw)
    if zlib.crc32(raw[SYMBOL_PREFIX:], zlib.crc32(raw[:4])) != crc:
        raise ContainerError("CRC32 des Daten-QR stimmt nicht")
    return index, raw[SYMBOL_PREFIX:]


def symbol_index(chunk: int, group_data: int, group_parity: int) -> int:
    """Globaler Symbolindex von Chunk `chunk`: Gruppe fuer Gruppe k Daten-, dann m Paritaetssymbole."""
    group, position = divmod(chunk, group_data)
    return group * (group_data + group_parity) + position


def plan_frames_v3(
    payload: bytes, ecl: Ecc = Ecc.LOW, data_slots: int = DATA_SLOTS, parity: int = 0
) -> list[FramePlan]:
    """Format v3: Gruppen aus k = GROUP_SYMBOLS - m Daten- und m Paritaetssymbolen, fortlaufend in Frames.

    Volle Gruppen fuellen genau 10 Frames, ein verlorener Frame trifft also nur eine Gruppe. Fuer die Paritaet
    wird der kurze letzte Chunk mit Nullen auf Chunkgroesse aufgefuellt; uebertragen wird er ungepolstert.
    """
    if not 0 <= parity < GROUP_SYMBOLS:
        raise ValueError(f"Paritaet {parity} ausserhalb von 0..{GROUP_SYMBOLS - 1} Symbolen je Gruppe")
    chunk = CHUNK_BYTES[ecl] - SYMBOL_PREFIX
    k = GROUP_SYMBOLS - parity
    chunks = [payload[i : i + chunk] for i in range(0, len(payload), chunk)] or [b""]
    symbols: list[bytes] = []
    for start in range(0, len(chunks), k):
        group = chunks[start : start + k]
        base = len(symbols)
        protection = encode_parity([c.ljust(chunk, b"\0") for c in group], parity)
        symbols += [pack_symbol(base + i, s) for i, s in enumerate([*group, *protection])]
    count = -(-len(symbols) // data_slots)
    digest = hashlib.sha256(payload).digest()
    return [
        FramePlan(
            FrameHeader(i, count, len(payload), chunk, ecl.ordinal, digest, 3, k, parity),
            tuple(symbols[i * data_slots : (i + 1) * data_slots]),
        )
        for i in range(count)
    ]


def group_layout(header: FrameHeader) -> list[tuple[int, int, int]]:
    """v3: je Gruppe (erster Chunk, erster Symbolindex, Datensymbole k_g); die Paritaet folgt den Daten."""
    total = max(1, -(-header.payload_length // header.chunk_bytes))
    k, m = header.group_data, header.group_parity
    return [(first, symbol_index(first, k, m), min(k, total - first)) for first in range(0, total, k)]
