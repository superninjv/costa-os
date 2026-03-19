#!/usr/bin/env python3
"""CLI-Anything Krita — deterministic CLI for Krita digital painting state.

Uses hyprctl for window detection, Krita config files for recent files
and installed resources.

Usage:
    cli-anything-krita status --json
    cli-anything-krita documents list --json
    cli-anything-krita recent list --json
    cli-anything-krita resources list --json --type brushes
"""

import json
import subprocess
import sys
from pathlib import Path

import click


def _hyprctl_clients() -> list[dict]:
    """Get all Hyprland clients via hyprctl."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _krita_windows() -> list[dict]:
    """Find Krita windows from Hyprland clients."""
    clients = _hyprctl_clients()
    windows = []
    for c in clients:
        cls = c.get("class", "").lower()
        if cls in ("krita", "org.kde.krita"):
            windows.append(c)
    return windows


def _parse_filename_from_title(title: str) -> str | None:
    """Extract filename from Krita window title.

    Krita titles look like: 'filename.kra \u2014 Krita'
    or 'filename.png [modified] \u2014 Krita'
    """
    if not title:
        return None
    # Krita uses em dash
    for sep in (" \u2014 Krita", " - Krita"):
        if sep in title:
            name = title.rsplit(sep, 1)[0].strip()
            # Strip modification markers
            for suffix in (" [modified]", " [*]", " *"):
                if name.endswith(suffix):
                    name = name[:-len(suffix)].strip()
            return name if name else None
    return None


def _is_running() -> bool:
    """Check if Krita is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "krita"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_recent_files() -> list[dict]:
    """Read recently opened files from Krita config."""
    results = []

    # Try krita_recent_files (one path per line)
    recent_file = Path.home() / ".local" / "share" / "krita" / "krita_recent_files"
    if recent_file.exists():
        try:
            for line in recent_file.read_text().strip().splitlines():
                filepath = line.strip()
                if filepath:
                    # Handle file:// URIs
                    if filepath.startswith("file://"):
                        from urllib.parse import unquote
                        filepath = unquote(filepath[7:])
                    results.append({
                        "path": filepath,
                        "exists": Path(filepath).exists(),
                    })
        except Exception:
            pass

    if results:
        return results

    # Fallback: parse kritarc [RecentFiles] section
    kritarc = Path.home() / ".config" / "kritarc"
    if kritarc.exists():
        try:
            in_section = False
            for line in kritarc.read_text().splitlines():
                line = line.strip()
                if line == "[RecentFiles]":
                    in_section = True
                    continue
                if line.startswith("[") and in_section:
                    break
                if in_section and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Keys like File1, File2, ... Name1, Name2, ...
                    if key.startswith("File") and value:
                        filepath = value
                        if filepath.startswith("file://"):
                            from urllib.parse import unquote
                            filepath = unquote(filepath[7:])
                        results.append({
                            "path": filepath,
                            "exists": Path(filepath).exists(),
                        })
        except Exception:
            pass

    return results


def _list_resources(resource_type: str) -> list[dict]:
    """List installed Krita resources of a given type."""
    krita_data = Path.home() / ".local" / "share" / "krita"

    # Map user-friendly names to directory names
    type_map = {
        "brushes": "paintoppresets",
        "brush_presets": "paintoppresets",
        "paintoppresets": "paintoppresets",
        "palettes": "palettes",
        "gradients": "gradients",
        "patterns": "patterns",
        "workspaces": "workspaces",
        "templates": "templates",
        "brushes_tips": "brushes",
        "brush_tips": "brushes",
    }

    dir_name = type_map.get(resource_type.lower(), resource_type.lower())
    resource_dir = krita_data / dir_name

    resources = []
    if resource_dir.exists() and resource_dir.is_dir():
        for f in sorted(resource_dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                resources.append({
                    "name": f.stem,
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                })

    return resources


@click.group()
def cli():
    """CLI-Anything Krita — deterministic digital painting app state access."""
    pass


@cli.command()
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def status(as_json):
    """Show Krita running status and current file."""
    running = _is_running()
    current_file = None
    focused = False

    if running:
        windows = _krita_windows()
        for w in windows:
            if w.get("focusHistoryID", -1) == 0 or w.get("focused", False):
                current_file = _parse_filename_from_title(w.get("title", ""))
                focused = True
                break
        if current_file is None and windows:
            current_file = _parse_filename_from_title(windows[0].get("title", ""))

    result = {
        "running": running,
        "focused": focused,
        "current_file": current_file,
    }

    if as_json:
        click.echo(json.dumps(result))
    else:
        state = "running" if running else "not running"
        click.echo(f"Krita: {state}")
        if current_file:
            click.echo(f"Current file: {current_file}")


@cli.group()
def documents():
    """Manage open Krita documents."""
    pass


@documents.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def documents_list(as_json):
    """List all open documents from window titles."""
    if not _is_running():
        result = {"documents": [], "count": 0, "running": False}
        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo("Krita is not running.")
        return

    windows = _krita_windows()
    docs = []
    for w in windows:
        filename = _parse_filename_from_title(w.get("title", ""))
        if filename:
            docs.append({
                "filename": filename,
                "title": w.get("title", ""),
                "focused": w.get("focused", False),
            })

    result = {"documents": docs, "count": len(docs), "running": True}

    if as_json:
        click.echo(json.dumps(result))
    else:
        if not docs:
            click.echo("No documents open.")
        for d in docs:
            marker = " *" if d["focused"] else ""
            click.echo(f"  {d['filename']}{marker}")


@cli.group()
def recent():
    """Recently opened files."""
    pass


@recent.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--limit", default=20, help="Number of entries")
def recent_list(as_json, limit):
    """List recently opened files."""
    files = _get_recent_files()[:limit]
    result = {"recent_files": files, "count": len(files)}

    if as_json:
        click.echo(json.dumps(result))
    else:
        if not files:
            click.echo("No recent files found.")
        for f in files:
            exists = "  " if f["exists"] else "! "
            click.echo(f"{exists}{f['path']}")


@cli.group()
def resources():
    """Installed Krita resources."""
    pass


@resources.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--type", "resource_type", default="brushes",
              help="Resource type (brushes, palettes, gradients, patterns, workspaces)")
def resources_list(as_json, resource_type):
    """List installed resources of a given type."""
    items = _list_resources(resource_type)
    result = {"resources": items, "count": len(items), "type": resource_type}

    if as_json:
        click.echo(json.dumps(result))
    else:
        if not items:
            click.echo(f"No {resource_type} found.")
        for r in items:
            click.echo(f"  {r['name']} ({r['filename']})")


def main():
    cli()


if __name__ == "__main__":
    main()
