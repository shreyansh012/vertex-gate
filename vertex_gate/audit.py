"""Append-only audit log. One JSON object per line."""

import json
import math
import os


def _clean(value):
    """Make a value safe for strict JSON. NaN and infinity become text."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def write(path, record):
    """Append one record and flush it to disk. Raises OSError on failure."""
    line = json.dumps(_clean(record), sort_keys=True, allow_nan=False)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
