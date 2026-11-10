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
