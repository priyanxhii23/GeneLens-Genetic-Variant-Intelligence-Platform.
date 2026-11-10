"""Shared HTTP helper with retries, exponential back-off and clear errors."""
from __future__ import annotations

import contextvars
import logging
import threading
import time

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class ExternalServiceError(RuntimeError):
    """Raised when an external data source cannot be reached or returns an error."""

    def __init__(self, service: str, message: str, status_code: int | None = None):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.status_code = status_code


RETRYABLE = {429, 500, 502, 503, 504}


_client: httpx.Client | None = None
_client_lock = threading.Lock()


def shared_client() -> httpx.Client:
    """One keep-alive HTTP client for the whole process (thread-safe, connection pooling).

    Re-using connections avoids a new TCP + TLS handshake per request, which
    dominated batched retrievals such as ClinVar esummary pages.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                s = get_settings()
                _client = httpx.Client(timeout=s.http_timeout_seconds, follow_redirects=True,
                                       limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
                                       headers={"User-Agent": "GeneLens/1.0 (research software)"})
    return _client


# Set by status probes: a health check must answer quickly, so no retries and a short timeout.
PROBE_MODE: contextvars.ContextVar[bool] = contextvars.ContextVar("PROBE_MODE", default=False)
PROBE_TIMEOUT_S = 10.0


def request_with_retry(method: str, url: str, service: str, retries: int | None = None, **kwargs) -> httpx.Response:
    settings = get_settings()
    delay = 1.0
    last_exc: Exception | None = None
    attempts = settings.http_max_retries if retries is None else retries
    if PROBE_MODE.get():
        attempts = 0
        kwargs.setdefault("timeout", PROBE_TIMEOUT_S)
    for attempt in range(attempts + 1):
        try:
            resp = shared_client().request(method, url, **kwargs)
            if resp.status_code in RETRYABLE:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                log.warning("%s returned %s (attempt %d); retrying in %.1fs", service, resp.status_code, attempt + 1, wait)
                last_exc = ExternalServiceError(service, f"HTTP {resp.status_code}", resp.status_code)
                if attempt < attempts:
                    time.sleep(wait)
                    delay *= 2
                continue
            if resp.status_code >= 400:
                raise ExternalServiceError(service, f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code)
            return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            log.warning("%s transport error (attempt %d): %s", service, attempt + 1, exc)
            last_exc = exc
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    raise ExternalServiceError(service, f"unavailable after retries ({last_exc})")
