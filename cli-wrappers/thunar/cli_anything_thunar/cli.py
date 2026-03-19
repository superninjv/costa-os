#!/usr/bin/env python3
"""CLI-Anything Thunar — deterministic CLI for Thunar file manager.

Uses Thunar's DBus interface and direct filesystem reads.

Usage:
    cli-anything-thunar files list --json [--path /some/dir]
    cli-anything-thunar navigation current-dir --json
    cli-anything-thunar tabs list --json
    cli-anything-thunar bookmarks list --json
"""

import json
import os
import subprocess
from pathlib import Path

import click


def _get_thunar_cwd() -> str:
    """Get Thunar's current working directory via DBus or window title."""
    try:
        r = subprocess.run(
            ["dbus-send", "--session", "--dest=org.xfce.Thunar",
             "--type=method_call", "--print-reply",
             "/org/xfce/FileManager", "org.xfce.FileManager.CurrentDirectory"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and "string" in r.stdout:
            for line in r.stdout.splitlines():
                if "string" in line:
                    return line.split('"')[1]
    except Exception:
        pass

    # Fallback: parse window title
    try:
        r = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            for client in json.loads(r.stdout):
                if "thunar" in client.get("class", "").lower():
                    title = client.get("title", "")
                    # Thunar title format: "directory_name - File Manager"
                    if " - " in title:
                        dir_name = title.rsplit(" - ", 1)[0].strip()
                        # Try to resolve to full path
                        if os.path.isdir(dir_name):
                            return dir_name
                        home = str(Path.home())
                        candidate = os.path.join(home, dir_name)
                        if os.path.isdir(candidate):
                            return candidate
                        return dir_name
    except Exception:
        pass

    return str(Path.home())


@click.group()
def cli():
    """CLI-Anything Thunar — deterministic file manager access."""
    pass


@cli.group()
def files():
    """File operations."""
    pass


@files.command("list")
@click.option("--json", "as_json", is_flag=True, default=True)
@click.option("--path", default="", help="Directory to list (default: Thunar's current dir)")
def files_list(as_json, path):
    """List files in a directory."""
    target = path or _get_thunar_cwd()
    try:
        entries = []
        for entry in sorted(Path(target).iterdir()):
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size,
                "hidden": entry.name.startswith("."),
            })
        if as_json:
            click.echo(json.dumps({
                "path": str(target),
                "files": entries,
                "count": len(entries),
            }))
        else:
            for e in entries:
                prefix = "d" if e["type"] == "directory" else "-"
                click.echo(f"{prefix} {e['name']}")
    except PermissionError:
        click.echo(json.dumps({"error": f"Permission denied: {target}"}))
    except FileNotFoundError:
        click.echo(json.dumps({"error": f"Not found: {target}"}))


@cli.group()
def navigation():
    """Navigation state."""
    pass


@navigation.command("current-dir")
@click.option("--json", "as_json", is_flag=True, default=True)
def nav_current_dir(as_json):
    """Get Thunar's current directory."""
    cwd = _get_thunar_cwd()
    if as_json:
        click.echo(json.dumps({"directory": cwd}))
    else:
        click.echo(cwd)


@cli.group()
def tabs():
    """Thunar tab management."""
    pass


@tabs.command("list")
@click.option("--json", "as_json", is_flag=True, default=True)
def tabs_list(as_json):
    """List open Thunar tabs (from window titles)."""
    tab_list = []
    try:
        r = subprocess.run(["hyprctl", "clients", "-j"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            for client in json.loads(r.stdout):
                if "thunar" in client.get("class", "").lower():
                    tab_list.append({
                        "title": client.get("title", ""),
                        "workspace": client.get("workspace", {}).get("name", ""),
                    })
    except Exception:
        pass

    if as_json:
        click.echo(json.dumps({"tabs": tab_list, "count": len(tab_list)}))
    else:
        for t in tab_list:
            click.echo(f"[ws:{t['workspace']}] {t['title']}")


@cli.group()
def bookmarks():
    """Thunar bookmarks."""
    pass


@bookmarks.command("list")
@click.option("--json", "as_json", is_flag=True, default=True)
def bookmarks_list(as_json):
    """List Thunar/GTK bookmarks."""
    bookmarks_file = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
    results = []

    if bookmarks_file.exists():
        for line in bookmarks_file.read_text().splitlines():
            parts = line.strip().split(" ", 1)
            if parts:
                uri = parts[0]
                name = parts[1] if len(parts) > 1 else uri.split("/")[-1]
                results.append({"name": name, "uri": uri})

    if as_json:
        click.echo(json.dumps({"bookmarks": results, "count": len(results)}))
    else:
        for b in results:
            click.echo(f"{b['name']} → {b['uri']}")


def main():
    cli()


if __name__ == "__main__":
    main()
