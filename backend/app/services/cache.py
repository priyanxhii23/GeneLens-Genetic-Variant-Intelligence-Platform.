"""Tiny gzip-JSON disk cache for external API responses.

Responses are keyed by a SHA-256 of the request so identical queries are
served from disk. Each entry stores the original retrieval timestamp so
provenance survives caching.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.config import get_settings


class DiskCache:
    def __init__(self, namespace: str, ttl_hours: float | None = None, root: Path | None = None):
        settings = get_settings()
        self.dir = (root or settings.cache_dir) / namespace
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = (ttl_hours if ttl_hours is not None else settings.cache_ttl_hours) * 3600

    @staticmethod
    def key(*parts: Any) -> str:
        raw = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json.gz"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                entry = json.load(fh)
        except (OSError, json.JSONDecodeError):
            p.unlink(missing_ok=True)
            return None
        if time.time() - entry.get("stored_at", 0) > self.ttl_seconds:
            return None
        return entry

    def set(self, key: str, payload: Any, meta: dict | None = None) -> dict:
        entry = {"stored_at": time.time(), "meta": meta or {}, "payload": payload}
        tmp = self._path(key).with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(entry, fh)
        tmp.replace(self._path(key))
        return entry
