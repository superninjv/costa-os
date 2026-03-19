#!/usr/bin/env python3
"""CLI-Anything registry — maps running apps to deterministic CLI wrappers.

When a CLI-Anything wrapper exists for an app, costa-nav can skip
AT-SPI + Ollama interpretation and call the CLI directly (~50ms, 0 tokens).

Registry lives at ~/.config/costa/cli-registry.json.
Default shipped from configs/costa/cli-registry.json.
"""

import json
import shutil
import subprocess
from pathlib import Path

COSTA_DIR = Path.home() / ".config" / "costa"
REGISTRY_PATH = COSTA_DIR / "cli-registry.json"
DEFAULT_REGISTRY = Path(__file__).parent.parent / "configs" / "costa" / "cli-registry.json"

_cache: dict | None = None


def load_registry() -> dict:
    """Load and cache the CLI registry. Returns {window_class: entry}."""
    global _cache
    if _cache is not None:
        return _cache

    path = REGISTRY_PATH if REGISTRY_PATH.exists() else DEFAULT_REGISTRY
    if not path.exists():
        _cache = {}
        return _cache

    try:
        entries = json.loads(path.read_text())
        _cache = {e["window_class"]: e for e in entries if isinstance(e, dict)}
    except (json.JSONDecodeError, KeyError):
        _cache = {}

    return _cache


def lookup(window_class: str) -> dict | None:
    """Look up a CLI wrapper for an app. Returns entry dict or None."""
    registry = load_registry()
    wc = window_class.lower()
    # Exact match first
    if wc in registry:
        entry = registry[wc]
        if entry.get("installed") and is_cli_available(entry.get("entry_point", "")):
            return entry
    # Partial match
    for key, entry in registry.items():
        if key in wc or wc in key:
            if entry.get("installed") and is_cli_available(entry.get("entry_point", "")):
                return entry
    return None


def is_cli_available(entry_point: str) -> bool:
    """Check if a CLI wrapper binary is on PATH."""
    if not entry_point:
        return False
    return shutil.which(entry_point) is not None


def match_query_to_command(entry: dict, query: str) -> str | None:
    """Match a natural-language query to a CLI subcommand via the query_map.

    Returns the CLI command string or None if no match.
    """
    query_map = entry.get("query_map", {})
    if not query_map:
        return None

    query_lower = query.lower()

    # Score each capability by keyword overlap
    best_cmd = None
    best_score = 0

    for capability, cmd in query_map.items():
        if cmd is None:  # explicitly unsupported
            continue
        # Split capability into keywords
        keywords = capability.lower().replace("_", " ").replace("-", " ").split()
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > best_score:
            best_score = score
            best_cmd = cmd

    return best_cmd if best_score > 0 else None


def run_cli(entry: dict, command: str, timeout: int = 10) -> dict | None:
    """Run a CLI-Anything command and parse JSON output.

    Returns parsed JSON dict, or None on failure.
    """
    entry_point = entry.get("entry_point", "")
    if not entry_point:
        return None

    parts = command.split()
    try:
        r = subprocess.run(
            [entry_point] + parts,
            capture_output=True, text=True, timeout=timeout
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def refresh_registry():
    """Scan installed pip packages matching cli-anything-* and update registry."""
    registry = load_registry()

    # Check each entry's installed status
    for wc, entry in registry.items():
        entry["installed"] = is_cli_available(entry.get("entry_point", ""))

    # Discover new cli-anything packages on PATH
    try:
        r = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            for pkg in json.loads(r.stdout):
                name = pkg.get("name", "")
                if name.startswith("cli-anything-") and name not in [e.get("package") for e in registry.values()]:
                    # New package found — add a basic entry
                    app_name = name.replace("cli-anything-", "")
                    registry[app_name] = {
                        "window_class": app_name,
                        "entry_point": name,
                        "package": name,
                        "version": pkg.get("version", "0.0.0"),
                        "capabilities": [],
                        "query_map": {},
                        "installed": True,
                        "source": "discovered",
                    }
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # Save updated registry
    _save_registry(registry)
    return registry


def register_cli(window_class: str, entry_point: str, package: str,
                 capabilities: list, query_map: dict | None = None):
    """Register a new CLI wrapper (used after on-demand generation)."""
    global _cache
    registry = load_registry()
    registry[window_class.lower()] = {
        "window_class": window_class.lower(),
        "entry_point": entry_point,
        "package": package,
        "version": "0.1.0",
        "capabilities": capabilities,
        "query_map": query_map or {},
        "installed": is_cli_available(entry_point),
        "source": "generated",
    }
    _save_registry(registry)
    _cache = registry


def list_registry() -> list:
    """Return registry entries as a list (for MCP tool output)."""
    registry = load_registry()
    result = []
    for wc, entry in registry.items():
        result.append({
            "app": wc,
            "entry_point": entry.get("entry_point", ""),
            "installed": entry.get("installed", False),
            "available": is_cli_available(entry.get("entry_point", "")),
            "capabilities": entry.get("capabilities", []),
            "source": entry.get("source", "unknown"),
        })
    return result


def _save_registry(registry: dict):
    """Save registry to disk."""
    global _cache
    COSTA_DIR.mkdir(parents=True, exist_ok=True)
    entries = list(registry.values())
    REGISTRY_PATH.write_text(json.dumps(entries, indent=2))
    _cache = registry
