"""
Shared caching helpers for benchmark fetchers.

Raw responses (HTML text or JSON strings) are stored under:
    ~/projects/costa-os/ai-router/benchmarks/raw/<source_name>/

Files are named with ISO-8601 timestamps so the most recent file can be
identified by sorting.  A cached file is considered fresh if it is less than
MAX_AGE_HOURS old (default 12).
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CACHE_ROOT = Path.home() / "projects" / "costa-os" / "ai-router" / "benchmarks" / "raw"
MAX_AGE_HOURS = 12


def _source_dir(source_name: str) -> Path:
    d = CACHE_ROOT / source_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cache(source_name: str) -> str | None:
    """
    Return the most recently cached raw content for *source_name*, or None if
    the cache is empty / stale (older than MAX_AGE_HOURS).
    """
    d = _source_dir(source_name)
    candidates = sorted(d.glob("*.txt")) + sorted(d.glob("*.json")) + sorted(d.glob("*.html"))
    if not candidates:
        return None

    latest = sorted(candidates)[-1]
    # Filename stem is an ISO-8601 timestamp like 2024-01-15T12:30:00
    try:
        ts = datetime.fromisoformat(latest.stem.replace("_", ":"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        if age > timedelta(hours=MAX_AGE_HOURS):
            return None
    except ValueError:
        # Unknown filename format — treat as stale
        return None

    print(f"[cache] Using cached data for '{source_name}' ({latest.name})", file=sys.stderr)
    return latest.read_text(encoding="utf-8", errors="replace")


def save_cache(source_name: str, content: str, ext: str = "html") -> Path:
    """
    Persist *content* to the cache directory for *source_name*.
    Returns the path of the written file.
    """
    d = _source_dir(source_name)
    # Colons are not valid in Windows filenames; replace with underscores for
    # portability even though we're on Linux.
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H_%M_%S")
    path = d / f"{ts}.{ext}"
    path.write_text(content, encoding="utf-8")
    return path
