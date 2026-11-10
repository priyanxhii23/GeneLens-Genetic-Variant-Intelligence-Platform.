"""Small shared helpers."""
from __future__ import annotations

import math

import numpy as np


def json_safe(obj):
    """Recursively replace NaN/±inf with None and numpy scalars with Python types (strict JSON)."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def user_message(exc: Exception, log=None) -> str:
    """Plain-language message for the UI; technical details go to the server log only.

    Messages GeneLens raises on purpose (ValueError/assembly mismatch) are already
    written for users. External-service failures name the service, never the
    raw payload. Anything else gets a reference ID that matches the log entry.
    """
    import uuid

    from app.services.http import ExternalServiceError

    if isinstance(exc, ExternalServiceError):
        if exc.status_code == 404:
            return f"{exc.service} has no record for this request – check the gene symbol."
        if exc.status_code == 429:
            return (f"{exc.service} is rate-limiting requests right now. Please try again in a minute "
                    "(an NCBI API key in backend/.env raises the limit).")
        return (f"{exc.service} could not be reached or returned an error. Please retry later – the Source "
                "Manager shows current availability.")
    if isinstance(exc, ValueError):
        return str(exc)[:400]
    ref = uuid.uuid4().hex[:8]
    if log is not None:
        log.error("internal error ref=%s: %r", ref, exc)
    return f"An unexpected error occurred while processing. Details were written to the backend log (reference {ref})."
