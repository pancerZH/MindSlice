"""A minimal Parquet reader (standard library only), enough for MemoryAgentBench's files.

MemoryAgentBench ships only Parquet, and this harness, like the engine, uses the standard library alone.
Supported: the Thrift compact protocol (footer and page headers), UNCOMPRESSED and SNAPPY pages, data
pages v1 and v2, dictionary pages, PLAIN and RLE_DICTIONARY byte arrays, and nested lists (Dremel
repetition and definition levels). Columns are read one at a time; structs are flattened into dotted
column paths (``metadata.source``). Anything else raises ``ParquetError`` rather than guessing.

``sources.py`` records the SHA-256 of the decoded rows of each file (computed once with pyarrow), and
``check`` compares this reader's output against it.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

MAGIC = b"PAR1"
CODEC_UNCOMPRESSED, CODEC_SNAPPY = 0, 1
PAGE_DATA, PAGE_DICTIONARY, PAGE_DATA_V2 = 0, 2, 3
ENC_PLAIN, ENC_PLAIN_DICTIONARY, ENC_RLE, ENC_RLE_DICTIONARY = 0, 2, 3, 8
TYPE_BOOLEAN, TYPE_INT32, TYPE_INT64, TYPE_BYTE_ARRAY = 0, 1, 2, 6
REQUIRED, OPTIONAL, REPEATED = 0, 1, 2


class ParquetError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Thrift compact protocol (just the reading side)
# ---------------------------------------------------------------------------


class _Thrift:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def varint(self) -> int:
        shift = result = 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7

    def zigzag(self) -> int:
        n = self.varint()
        return (n >> 1) ^ -(n & 1)

    def binary(self) -> bytes:
        n = self.varint()
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def value(self, kind: int) -> Any:
        if kind == 1:
            return True
        if kind == 2:
            return False
        if kind == 3:
            b = self.byte()
            return b - 256 if b > 127 else b
        if kind in (4, 5, 6):
            return self.zigzag()
        if kind == 7:
            out = struct.unpack_from("<d", self.data, self.pos)[0]
            self.pos += 8
            return out
        if kind == 8:
            return self.binary()
        if kind in (9, 10):
            header = self.byte()
            size, elem = header >> 4, header & 0x0F
            if size == 15:
                size = self.varint()
            if elem in (1, 2):  # booleans inside a list are one byte each
                return [self.byte() == 1 for _ in range(size)]
            return [self.value(elem) for _ in range(size)]
        if kind == 11:
            size = self.varint()
            if not size:
                return {}
            types = self.byte()
            return {self.value(types >> 4): self.value(types & 0x0F) for _ in range(size)}
        if kind == 12:
            return self.struct()
        raise ParquetError(f"unknown Thrift compact type {kind}")

    def struct(self) -> dict[int, Any]:
        out: dict[int, Any] = {}
        last = 0
        while True:
            header = self.byte()
            if header == 0:
                return out
            delta, kind = header >> 4, header & 0x0F
            field = last + delta if delta else self.zigzag()
            out[field] = self.value(kind)
            last = field


# ---------------------------------------------------------------------------
# Snappy and the RLE / bit-packed hybrid
# ---------------------------------------------------------------------------


def snappy_decompress(data: bytes) -> bytes:
    t = _Thrift(data)
    size = t.varint()
    out = bytearray()
    pos = t.pos
    n = len(data)
    while pos < n:
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:
            length = tag >> 2
            if length >= 60:
                extra = length - 59
                length = int.from_bytes(data[pos : pos + extra], "little")
                pos += extra
            length += 1
            out += data[pos : pos + length]
            pos += length
            continue
        if kind == 1:
            length = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | data[pos]
            pos += 1
        elif kind == 2:
            length = (tag >> 2) + 1
            offset = int.from_bytes(data[pos : pos + 2], "little")
            pos += 2
        else:
            length = (tag >> 2) + 1
            offset = int.from_bytes(data[pos : pos + 4], "little")
            pos += 4
        if offset == 0 or offset > len(out):
            raise ParquetError("corrupt snappy stream")
        start = len(out) - offset
        if offset >= length:
            out += out[start : start + length]
        else:  # overlapping copy: repeat the window byte by byte
            for i in range(length):
                out.append(out[start + i])
    if len(out) != size:
        raise ParquetError(f"snappy length mismatch ({len(out)} != {size})")
    return bytes(out)


def rle_hybrid(data: bytes, pos: int, end: int, bit_width: int, count: int) -> list[int]:
    """Decode ``count`` values of the RLE / bit-packed hybrid encoding from ``data[pos:end]``."""
    out: list[int] = []
    width_bytes = (bit_width + 7) // 8
    mask = (1 << bit_width) - 1
    t = _Thrift(data, pos)
    while len(out) < count and t.pos < end:
        header = t.varint()
        if header & 1:  # bit-packed groups of 8 values, least significant bit first
            groups = header >> 1
            nbytes = groups * bit_width
            chunk = int.from_bytes(data[t.pos : t.pos + nbytes], "little")
            t.pos += nbytes
            for i in range(groups * 8):
                out.append((chunk >> (i * bit_width)) & mask if bit_width else 0)
        else:
            run = header >> 1
            value = int.from_bytes(data[t.pos : t.pos + width_bytes], "little")
            t.pos += width_bytes
            out.extend([value] * run)
    if len(out) < count:
        raise ParquetError("RLE stream ended early")
    return out[:count]


def _plain_byte_arrays(data: bytes, pos: int, count: int) -> list[bytes]:
    out = []
    for _ in range(count):
        (n,) = struct.unpack_from("<I", data, pos)
        pos += 4
        out.append(data[pos : pos + n])
        pos += n
    return out


# ---------------------------------------------------------------------------
# File structure
# ---------------------------------------------------------------------------


class ParquetFile:
    def __init__(self, path: str | Path) -> None:
        self.data = Path(path).read_bytes()
        if self.data[:4] != MAGIC or self.data[-4:] != MAGIC:
            raise ParquetError(f"{path} is not a Parquet file")
        (meta_len,) = struct.unpack_from("<I", self.data, len(self.data) - 8)
        meta = _Thrift(self.data, len(self.data) - 8 - meta_len).struct()
        self.num_rows = meta[3]
        self._columns = self._schema(meta[2])
        self._chunks: dict[str, list[dict[int, Any]]] = {}
        for group in meta[4]:
            for chunk in group[1]:
                cm = chunk[3]
                name = ".".join(p.decode() for p in cm[3])
                self._chunks.setdefault(name, []).append(cm)

    @staticmethod
    def _schema(elements: list[dict[int, Any]]) -> dict[str, list[int]]:
        """Leaf column path -> repetition type of every node below the root."""
        leaves: dict[str, list[int]] = {}
        pos = 1  # element 0 is the root

        def walk(prefix: list[str], reps: list[int]) -> None:
            nonlocal pos
            el = elements[pos]
            pos += 1
            name, rep = el[4].decode(), el.get(3, REQUIRED)
            path, chain = prefix + [name], reps + [rep]
            children = el.get(5, 0)
            if not children:
                leaves[".".join(path)] = chain  # only byte-array leaves can be decoded (see _triples)
            for _ in range(children):
                walk(path, chain)

        for _ in range(elements[0].get(5, 0)):
            walk([], [])
        return leaves

    def columns(self) -> list[str]:
        """Logical column names: leaf paths without the LIST wrappers (``questions``, ``metadata.source``)."""
        return [self._logical(c) for c in self._columns]

    @staticmethod
    def _logical(leaf: str) -> str:
        return leaf.replace(".list.element", "")

    def _leaf(self, name: str) -> str:
        if name in self._columns:
            return name
        matches = [c for c in self._columns if self._logical(c) == name]
        if len(matches) != 1:
            raise ParquetError(f"no column {name!r} (have: {', '.join(self.columns())})")
        return matches[0]

    # -- one column ---------------------------------------------------------
    def _levels(self, name: str) -> tuple[int, int, list[int], list[int]]:
        reps = self._columns[name]
        max_def = max_rep = 0
        list_def, elem_def = [0], [0]  # index r = 1..max_rep
        for rep in reps:
            before = max_def
            if rep != REQUIRED:
                max_def += 1
            if rep == REPEATED:
                max_rep += 1
                list_def.append(before)
                elem_def.append(max_def)
        return max_def, max_rep, list_def, elem_def

    def _triples(self, name: str, max_def: int, max_rep: int) -> list[tuple[int, int, Any]]:
        out: list[tuple[int, int, Any]] = []
        for cm in self._chunks[name]:
            if cm[1] != TYPE_BYTE_ARRAY:
                raise ParquetError(f"column {name}: only byte-array columns are supported")
            codec = cm[4]
            if codec not in (CODEC_UNCOMPRESSED, CODEC_SNAPPY):
                raise ParquetError(f"column {name}: unsupported codec {codec}")
            pos = cm.get(11) or cm[9]
            end = pos + cm[7]
            dictionary: list[bytes] | None = None
            remaining = cm[5]
            while remaining > 0 and pos < end:
                t = _Thrift(self.data, pos)
                header = t.struct()
                body = self.data[t.pos : t.pos + header[3]]
                pos = t.pos + header[3]
                kind = header[1]
                if kind == PAGE_DICTIONARY:
                    raw = snappy_decompress(body) if codec == CODEC_SNAPPY else body
                    dictionary = _plain_byte_arrays(raw, 0, header[7][1])
                    continue
                if kind == PAGE_DATA:
                    h = header[5]
                    n, encoding = h[1], h[2]
                    raw = snappy_decompress(body) if codec == CODEC_SNAPPY else body
                    p = 0
                    reps_l = defs_l = None
                    if max_rep:
                        (ln,) = struct.unpack_from("<I", raw, p)
                        reps_l = rle_hybrid(raw, p + 4, p + 4 + ln, max_rep.bit_length(), n)
                        p += 4 + ln
                    if max_def:
                        (ln,) = struct.unpack_from("<I", raw, p)
                        defs_l = rle_hybrid(raw, p + 4, p + 4 + ln, max_def.bit_length(), n)
                        p += 4 + ln
                    values_raw, vpos = raw, p
                elif kind == PAGE_DATA_V2:
                    h = header[8]
                    n, encoding = h[1], h[4]
                    dlen, rlen = h[5], h[6]
                    reps_l = rle_hybrid(body, 0, rlen, max_rep.bit_length(), n) if max_rep else None
                    defs_l = rle_hybrid(body, rlen, rlen + dlen, max_def.bit_length(), n) if max_def else None
                    rest = body[rlen + dlen :]
                    compressed = h.get(7, True)
                    values_raw = snappy_decompress(rest) if codec == CODEC_SNAPPY and compressed else rest
                    vpos = 0
                else:
                    continue  # index pages carry no values
                defs_l = defs_l or [max_def] * n
                reps_l = reps_l or [0] * n
                present = sum(1 for d in defs_l if d == max_def)
                if encoding == ENC_PLAIN:
                    values = _plain_byte_arrays(values_raw, vpos, present)
                elif encoding in (ENC_PLAIN_DICTIONARY, ENC_RLE_DICTIONARY):
                    if dictionary is None:
                        raise ParquetError(f"column {name}: dictionary page missing")
                    width = values_raw[vpos]
                    idx = rle_hybrid(values_raw, vpos + 1, len(values_raw), width, present)
                    values = [dictionary[i] for i in idx]
                else:
                    raise ParquetError(f"column {name}: unsupported encoding {encoding}")
                it = iter(values)
                out.extend((r, d, next(it).decode("utf-8") if d == max_def else None) for r, d in zip(reps_l, defs_l))
                remaining -= n
        return out

    def column(self, name: str) -> list[Any]:
        """Every row's value for one column (logical or leaf name), with lists rebuilt from the levels."""
        name = self._leaf(name)
        max_def, max_rep, list_def, elem_def = self._levels(name)
        rows: list[Any] = []
        stack: list[Any] = [None] * (max_rep + 1)
        for rep, de, val in self._triples(name, max_def, max_rep):
            if rep == 0:
                if max_rep == 0:
                    rows.append(val)
                    continue
                if de < list_def[1]:
                    rows.append(None)
                    continue
                top: list[Any] = []
                rows.append(top)
                stack[1] = top
                depth = 1
            else:
                depth = rep
            while True:
                if de < elem_def[depth]:
                    break  # an empty list
                if depth == max_rep:
                    stack[depth].append(val)
                    break
                if de < list_def[depth + 1]:
                    stack[depth].append(None)
                    break
                inner: list[Any] = []
                stack[depth].append(inner)
                stack[depth + 1] = inner
                depth += 1
        if len(rows) != self.num_rows:
            raise ParquetError(f"column {name}: {len(rows)} rows, expected {self.num_rows}")
        return rows

    def rows(self, names: list[str]) -> list[dict[str, Any]]:
        cols = {n: self.column(n) for n in names}
        return [{n: cols[n][i] for n in names} for i in range(self.num_rows)]
