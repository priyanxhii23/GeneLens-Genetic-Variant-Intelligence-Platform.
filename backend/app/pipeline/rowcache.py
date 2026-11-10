"""Fast, cached loading of variant rows.

* Uses SQLAlchemy Core (``select(table)`` → mappings) instead of ORM objects,
  which avoids per-row object construction for 10–20k-row genes.
* Keeps the most recently used row sets in memory. **Every write path calls
  ``invalidate()``** (analysis completion, synthetic generation, custom dataset
  processing, deletion), so cached rows can never be stale.
* Callers receive fresh dict copies, so mutating a row cannot corrupt the cache.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Variant

MAX_ENTRIES = 12
_lock = threading.Lock()
_cache: "OrderedDict[tuple, list[dict]]" = OrderedDict()
_stats = {"hits": 0, "misses": 0}
T = Variant.__table__


def _query(db: Session, *conditions) -> list[dict]:
    out = []
    for m in db.execute(select(T).where(*conditions)).mappings():
        d = dict(m)
        d["vcf_key"] = d["variant_key"]
        out.append(d)
    return out


def rows(db: Session, key: tuple, *conditions) -> list[dict]:
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            _stats["hits"] += 1
            return [dict(r) for r in hit]
    data = _query(db, *conditions)
    with _lock:
        _stats["misses"] += 1
        _cache[key] = data
        while len(_cache) > MAX_ENTRIES:
            _cache.popitem(last=False)
    return [dict(r) for r in data]


def invalidate():
    with _lock:
        _cache.clear()


def stats() -> dict:
    with _lock:
        return {**_stats, "entries": len(_cache)}
