#!/usr/bin/env python3
"""CLI-Anything VS Code — deterministic CLI for Visual Studio Code editor state.

Uses hyprctl window titles and VS Code config/state files to query editor state.
No accessibility tree parsing required.

Usage:
    cli-anything-code workspace current --json
    cli-anything-code workspace recent --json
    cli-anything-code extensions list --json
    cli-anything-code files open --json
    cli-anything-code settings get --json --key "editor.fontSize"
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import click

# VS Code config directory (Linux)
VSCODE_CONFIG = Path.home() / ".config" / "Code" / "User"
VSCODE_GLOBAL_STORAGE = VSCODE_CONFIG / "globalStorage"
VSCODE_SETTINGS = VSCODE_CONFIG / "settings.json"
VSCODE_STATE_DB = VSCODE_GLOBAL_STORAGE / "state.vscdb"
VSCODE_STORAGE_JSON = VSCODE_GLOBAL_STORAGE / "storage.json"

# Hyprland window classes that match VS Code
VSCODE_CLASSES = {"code", "code-url-handler", "Code", "visual-studio-code"}


def _is_vscode_running() -> bool:
    """Check if any VS Code process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "code"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_vscode_windows() -> list[dict]:
    """Get all VS Code windows from Hyprland via hyprctl."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        clients = json.loads(result.stdout)
        return [
            c for c in clients
            if c.get("class", "").lower() in {v.lower() for v in VSCODE_CLASSES}
        ]
    except Exception:
        return []


def _get_active_window() -> dict | None:
    """Get the currently focused Hyprland window."""
    try:
        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def _parse_window_title(title: str) -> dict:
    """Parse VS Code window title into components.

    VS Code titles follow patterns like:
        "filename.py - folder - Visual Studio Code"
        "folder - Visual Studio Code"
        "Welcome - Visual Studio Code"
    """
    parts = [p.strip() for p in title.split(" - ")]
    info = {"raw_title": title}

    # Remove the "Visual Studio Code" suffix
    if parts and parts[-1] == "Visual Studio Code":
        parts = parts[:-1]

    if len(parts) == 0:
        return info
    elif len(parts) == 1:
        # Could be just a folder name or a file
        info["folder"] = parts[0]
    elif len(parts) == 2:
        info["file"] = parts[0]
        info["folder"] = parts[1]
    else:
        # More complex: "file - subfolder - folder" or similar
        info["file"] = parts[0]
        info["folder"] = parts[-1]
        info["path_parts"] = parts[1:-1]

    return info


def _query_state_db(query: str, params: tuple = ()) -> list:
    """Query the VS Code state SQLite database (state.vscdb)."""
    if not VSCODE_STATE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(
            f"file:{VSCODE_STATE_DB}?mode=ro&immutable=1", uri=True
        )
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def _read_state_db_value(key: str) -> str | None:
    """Read a single value from state.vscdb by key."""
    rows = _query_state_db(
        "SELECT value FROM ItemTable WHERE key = ?", (key,)
    )
    return rows[0][0] if rows else None


def _get_recent_workspaces_from_db() -> list[dict]:
    """Read recently opened workspaces/folders from state.vscdb."""
    raw = _read_state_db_value("history.recentlyOpenedPathsList")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        results = []
        for entry in data.get("entries", []):
            item = {}
            if "folderUri" in entry:
                item["type"] = "folder"
                item["uri"] = entry["folderUri"]
                # file:///path/to/folder -> /path/to/folder
                if item["uri"].startswith("file://"):
                    item["path"] = item["uri"][7:]
            elif "workspace" in entry:
                ws = entry["workspace"]
                item["type"] = "workspace"
                item["uri"] = ws.get("configPath", "")
                if item["uri"].startswith("file://"):
                    item["path"] = item["uri"][7:]
            elif "fileUri" in entry:
                item["type"] = "file"
                item["uri"] = entry["fileUri"]
                if item["uri"].startswith("file://"):
                    item["path"] = item["uri"][7:]
            else:
                continue

            if "label" in entry:
                item["label"] = entry["label"]
            if "remoteAuthority" in entry:
                item["remote"] = entry["remoteAuthority"]

            results.append(item)
        return results
    except (json.JSONDecodeError, KeyError):
        return []


def _get_recent_workspaces_from_json() -> list[dict]:
    """Fallback: read recently opened from storage.json."""
    if not VSCODE_STORAGE_JSON.exists():
        return []
    try:
        data = json.loads(VSCODE_STORAGE_JSON.read_text())
        raw = data.get("openedPathsList", {})
        results = []
        for ws in raw.get("workspaces3", []):
            if isinstance(ws, str):
                results.append({"type": "folder", "uri": ws})
                if ws.startswith("file://"):
                    results[-1]["path"] = ws[7:]
            elif isinstance(ws, dict):
                item = {"type": "workspace"}
                item["uri"] = ws.get("configPath", "")
                if item["uri"].startswith("file://"):
                    item["path"] = item["uri"][7:]
                results.append(item)
        return results
    except Exception:
        return []


def _get_open_files_from_db() -> list[dict]:
    """Read open editor tabs from state.vscdb."""
    # VS Code stores open editors per window in various keys
    results = []

    # Try the editorpart storage key
    for key_prefix in [
        "workbench.editor.languageDetectionOpenedLanguages.",
        "memento/workbench.editors.files.textFileEditor",
    ]:
        rows = _query_state_db(
            "SELECT key, value FROM ItemTable WHERE key LIKE ?",
            (f"{key_prefix}%",),
        )
        for key, value in rows:
            try:
                data = json.loads(value)
                if isinstance(data, dict) and "resource" in data:
                    uri = data["resource"]
                    item = {"uri": uri}
                    if uri.startswith("file://"):
                        item["path"] = uri[7:]
                    results.append(item)
            except (json.JSONDecodeError, TypeError):
                continue

    # Try backup workspaces storage for open editors
    raw = _read_state_db_value("workbench.activity.pinnedViewlets2")
    # This key doesn't help, but the editor MRU does:
    mru_raw = _read_state_db_value(
        "memento/workbench.editor.editorHistoryModel"
    )
    if mru_raw:
        try:
            mru_data = json.loads(mru_raw)
            entries = mru_data if isinstance(mru_data, list) else mru_data.get("entries", [])
            for entry in entries:
                if isinstance(entry, dict):
                    editor = entry.get("editor", entry)
                    uri = editor.get("resource", "")
                    if uri and uri.startswith("file://"):
                        results.append({
                            "uri": uri,
                            "path": uri[7:],
                        })
        except (json.JSONDecodeError, TypeError):
            pass

    # Deduplicate by path
    seen = set()
    unique = []
    for r in results:
        key = r.get("path", r.get("uri", ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def _error_exit(message: str, as_json: bool = True):
    """Print error and exit."""
    if as_json:
        click.echo(json.dumps({"error": message}))
    else:
        click.echo(f"Error: {message}", err=True)
    sys.exit(1)


@click.group()
def cli():
    """CLI-Anything VS Code — deterministic editor state access."""
    pass


# ── workspace ──────────────────────────────────────────────────────────

@cli.group()
def workspace():
    """VS Code workspace and folder information."""
    pass


@workspace.command("current")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def workspace_current(as_json):
    """Show the current workspace/folder from the active VS Code window."""
    if not _is_vscode_running():
        _error_exit("VS Code is not running", as_json)

    # Check if the active window is VS Code
    active = _get_active_window()
    vscode_windows = _get_vscode_windows()

    if not vscode_windows:
        _error_exit("No VS Code windows found", as_json)

    # Prefer the active window if it's VS Code
    target = None
    if active and active.get("class", "").lower() in {v.lower() for v in VSCODE_CLASSES}:
        target = active
    else:
        # Use the first (most recently focused) VS Code window
        target = vscode_windows[0]

    title = target.get("title", "")
    parsed = _parse_window_title(title)
    parsed["window_address"] = target.get("address", "")
    parsed["workspace_id"] = target.get("workspace", {}).get("id", "")
    parsed["pid"] = target.get("pid", 0)

    if as_json:
        click.echo(json.dumps(parsed))
    else:
        folder = parsed.get("folder", "unknown")
        file = parsed.get("file", "")
        if file:
            click.echo(f"{file} in {folder}")
        else:
            click.echo(folder)


@workspace.command("recent")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--limit", default=20, help="Number of entries")
def workspace_recent(as_json, limit):
    """List recently opened workspaces and folders."""
    # Try state.vscdb first, fall back to storage.json
    workspaces = _get_recent_workspaces_from_db()
    if not workspaces:
        workspaces = _get_recent_workspaces_from_json()

    workspaces = workspaces[:limit]

    if as_json:
        click.echo(json.dumps({"workspaces": workspaces, "count": len(workspaces)}))
    else:
        for ws in workspaces:
            path = ws.get("path", ws.get("uri", ""))
            wtype = ws.get("type", "unknown")
            click.echo(f"[{wtype}] {path}")


# ── extensions ─────────────────────────────────────────────────────────

@cli.group()
def extensions():
    """VS Code extensions."""
    pass


@extensions.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def extensions_list(as_json):
    """List installed VS Code extensions."""
    try:
        result = subprocess.run(
            ["code", "--list-extensions", "--show-versions"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            _error_exit(
                f"Failed to list extensions: {result.stderr.strip()}", as_json
            )

        ext_list = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if "@" in line:
                ext_id, version = line.rsplit("@", 1)
                ext_list.append({"id": ext_id, "version": version})
            else:
                ext_list.append({"id": line, "version": ""})

        if as_json:
            click.echo(json.dumps({"extensions": ext_list, "count": len(ext_list)}))
        else:
            for ext in ext_list:
                click.echo(f"{ext['id']}@{ext['version']}" if ext["version"] else ext["id"])

    except FileNotFoundError:
        _error_exit("'code' CLI not found in PATH", as_json)
    except subprocess.TimeoutExpired:
        _error_exit("Timed out listing extensions", as_json)


# ── files ──────────────────────────────────────────────────────────────

@cli.group()
def files():
    """VS Code open files."""
    pass


@files.command("open")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def files_open(as_json):
    """List currently open files in VS Code."""
    open_files = []

    # Source 1: Window titles from Hyprland (most reliable for "currently visible")
    vscode_windows = _get_vscode_windows()
    for win in vscode_windows:
        parsed = _parse_window_title(win.get("title", ""))
        if "file" in parsed:
            open_files.append({
                "file": parsed["file"],
                "folder": parsed.get("folder", ""),
                "source": "window_title",
            })

    # Source 2: Editor history from state.vscdb (recently edited files)
    db_files = _get_open_files_from_db()
    for f in db_files:
        path = f.get("path", "")
        if path:
            open_files.append({
                "file": Path(path).name,
                "path": path,
                "source": "state_db",
            })

    # Deduplicate by filename (prefer window_title source)
    seen = set()
    unique = []
    for f in open_files:
        key = f.get("path", f.get("file", ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(f)

    if not unique and not _is_vscode_running():
        _error_exit("VS Code is not running", as_json)

    if as_json:
        click.echo(json.dumps({"files": unique, "count": len(unique)}))
    else:
        for f in unique:
            path = f.get("path", f.get("file", ""))
            click.echo(path)


# ── settings ───────────────────────────────────────────────────────────

@cli.group()
def settings():
    """VS Code settings."""
    pass


@settings.command("get")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--key", required=True, help="Setting key (e.g. editor.fontSize)")
def settings_get(as_json, key):
    """Read a VS Code setting by key."""
    if not VSCODE_SETTINGS.exists():
        _error_exit(f"Settings file not found: {VSCODE_SETTINGS}", as_json)

    try:
        # VS Code settings.json may have comments (JSONC) — strip them
        raw = VSCODE_SETTINGS.read_text()
        # Simple comment stripping: remove // comments and /* */ blocks
        import re
        # Remove single-line comments (but not inside strings)
        cleaned = re.sub(r'(?<!:)//.*$', '', raw, flags=re.MULTILINE)
        # Remove multi-line comments
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        # Remove trailing commas before } or ]
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

        data = json.loads(cleaned)
    except (json.JSONDecodeError, OSError) as e:
        _error_exit(f"Failed to parse settings: {e}", as_json)

    # Support dotted keys: "editor.fontSize" -> data["editor.fontSize"]
    # VS Code uses flat dotted keys, not nested objects
    value = data.get(key)

    if value is None:
        # Also try nested lookup for non-standard settings
        parts = key.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                current = None
                break
        value = current

    if as_json:
        click.echo(json.dumps({"key": key, "value": value}))
    else:
        click.echo(f"{key} = {value}")


def main():
    cli()


if __name__ == "__main__":
    main()
