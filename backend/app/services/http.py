"""Shared HTTP helper with retries, exponential back-off and clear errors."""
from __future__ import annotations

import logging
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


def request_with_retry(method: str, url: str, service: str, **kwargs) -> httpx.Response:
    settings = get_settings()
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(settings.http_max_retries + 1):
        try:
            with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True) as client:
                resp = client.request(method, url, **kwargs)
            if resp.status_code in RETRYABLE:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                log.warning("%s returned %s (attempt %d); retrying in %.1fs", service, resp.status_code, attempt + 1, wait)
                last_exc = ExternalServiceError(service, f"HTTP {resp.status_code}", resp.status_code)
                time.sleep(wait)
                delay *= 2
                continue
            if resp.status_code >= 400:
                raise ExternalServiceError(service, f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code)
            return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            log.warning("%s transport error (attempt %d): %s", service, attempt + 1, exc)
            last_exc = exc
            time.sleep(delay)
            delay *= 2
    raise ExternalServiceError(service, f"unavailable after retries ({last_exc})")
