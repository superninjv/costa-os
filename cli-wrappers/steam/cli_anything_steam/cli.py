#!/usr/bin/env python3
"""CLI-Anything Steam — deterministic CLI for Steam library and game state.

Parses VDF/ACF manifest files to read game library state. Uses hyprctl to
detect running Steam/game windows.

Usage:
    cli-anything-steam library list --json
    cli-anything-steam library count --json
    cli-anything-steam status --json
    cli-anything-steam game info --json --appid 431960
    cli-anything-steam running --json
    cli-anything-steam downloads --json
"""

import json
import subprocess
import sys
from pathlib import Path

import click

STEAM_ROOT = Path.home() / ".local" / "share" / "Steam"
STEAMAPPS = STEAM_ROOT / "steamapps"


# ---------------------------------------------------------------------------
# VDF / ACF parser
# ---------------------------------------------------------------------------

def parse_vdf(text: str) -> dict:
    """Parse Valve Data Format text into a nested dict.

    VDF is a simple format:
        "key"    "value"
        "key"
        {
            ...nested...
        }

    No commas, no colons. Keys and values are double-quoted strings.
    Braces denote nested dicts.
    """
    tokens = _tokenize_vdf(text)
    result, _ = _parse_vdf_tokens(tokens, 0)
    return result


def _tokenize_vdf(text: str) -> list[str]:
    """Tokenize VDF text into quoted strings and braces."""
    tokens: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in (" ", "\t", "\r", "\n"):
            i += 1
        elif ch == "/" and i + 1 < length and text[i + 1] == "/":
            # Line comment — skip to end of line
            while i < length and text[i] != "\n":
                i += 1
        elif ch == '"':
            # Quoted string
            j = i + 1
            while j < length and text[j] != '"':
                if text[j] == "\\":
                    j += 1  # skip escaped char
                j += 1
            tokens.append(text[i + 1 : j])
            i = j + 1
        elif ch in ("{", "}"):
            tokens.append(ch)
            i += 1
        else:
            # Unquoted token (some VDF files use unquoted keys)
            j = i
            while j < length and text[j] not in (" ", "\t", "\r", "\n", '"', "{", "}"):
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_vdf_tokens(tokens: list[str], pos: int) -> tuple[dict, int]:
    """Recursively parse tokens into a dict starting at pos."""
    result: dict = {}
    while pos < len(tokens):
        token = tokens[pos]
        if token == "}":
            return result, pos + 1
        key = token
        pos += 1
        if pos >= len(tokens):
            break
        if tokens[pos] == "{":
            pos += 1  # consume '{'
            value, pos = _parse_vdf_tokens(tokens, pos)
            result[key] = value
        else:
            result[key] = tokens[pos]
            pos += 1
    return result, pos


# ---------------------------------------------------------------------------
# Steam data readers
# ---------------------------------------------------------------------------

def _steam_installed() -> bool:
    """Check if the Steam directory exists."""
    return STEAM_ROOT.is_dir()


def _read_acf(path: Path) -> dict | None:
    """Read and parse a single ACF manifest file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_vdf(text)
        # ACF files have a top-level "AppState" key
        return parsed.get("AppState", parsed)
    except Exception:
        return None


def _list_installed_games() -> list[dict]:
    """Parse all appmanifest_*.acf files and return game info."""
    if not STEAMAPPS.is_dir():
        return []

    games = []
    for acf in sorted(STEAMAPPS.glob("appmanifest_*.acf")):
        data = _read_acf(acf)
        if data is None:
            continue
        size_bytes = int(data.get("SizeOnDisk", "0"))
        games.append({
            "appid": data.get("appid", ""),
            "name": data.get("name", ""),
            "installdir": data.get("installdir", ""),
            "size_bytes": size_bytes,
            "size_human": _human_size(size_bytes),
            "last_played": int(data.get("LastPlayed", "0")) or None,
            "last_updated": int(data.get("LastUpdated", "0")) or None,
            "state_flags": int(data.get("StateFlags", "0")),
            "build_id": data.get("buildid", ""),
        })
    return games


def _human_size(nbytes: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def _hyprctl_clients() -> list[dict]:
    """Get window list from hyprctl."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _is_steam_running() -> bool:
    """Check if Steam is running via hyprctl or process list."""
    # Check hyprctl first
    for client in _hyprctl_clients():
        if "steam" in client.get("class", "").lower():
            return True
    # Fallback: check process list
    try:
        result = subprocess.run(
            ["pgrep", "-x", "steam"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _detect_running_game() -> dict | None:
    """Detect a currently running game from hyprctl window list.

    Steam game windows typically have a class different from 'steam' and
    often match an installed game's name or installdir.
    """
    clients = _hyprctl_clients()
    installed = {g["installdir"].lower(): g for g in _list_installed_games()}
    installed_names = {g["name"].lower(): g for g in _list_installed_games()}

    steam_classes = {"steam", "steamwebhelper", ""}

    for client in clients:
        wclass = client.get("class", "").lower()
        title = client.get("title", "")

        # Skip Steam UI windows
        if wclass in steam_classes:
            continue

        # Try matching window class to installdir or game name
        for key, game in installed.items():
            if key and key in wclass:
                return {
                    "appid": game["appid"],
                    "name": game["name"],
                    "window_class": client.get("class", ""),
                    "window_title": title,
                }

        for name_lower, game in installed_names.items():
            if name_lower and name_lower in title.lower():
                return {
                    "appid": game["appid"],
                    "name": game["name"],
                    "window_class": client.get("class", ""),
                    "window_title": title,
                }

    # Check if any non-Steam game-like window exists while Steam is running
    if _is_steam_running():
        for client in clients:
            wclass = client.get("class", "").lower()
            if wclass and wclass not in steam_classes and wclass != "steamwebhelper":
                # Could be a game — report what we see
                pid = client.get("pid", 0)
                if pid:
                    try:
                        # Check if this process is a child of Steam
                        result = subprocess.run(
                            ["ps", "-o", "ppid=", "-p", str(pid)],
                            capture_output=True, text=True, timeout=5,
                        )
                        ppid = result.stdout.strip()
                        steam_pids = subprocess.run(
                            ["pgrep", "steam"],
                            capture_output=True, text=True, timeout=5,
                        )
                        if ppid in steam_pids.stdout.strip().split("\n"):
                            return {
                                "appid": None,
                                "name": client.get("title", wclass),
                                "window_class": client.get("class", ""),
                                "window_title": client.get("title", ""),
                            }
                    except (subprocess.SubprocessError, FileNotFoundError):
                        pass

    return None


def _check_downloads() -> list[dict]:
    """Check for active downloads by examining StateFlags in ACF files.

    StateFlags is a bitmask:
        1 = Invalid
        2 = Uninstalled
        4 = Fully installed
        16 = Update required
        32 = Downloading (update)
        64 = Downloading (content)
        512 = Staged (ready to install update)
        1024 = Downloading
    """
    if not STEAMAPPS.is_dir():
        return []

    downloading = []
    for acf in STEAMAPPS.glob("appmanifest_*.acf"):
        data = _read_acf(acf)
        if data is None:
            continue
        flags = int(data.get("StateFlags", "0"))
        # Not fully installed (4) or has download/update flags
        if flags & (16 | 32 | 64 | 1024):
            to_download = int(data.get("BytesToDownload", "0"))
            downloaded = int(data.get("BytesDownloaded", "0"))
            to_stage = int(data.get("BytesToStage", "0"))
            staged = int(data.get("BytesStaged", "0"))

            progress = None
            if to_download > 0:
                progress = round(downloaded / to_download * 100, 1)

            downloading.append({
                "appid": data.get("appid", ""),
                "name": data.get("name", ""),
                "state_flags": flags,
                "bytes_to_download": to_download,
                "bytes_downloaded": downloaded,
                "bytes_to_stage": to_stage,
                "bytes_staged": staged,
                "progress_pct": progress,
            })

    return downloading


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """CLI-Anything Steam — deterministic access to Steam library and game state."""
    pass


@cli.group()
def library():
    """Steam game library commands."""
    pass


@library.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def library_list(as_json):
    """List all installed Steam games."""
    if not _steam_installed():
        click.echo(json.dumps({"error": "Steam not installed", "games": [], "count": 0}))
        sys.exit(1)

    games = _list_installed_games()
    if as_json:
        click.echo(json.dumps({"games": games, "count": len(games)}))
    else:
        for g in games:
            click.echo(f"[{g['appid']}] {g['name']} ({g['size_human']})")


@library.command("count")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def library_count(as_json):
    """Count installed Steam games."""
    if not _steam_installed():
        click.echo(json.dumps({"error": "Steam not installed", "count": 0}))
        sys.exit(1)

    games = _list_installed_games()
    if as_json:
        click.echo(json.dumps({"count": len(games)}))
    else:
        click.echo(str(len(games)))


@cli.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def status(as_json):
    """Check if Steam is running and what game is active."""
    installed = _steam_installed()
    running = _is_steam_running() if installed else False
    current_game = _detect_running_game() if running else None

    result = {
        "installed": installed,
        "running": running,
        "current_game": current_game,
    }
    if as_json:
        click.echo(json.dumps(result))
    else:
        click.echo(f"Installed: {installed}")
        click.echo(f"Running: {running}")
        if current_game:
            click.echo(f"Playing: {current_game['name']}")


@cli.group()
def game():
    """Individual game commands."""
    pass


@game.command("info")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--appid", required=True, type=str, help="Steam App ID")
def game_info(as_json, appid):
    """Show details for a specific game by App ID."""
    if not _steam_installed():
        click.echo(json.dumps({"error": "Steam not installed"}))
        sys.exit(1)

    acf_path = STEAMAPPS / f"appmanifest_{appid}.acf"
    if not acf_path.exists():
        click.echo(json.dumps({"error": f"Game {appid} not found", "appid": appid}))
        sys.exit(1)

    data = _read_acf(acf_path)
    if data is None:
        click.echo(json.dumps({"error": f"Failed to parse manifest for {appid}"}))
        sys.exit(1)

    size_bytes = int(data.get("SizeOnDisk", "0"))
    install_path = STEAMAPPS / "common" / data.get("installdir", "")

    result = {
        "appid": data.get("appid", ""),
        "name": data.get("name", ""),
        "installdir": data.get("installdir", ""),
        "install_path": str(install_path),
        "size_bytes": size_bytes,
        "size_human": _human_size(size_bytes),
        "last_played": int(data.get("LastPlayed", "0")) or None,
        "last_updated": int(data.get("LastUpdated", "0")) or None,
        "state_flags": int(data.get("StateFlags", "0")),
        "build_id": data.get("buildid", ""),
        "installed_depots": data.get("InstalledDepots", {}),
        "user_config": data.get("UserConfig", {}),
    }

    if as_json:
        click.echo(json.dumps(result))
    else:
        click.echo(f"Name: {result['name']}")
        click.echo(f"App ID: {result['appid']}")
        click.echo(f"Install dir: {result['install_path']}")
        click.echo(f"Size: {result['size_human']}")
        click.echo(f"Build: {result['build_id']}")


@cli.command("running")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def running(as_json):
    """Detect currently running game."""
    if not _is_steam_running():
        result = {"running": False, "game": None}
    else:
        game = _detect_running_game()
        result = {"running": True, "game": game}

    if as_json:
        click.echo(json.dumps(result))
    else:
        if result["game"]:
            click.echo(f"Playing: {result['game']['name']}")
        elif result["running"]:
            click.echo("Steam is running, no game detected")
        else:
            click.echo("Steam is not running")


@cli.command("downloads")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def downloads(as_json):
    """Check active downloads and updates."""
    if not _steam_installed():
        click.echo(json.dumps({"error": "Steam not installed", "downloads": []}))
        sys.exit(1)

    dl = _check_downloads()
    if as_json:
        click.echo(json.dumps({"downloads": dl, "count": len(dl)}))
    else:
        if not dl:
            click.echo("No active downloads")
        else:
            for d in dl:
                pct = f" ({d['progress_pct']}%)" if d["progress_pct"] is not None else ""
                click.echo(f"[{d['appid']}] {d['name']}{pct}")


def main():
    cli()


if __name__ == "__main__":
    main()
