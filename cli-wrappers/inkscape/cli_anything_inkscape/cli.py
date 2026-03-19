#!/usr/bin/env python3
"""CLI-Anything Inkscape — deterministic CLI for Inkscape editor state.

Uses hyprctl for window detection, Inkscape CLI for exports,
and XDG recent files / Inkscape config for history.

Usage:
    cli-anything-inkscape status --json
    cli-anything-inkscape documents list --json
    cli-anything-inkscape recent list --json
    cli-anything-inkscape export --json --input file.svg --format png --output file.png
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


def _inkscape_windows() -> list[dict]:
    """Find Inkscape windows from Hyprland clients."""
    clients = _hyprctl_clients()
    windows = []
    for c in clients:
        if c.get("class", "").lower() == "org.inkscape.inkscape" or \
           c.get("class", "").lower() == "inkscape":
            windows.append(c)
    return windows


def _parse_filename_from_title(title: str) -> str | None:
    """Extract filename from Inkscape window title.

    Inkscape titles look like: 'filename.svg - Inkscape'
    or 'filename.svg (imported) - Inkscape'
    """
    if not title:
        return None
    # Strip " - Inkscape" suffix
    if " - Inkscape" in title:
        name = title.rsplit(" - Inkscape", 1)[0].strip()
        # Strip parenthetical annotations like (imported)
        if "(" in name:
            name = name.rsplit("(", 1)[0].strip()
        return name if name else None
    return None


def _is_running() -> bool:
    """Check if Inkscape is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "inkscape"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_recent_files() -> list[dict]:
    """Read recently opened files from Inkscape's recent files or XDG recent."""
    results = []

    # Try Inkscape's own recent-files.csv
    inkscape_recent = Path.home() / ".config" / "inkscape" / "recent-files.csv"
    if inkscape_recent.exists():
        try:
            for line in inkscape_recent.read_text().strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # CSV format: path,timestamp or just path
                parts = line.split(",", 1)
                filepath = parts[0].strip().strip('"')
                if filepath:
                    results.append({
                        "path": filepath,
                        "exists": Path(filepath).exists(),
                    })
        except Exception:
            pass

    if results:
        return results

    # Fallback: XDG recently-used.xbel
    xbel_path = Path.home() / ".local" / "share" / "recently-used.xbel"
    if xbel_path.exists():
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xbel_path)
            root = tree.getroot()
            for bookmark in root.findall("{http://www.freedesktop.org/standards/desktop-bookmarks}bookmark"):
                href = bookmark.get("href", "")
                # Filter for SVG/Inkscape-related files
                if any(href.lower().endswith(ext) for ext in
                       (".svg", ".svgz", ".eps", ".pdf", ".png", ".ai")):
                    # Convert file:// URI to path
                    if href.startswith("file://"):
                        filepath = href[7:]
                    else:
                        filepath = href
                    from urllib.parse import unquote
                    filepath = unquote(filepath)
                    results.append({
                        "path": filepath,
                        "exists": Path(filepath).exists(),
                    })
        except Exception:
            pass

    return results


@click.group()
def cli():
    """CLI-Anything Inkscape — deterministic vector editor state access."""
    pass


@cli.command()
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def status(as_json):
    """Show Inkscape running status and current file."""
    running = _is_running()
    current_file = None
    focused = False

    if running:
        windows = _inkscape_windows()
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
        click.echo(f"Inkscape: {state}")
        if current_file:
            click.echo(f"Current file: {current_file}")


@cli.group()
def documents():
    """Manage open Inkscape documents."""
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
            click.echo("Inkscape is not running.")
        return

    windows = _inkscape_windows()
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


@cli.command()
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--input", "input_file", required=True, help="Input SVG file")
@click.option("--format", "fmt", default="png", help="Export format (png, pdf, eps, ps)")
@click.option("--output", "output_file", required=True, help="Output file path")
@click.option("--dpi", default=96, help="Export DPI")
def export(as_json, input_file, fmt, output_file, dpi):
    """Export an SVG file to another format via Inkscape CLI."""
    input_path = Path(input_file)
    if not input_path.exists():
        result = {"success": False, "error": f"Input file not found: {input_file}"}
        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    cmd = [
        "inkscape",
        f"--export-filename={output_file}",
        f"--export-type={fmt}",
        f"--export-dpi={dpi}",
        str(input_path),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        success = proc.returncode == 0 and Path(output_file).exists()
        result = {
            "success": success,
            "input": str(input_path),
            "output": output_file,
            "format": fmt,
            "dpi": dpi,
        }
        if not success:
            result["error"] = proc.stderr.strip() or "Export failed"

        if as_json:
            click.echo(json.dumps(result))
        else:
            if success:
                click.echo(f"Exported: {output_file}")
            else:
                click.echo(f"Export failed: {result.get('error', 'unknown')}", err=True)
                sys.exit(1)
    except subprocess.TimeoutExpired:
        result = {"success": False, "error": "Export timed out after 120s"}
        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo("Error: export timed out", err=True)
        sys.exit(1)
    except FileNotFoundError:
        result = {"success": False, "error": "inkscape command not found"}
        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo("Error: inkscape not installed", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
