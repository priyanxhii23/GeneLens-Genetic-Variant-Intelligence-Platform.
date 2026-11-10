"""Parallel, cached source probes (stale-while-revalidate).

* All seven probes run concurrently (thread pool), each with a short timeout,
  so a full check takes as long as the slowest source instead of the sum.
* Results are cached for ``FRESH_S`` seconds. After that the cached value is
  still returned immediately while a background thread refreshes it, so pages
  never block on network checks once the first result exists.
* The server warms the cache at startup (see ``app.main``).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)
FRESH_S = 300
_lock = threading.Lock()
_state: dict = {"at": 0.0, "probes": None, "gnomad_enum": None, "refreshing": False}
_run_lock = threading.Lock()  # one probe round at a time; concurrent callers wait for it


def fetch_gnomad_enum() -> set[str]:
    """Dataset IDs the live gnomAD API offers (empty set if unreachable)."""
    from app.services.gnomad_client import GnomadClient
    from app.services.http import PROBE_MODE

    token = PROBE_MODE.set(True)
    try:
        data = GnomadClient()._post('{ __type(name:"DatasetId"){ enumValues{ name } } }')
        return {e["name"] for e in data["__type"]["enumValues"]}
    except Exception:  # noqa: BLE001 - unreachable API means "no datasets confirmed"
        return set()
    finally:
        PROBE_MODE.reset(token)


def _run_all(only_if_older_than: float | None = None) -> dict:
    """Run one probe round. Concurrent callers wait for the in-flight round and reuse its result."""
    with _run_lock:
        if only_if_older_than is not None and _state["probes"] is not None and _state["at"] >= only_if_older_than:
            return _state["probes"]  # another thread just finished a round
        return _run_all_locked()


def _run_all_locked() -> dict:
    from app.sources.registry import SOURCES

    with ThreadPoolExecutor(max_workers=len(SOURCES) + 1) as ex:
        futures = {s.id: ex.submit(s.check) for s in SOURCES}
        enum_f = ex.submit(fetch_gnomad_enum)
        probes = {k: f.result() for k, f in futures.items()}
        enum = enum_f.result()
    with _lock:
        _state.update(at=time.time(), probes=probes, gnomad_enum=enum, refreshing=False)
    return probes


def _refresh_in_background():
    with _lock:
        if _state["refreshing"]:
            return
        _state["refreshing"] = True

    def work():
        try:
            _run_all()
        except Exception as exc:  # noqa: BLE001
            log.warning("background source refresh failed: %s", exc)
            with _lock:
                _state["refreshing"] = False

    threading.Thread(target=work, daemon=True, name="source-probe-refresh").start()


def get_probes(force: bool = False) -> tuple[dict, set]:
    """Return (probe results by source id, gnomAD dataset enum)."""
    if force:
        _run_all()
    elif _state["probes"] is None:
        _run_all(only_if_older_than=time.time() - FRESH_S)  # waits for a warm-up already in progress
    elif time.time() - _state["at"] > FRESH_S:
        _refresh_in_background()
    return _state["probes"], _state["gnomad_enum"] or set()


def update_one(source_id: str, probe: dict):
    with _lock:
        if _state["probes"] is not None:
            _state["probes"][source_id] = probe


def warm_up():
    threading.Thread(target=lambda: get_probes(force=True), daemon=True, name="source-probe-warmup").start()
