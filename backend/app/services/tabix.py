"""Minimal remote tabix reader (pure Python, no pysam).

Reads a region from a bgzip-compressed, tabix-indexed VCF served over HTTP(S)
using byte-range requests, so GeneLens can fetch one gene's records from the
1000 Genomes phase 3 VCFs (tens of GB in total) while downloading only the
~130 kB index plus a few compressed blocks.

Format references: SAMtools tabix specification (TBI) and the BGZF section
of the SAM specification. Implemented features: bins + linear index,
chunk merging, BGZF multi-member decompression.
"""
from __future__ import annotations

import gzip
import struct
import zlib


def reg2bins(beg: int, end: int) -> list[int]:
    """UCSC binning scheme used by tabix (0-based, half-open [beg, end))."""
    end -= 1
    bins = [0]
    for shift, offset in ((26, 1), (23, 9), (20, 73), (17, 585), (14, 4681)):
        bins.extend(range(offset + (beg >> shift), offset + (end >> shift) + 1))
    return bins


class TabixIndex:
    def __init__(self, raw_gz: bytes):
        data = gzip.decompress(raw_gz)
        if data[:4] != b"TBI\x01":
            raise ValueError("not a tabix index")
        n_ref, fmt, col_seq, col_beg, col_end, meta, skip, l_nm = struct.unpack_from("<8i", data, 4)
        names = data[36:36 + l_nm].split(b"\x00")
        self.names = [n.decode() for n in names if n]
        pos = 36 + l_nm
        self.refs: list[tuple[dict[int, list[tuple[int, int]]], list[int]]] = []
        for _ in range(n_ref):
            (n_bin,) = struct.unpack_from("<i", data, pos)
            pos += 4
            bins: dict[int, list[tuple[int, int]]] = {}
            for _ in range(n_bin):
                b, n_chunk = struct.unpack_from("<Ii", data, pos)
                pos += 8
                chunks = list(struct.iter_unpack("<QQ", data[pos:pos + 16 * n_chunk]))
                pos += 16 * n_chunk
                bins[b] = chunks
            (n_intv,) = struct.unpack_from("<i", data, pos)
            pos += 4
            ioff = [x[0] for x in struct.iter_unpack("<Q", data[pos:pos + 8 * n_intv])]
            pos += 8 * n_intv
            self.refs.append((bins, ioff))

    def start_offset(self, chrom: str, beg: int) -> int | None:
        """Virtual offset from the linear index at or before 0-based position ``beg``.

        Records are sorted by position, so every record with POS ≥ beg lies at
        or after this offset; reading sequentially from here until POS > end
        retrieves the region with one or two range requests.
        """
        if chrom not in self.names:
            return None
        _, ioff = self.refs[self.names.index(chrom)]
        w = min(beg >> 14, len(ioff) - 1)
        while w > 0 and ioff[w] == 0:
            w -= 1
        return ioff[w] if ioff else 0

    def chunks(self, chrom: str, beg: int, end: int) -> list[tuple[int, int]]:
        """Virtual-offset chunks that may contain records overlapping [beg, end) (0-based)."""
        if chrom not in self.names:
            return []
        bins, ioff = self.refs[self.names.index(chrom)]
        min_off = ioff[min(beg >> 14, len(ioff) - 1)] if ioff else 0
        out = sorted(c for b in reg2bins(beg, end) for c in bins.get(b, []) if c[1] > min_off)
        merged: list[list[int]] = []
        for s, e in out:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        return [(s, e) for s, e in merged]


def bgzf_decompress(raw: bytes) -> bytes:
    """Decompress concatenated BGZF/gzip members (a trailing partial member is ignored)."""
    return bgzf_decompress_counted(raw)[0]


def bgzf_decompress_counted(raw: bytes) -> tuple[bytes, int]:
    """Decompress only *complete* BGZF members; return (data, compressed bytes consumed).

    A trailing partial member (cut by the byte range) contributes nothing, so
    the caller can resume exactly at ``offset + consumed`` without duplicates.
    """
    out = bytearray()
    consumed = 0
    while consumed < len(raw):
        d = zlib.decompressobj(31)
        try:
            chunk = d.decompress(raw[consumed:])
        except zlib.error:
            break
        if not d.eof:  # incomplete trailing block
            break
        out += chunk
        consumed = len(raw) - len(d.unused_data)
    return bytes(out), consumed
