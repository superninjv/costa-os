#!/usr/bin/env python3
"""CLI-Anything Vesktop — deterministic CLI for Discord (Vesktop) state.

Reads window titles via hyprctl and config files from ~/.config/vesktop/
to expose Discord status without requiring Discord API tokens.

Window title formats observed:
    "#channel - Server - Vesktop"       — text channel
    "Username - Vesktop"                — DM conversation
    "Server - Vesktop"                  — server view (no channel selected)
    "Friends - Vesktop"                 — friends list
    "Vesktop"                           — loading / home
    Title contains voice indicators when in voice channel.

Usage:
    cli-anything-vesktop status --json
    cli-anything-vesktop channel current --json
    cli-anything-vesktop settings get --json
    cli-anything-vesktop voice status --json
"""

import json
import subprocess
import sys
from pathlib import Path

import click


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hyprctl_clients() -> list[dict]:
    """Return parsed JSON from `hyprctl clients -j`."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return []


def _vesktop_windows() -> list[dict]:
    """Return hyprctl client entries whose class is 'vesktop'."""
    return [
        c for c in _hyprctl_clients()
        if c.get("class", "").lower() == "vesktop"
    ]


def _parse_window_title(title: str) -> dict:
    """Parse a Vesktop window title into structured data.

    Returns dict with keys: raw, server, channel, dm_user, view, in_voice.
    """
    result = {
        "raw": title,
        "server": None,
        "channel": None,
        "dm_user": None,
        "view": "unknown",
        "in_voice": False,
    }

    if not title or title.strip() == "Vesktop":
        result["view"] = "home"
        return result

    # Strip the " - Vesktop" suffix
    suffix = " - Vesktop"
    if title.endswith(suffix):
        body = title[: -len(suffix)]
    else:
        # Unexpected format — return raw
        result["view"] = "unknown"
        return result

    # Detect voice: Vesktop sometimes appends voice indicators or the title
    # reflects the voice channel. A channel starting with a speaker icon or
    # containing common voice-channel markers hints at voice state.
    # More reliable: check if multiple windows exist (voice overlay).
    # For now, we flag common patterns.
    voice_prefixes = ("\U0001f50a", "\U0001f509", "\U0001f507")  # speaker emojis
    if any(body.startswith(p) for p in voice_prefixes):
        result["in_voice"] = True
        body = body.lstrip("".join(voice_prefixes)).strip()

    # "#channel - Server" — text channel in a server
    if body.startswith("#"):
        parts = body.split(" - ", 1)
        result["channel"] = parts[0]  # includes the #
        result["server"] = parts[1] if len(parts) > 1 else None
        result["view"] = "channel"
        return result

    # "Friends" — friends list
    if body == "Friends":
        result["view"] = "friends"
        return result

    # "Name - Server" could be a voice channel (no #) or a DM
    # Heuristic: if there's a " - " separator, it's likely server context
    if " - " in body:
        parts = body.split(" - ", 1)
        # Could be a voice channel name or a non-text channel
        result["channel"] = parts[0]
        result["server"] = parts[1]
        result["view"] = "channel"
        return result

    # Single name — DM or server home
    result["dm_user"] = body
    result["view"] = "dm"
    return result


def _read_vesktop_settings() -> dict:
    """Read Vesktop settings from known config paths."""
    config_base = Path.home() / ".config" / "vesktop"
    settings = {}

    # Main settings.json (Vesktop-level settings)
    main_settings = config_base / "settings.json"
    if main_settings.exists():
        try:
            settings["vesktop"] = json.loads(main_settings.read_text())
        except (json.JSONDecodeError, OSError):
            settings["vesktop"] = None

    # Discord-level settings (Vencord injects into this path)
    discord_settings = config_base / "settings" / "settings.json"
    if discord_settings.exists():
        try:
            settings["vencord"] = json.loads(discord_settings.read_text())
        except (json.JSONDecodeError, OSError):
            settings["vencord"] = None

    return settings


def _json_output(data: dict) -> None:
    """Print compact JSON to stdout."""
    click.echo(json.dumps(data))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """CLI-Anything Vesktop — deterministic Discord state access."""
    pass


# -- status -----------------------------------------------------------------

@cli.command()
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def status(as_json):
    """Check if Vesktop is running and show current state."""
    windows = _vesktop_windows()
    running = len(windows) > 0

    result = {
        "running": running,
        "window_count": len(windows),
        "windows": [],
    }

    for w in windows:
        title = w.get("title", "")
        parsed = _parse_window_title(title)
        result["windows"].append({
            "title": title,
            "workspace": w.get("workspace", {}).get("id"),
            "focused": w.get("focusHistoryID", -1) == 0,
            "address": w.get("address", ""),
            "parsed": parsed,
        })

    if as_json:
        _json_output(result)
    else:
        if not running:
            click.echo("Vesktop is not running.")
        else:
            for win in result["windows"]:
                focus = " (focused)" if win["focused"] else ""
                click.echo(f"[ws {win['workspace']}] {win['title']}{focus}")


# -- channel ----------------------------------------------------------------

@cli.group()
def channel():
    """Discord channel information."""
    pass


@channel.command("current")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def channel_current(as_json):
    """Show the current server and channel from the active Vesktop window."""
    windows = _vesktop_windows()

    if not windows:
        result = {"error": "Vesktop is not running", "running": False}
        if as_json:
            _json_output(result)
        else:
            click.echo("Vesktop is not running.", err=True)
        sys.exit(1)

    # Prefer the focused window, fall back to first
    focused = [w for w in windows if w.get("focusHistoryID", -1) == 0]
    win = focused[0] if focused else windows[0]
    title = win.get("title", "")
    parsed = _parse_window_title(title)

    result = {
        "running": True,
        "server": parsed["server"],
        "channel": parsed["channel"],
        "dm_user": parsed["dm_user"],
        "view": parsed["view"],
        "in_voice": parsed["in_voice"],
        "raw_title": title,
    }

    if as_json:
        _json_output(result)
    else:
        if parsed["view"] == "channel":
            click.echo(f"{parsed['channel']} in {parsed['server']}")
        elif parsed["view"] == "dm":
            click.echo(f"DM: {parsed['dm_user']}")
        elif parsed["view"] == "friends":
            click.echo("Friends list")
        else:
            click.echo(f"View: {parsed['view']} ({title})")


# -- settings ---------------------------------------------------------------

@cli.group()
def settings():
    """Vesktop and Vencord settings."""
    pass


@settings.command("get")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--key", default=None, help="Dot-separated key to extract (e.g. 'vesktop.minimizeToTray')")
def settings_get(as_json, key):
    """Read Vesktop and Vencord settings from config files."""
    all_settings = _read_vesktop_settings()

    if key:
        # Navigate dot-separated path
        parts = key.split(".")
        value = all_settings
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                value = None
                break
        result = {"key": key, "value": value}
    else:
        result = {
            "vesktop_config": str(Path.home() / ".config" / "vesktop" / "settings.json"),
            "vencord_config": str(Path.home() / ".config" / "vesktop" / "settings" / "settings.json"),
            "settings": all_settings,
        }

    if as_json:
        _json_output(result)
    else:
        click.echo(json.dumps(result, indent=2))


# -- voice ------------------------------------------------------------------

@cli.group()
def voice():
    """Discord voice channel state."""
    pass


@voice.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def voice_status(as_json):
    """Detect if currently in a voice channel.

    Uses window title heuristics and multi-window detection.
    When in a voice call, Vesktop may show a second window (voice overlay)
    or change the title to reflect the voice channel.
    """
    windows = _vesktop_windows()

    if not windows:
        result = {"error": "Vesktop is not running", "running": False, "in_voice": False}
        if as_json:
            _json_output(result)
        else:
            click.echo("Vesktop is not running.", err=True)
        sys.exit(1)

    # Parse all windows for voice indicators
    in_voice = False
    voice_channel = None
    voice_server = None

    for w in windows:
        parsed = _parse_window_title(w.get("title", ""))
        if parsed["in_voice"]:
            in_voice = True
            voice_channel = parsed["channel"]
            voice_server = parsed["server"]
            break

    # Heuristic: multiple vesktop windows may indicate voice overlay
    if len(windows) > 1 and not in_voice:
        in_voice = True  # likely voice overlay / popout

    result = {
        "running": True,
        "in_voice": in_voice,
        "voice_channel": voice_channel,
        "voice_server": voice_server,
        "window_count": len(windows),
    }

    if as_json:
        _json_output(result)
    else:
        if in_voice:
            ch = voice_channel or "unknown channel"
            srv = f" in {voice_server}" if voice_server else ""
            click.echo(f"In voice: {ch}{srv}")
        else:
            click.echo("Not in voice.")


# ---------------------------------------------------------------------------

def main():
    cli()


if __name__ == "__main__":
    main()
