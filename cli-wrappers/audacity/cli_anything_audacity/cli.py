#!/usr/bin/env python3
"""CLI-Anything Audacity — deterministic CLI for Audacity audio editor state.

Uses hyprctl for window detection, Audacity config for recent files,
and ALSA tools for audio device enumeration.

Usage:
    cli-anything-audacity status --json
    cli-anything-audacity projects list --json
    cli-anything-audacity recent list --json
    cli-anything-audacity devices list --json
"""

import json
import re
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


def _audacity_windows() -> list[dict]:
    """Find Audacity windows from Hyprland clients."""
    clients = _hyprctl_clients()
    windows = []
    for c in clients:
        cls = c.get("class", "").lower()
        if cls in ("audacity", "org.audacityteam.audacity"):
            windows.append(c)
    return windows


def _parse_project_from_title(title: str) -> str | None:
    """Extract project name from Audacity window title.

    Audacity titles look like: 'ProjectName - Audacity'
    or 'filename.aup3 - Audacity'
    """
    if not title:
        return None
    if " - Audacity" in title:
        name = title.rsplit(" - Audacity", 1)[0].strip()
        # Strip modification marker
        if name.endswith("*"):
            name = name[:-1].strip()
        return name if name else None
    return None


def _is_running() -> bool:
    """Check if Audacity is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "audacity"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_recent_files() -> list[dict]:
    """Read recently opened files from Audacity config."""
    results = []
    cfg_path = Path.home() / ".config" / "audacity" / "audacity.cfg"

    if not cfg_path.exists():
        # Try older location
        cfg_path = Path.home() / ".audacity-data" / "audacity.cfg"

    if not cfg_path.exists():
        return results

    try:
        in_section = False
        for line in cfg_path.read_text().splitlines():
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
                # Keys like File1, File2, ... or file0, file1, ...
                if key.lower().startswith("file") and value:
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


def _parse_alsa_devices(output: str, direction: str) -> list[dict]:
    """Parse output of arecord -l or aplay -l into device list."""
    devices = []
    # Lines like: card 0: PCH [HDA Intel PCH], device 0: ALC269 Analog [ALC269 Analog]
    pattern = re.compile(
        r"card\s+(\d+):\s+(\S+)\s+\[([^\]]*)\],\s+device\s+(\d+):\s+([^\[]*)\[([^\]]*)\]"
    )
    for line in output.splitlines():
        m = pattern.search(line)
        if m:
            devices.append({
                "card": int(m.group(1)),
                "card_id": m.group(2),
                "card_name": m.group(3),
                "device": int(m.group(4)),
                "device_id": m.group(5).strip(),
                "device_name": m.group(6),
                "direction": direction,
                "alsa_id": f"hw:{m.group(1)},{m.group(4)}",
            })
    return devices


def _list_audio_devices() -> list[dict]:
    """List audio devices using arecord and aplay."""
    devices = []

    for cmd, direction in [
        (["arecord", "-l"], "input"),
        (["aplay", "-l"], "output"),
    ]:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                devices.extend(_parse_alsa_devices(result.stdout, direction))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return devices


@click.group()
def cli():
    """CLI-Anything Audacity — deterministic audio editor state access."""
    pass


@cli.command()
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def status(as_json):
    """Show Audacity running status and current project."""
    running = _is_running()
    current_project = None
    focused = False

    if running:
        windows = _audacity_windows()
        for w in windows:
            if w.get("focusHistoryID", -1) == 0 or w.get("focused", False):
                current_project = _parse_project_from_title(w.get("title", ""))
                focused = True
                break
        if current_project is None and windows:
            current_project = _parse_project_from_title(windows[0].get("title", ""))

    result = {
        "running": running,
        "focused": focused,
        "current_project": current_project,
    }

    if as_json:
        click.echo(json.dumps(result))
    else:
        state = "running" if running else "not running"
        click.echo(f"Audacity: {state}")
        if current_project:
            click.echo(f"Current project: {current_project}")


@cli.group()
def projects():
    """Manage open Audacity projects."""
    pass


@projects.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def projects_list(as_json):
    """List all open projects from window titles."""
    if not _is_running():
        result = {"projects": [], "count": 0, "running": False}
        if as_json:
            click.echo(json.dumps(result))
        else:
            click.echo("Audacity is not running.")
        return

    windows = _audacity_windows()
    projs = []
    for w in windows:
        project = _parse_project_from_title(w.get("title", ""))
        if project:
            projs.append({
                "project": project,
                "title": w.get("title", ""),
                "focused": w.get("focused", False),
            })

    result = {"projects": projs, "count": len(projs), "running": True}

    if as_json:
        click.echo(json.dumps(result))
    else:
        if not projs:
            click.echo("No projects open.")
        for p in projs:
            marker = " *" if p["focused"] else ""
            click.echo(f"  {p['project']}{marker}")


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
def devices():
    """Audio devices."""
    pass


@devices.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--direction", type=click.Choice(["all", "input", "output"]),
              default="all", help="Filter by direction")
def devices_list(as_json, direction):
    """List audio input/output devices via ALSA."""
    all_devices = _list_audio_devices()
    if direction != "all":
        all_devices = [d for d in all_devices if d["direction"] == direction]

    result = {"devices": all_devices, "count": len(all_devices)}

    if as_json:
        click.echo(json.dumps(result))
    else:
        if not all_devices:
            click.echo("No audio devices found.")
        for d in all_devices:
            arrow = "<-" if d["direction"] == "input" else "->"
            click.echo(f"  {arrow} [{d['alsa_id']}] {d['card_name']}: {d['device_name']}")


def main():
    cli()


if __name__ == "__main__":
    main()
