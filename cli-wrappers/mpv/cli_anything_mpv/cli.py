"""CLI-Anything MPV wrapper — IPC socket primary, playerctl fallback."""

import json
import os
import socket
import subprocess
import sys

import click

DEFAULT_SOCKET = "/tmp/mpvsocket"


# ---------------------------------------------------------------------------
# IPC helpers
# ---------------------------------------------------------------------------

def _get_socket_path() -> str:
    """Return the MPV IPC socket path (env override or default)."""
    return os.environ.get("MPV_SOCKET", DEFAULT_SOCKET)


def _ipc_command(command: list, socket_path: str | None = None) -> dict:
    """Send a JSON command to MPV's IPC socket and return the parsed response.

    Raises ConnectionError when the socket is unreachable (MPV not running or
    socket not configured).
    """
    path = socket_path or _get_socket_path()

    if not os.path.exists(path):
        raise ConnectionError(f"MPV IPC socket not found at {path}")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(path)
        payload = json.dumps({"command": command}) + "\n"
        sock.sendall(payload.encode())

        # Read until we get a complete JSON line (MPV sends newline-delimited JSON).
        buf = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
    finally:
        sock.close()

    # MPV may emit event lines before the response; take the last complete line
    # that parses as a response (has "error" key).
    for line in reversed(buf.strip().split(b"\n")):
        try:
            data = json.loads(line)
            if "error" in data:
                return data
        except json.JSONDecodeError:
            continue

    raise ConnectionError("No valid response from MPV IPC socket")


def _get_property(name: str, socket_path: str | None = None):
    """Get a single MPV property via IPC. Returns the value or None on error."""
    try:
        resp = _ipc_command(["get_property", name], socket_path)
        if resp.get("error") == "success":
            return resp.get("data")
    except (ConnectionError, OSError):
        pass
    return None


def _get_properties(names: list[str], socket_path: str | None = None) -> dict:
    """Get multiple properties, returning a dict of name -> value (None on failure)."""
    result = {}
    for name in names:
        result[name] = _get_property(name, socket_path)
    return result


# ---------------------------------------------------------------------------
# playerctl fallback helpers
# ---------------------------------------------------------------------------

def _playerctl(*args: str) -> str | None:
    """Run a playerctl command targeting mpv. Returns stdout or None."""
    try:
        proc = subprocess.run(
            ["playerctl", "-p", "mpv", *args],
            capture_output=True, text=True, timeout=3,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _mpv_running_via_playerctl() -> bool:
    """Check if mpv shows up in playerctl players."""
    result = _playerctl("status")
    return result is not None


def _status_via_playerctl() -> dict | None:
    """Gather status info via playerctl as fallback."""
    status = _playerctl("status")
    if status is None:
        return None

    metadata_fmt = (
        "{{artist}}\n{{title}}\n{{album}}\n"
        "{{mpris:length}}\n{{volume}}"
    )
    meta_raw = _playerctl("metadata", "--format", metadata_fmt)
    position_raw = _playerctl("position")

    artist, title, album, length_us, volume = "", "", "", "", ""
    if meta_raw:
        parts = meta_raw.split("\n")
        artist = parts[0] if len(parts) > 0 else ""
        title = parts[1] if len(parts) > 1 else ""
        album = parts[2] if len(parts) > 2 else ""
        length_us = parts[3] if len(parts) > 3 else ""
        volume = parts[4] if len(parts) > 4 else ""

    # Convert microseconds to seconds
    duration = None
    if length_us and length_us.isdigit():
        duration = int(length_us) / 1_000_000

    position = None
    if position_raw:
        try:
            position = float(position_raw)
        except ValueError:
            pass

    vol = None
    if volume:
        try:
            vol = float(volume) * 100  # playerctl returns 0.0-1.0
        except ValueError:
            pass

    return {
        "state": status.lower(),  # Playing -> playing, Paused -> paused, Stopped -> stopped
        "filename": title or None,
        "title": title or None,
        "artist": artist or None,
        "album": album or None,
        "position": position,
        "duration": duration,
        "volume": vol,
        "source": "playerctl",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def main():
    """CLI-Anything wrapper for MPV media player."""


@main.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def status(as_json: bool):
    """Playback state, current file, position, duration, volume."""
    # Try IPC socket first
    props = _get_properties([
        "pause", "filename", "media-title", "time-pos",
        "duration", "volume", "idle-active", "path",
    ])

    ipc_available = props.get("filename") is not None or props.get("idle-active") is not None

    if ipc_available:
        if props.get("idle-active"):
            state = "idle"
        elif props.get("pause"):
            state = "paused"
        else:
            state = "playing"

        result = {
            "state": state,
            "filename": props.get("filename"),
            "path": props.get("path"),
            "title": props.get("media-title"),
            "position": props.get("time-pos"),
            "duration": props.get("duration"),
            "volume": props.get("volume"),
            "source": "ipc",
        }
    else:
        # Fallback to playerctl
        result = _status_via_playerctl()
        if result is None:
            result = {"error": "mpv is not running", "state": "stopped", "source": "none"}

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if result.get("error"):
            click.echo(f"MPV: not running")
        else:
            click.echo(f"State:    {result['state']}")
            click.echo(f"File:     {result.get('filename') or 'N/A'}")
            if result.get("title"):
                click.echo(f"Title:    {result['title']}")
            pos = result.get("position")
            dur = result.get("duration")
            if pos is not None and dur is not None:
                click.echo(f"Position: {_fmt_time(pos)} / {_fmt_time(dur)}")
            if result.get("volume") is not None:
                click.echo(f"Volume:   {result['volume']:.0f}%")
            click.echo(f"Source:   {result['source']}")


@main.command("now-playing")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def now_playing(as_json: bool):
    """Current media: filename, title from metadata if available."""
    props = _get_properties([
        "filename", "media-title", "metadata", "path",
    ])

    ipc_available = props.get("filename") is not None

    if ipc_available:
        metadata = props.get("metadata") or {}
        result = {
            "filename": props.get("filename"),
            "path": props.get("path"),
            "title": props.get("media-title"),
            "metadata": metadata if isinstance(metadata, dict) else {},
            "source": "ipc",
        }
    else:
        # playerctl fallback
        fallback = _status_via_playerctl()
        if fallback:
            result = {
                "filename": fallback.get("filename"),
                "path": None,
                "title": fallback.get("title"),
                "metadata": {
                    k: v for k, v in {
                        "artist": fallback.get("artist"),
                        "album": fallback.get("album"),
                    }.items() if v
                },
                "source": "playerctl",
            }
        else:
            result = {"error": "mpv is not running", "source": "none"}

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if result.get("error"):
            click.echo("MPV: not running")
        else:
            click.echo(f"File:     {result.get('filename') or 'N/A'}")
            if result.get("title"):
                click.echo(f"Title:    {result['title']}")
            if result.get("path"):
                click.echo(f"Path:     {result['path']}")
            meta = result.get("metadata", {})
            for k, v in meta.items():
                click.echo(f"  {k}: {v}")
            click.echo(f"Source:   {result['source']}")


@main.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def playlist(as_json: bool):
    """Current playlist contents (via IPC socket)."""
    count = _get_property("playlist-count")

    if count is None:
        # No IPC - can't get playlist from playerctl
        result = {"error": "mpv IPC socket not available (playlist requires IPC)", "entries": []}
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("MPV: IPC socket not available (playlist requires direct socket connection)")
        return

    entries = []
    current_pos = _get_property("playlist-pos") or 0

    for i in range(count):
        filename = _get_property(f"playlist/{i}/filename")
        title = _get_property(f"playlist/{i}/title")
        entries.append({
            "index": i,
            "filename": filename,
            "title": title,
            "current": i == current_pos,
        })

    result = {
        "count": count,
        "position": current_pos,
        "entries": entries,
        "source": "ipc",
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        if not entries:
            click.echo("Playlist: empty")
        else:
            click.echo(f"Playlist ({count} items):")
            for e in entries:
                marker = " >> " if e["current"] else "    "
                name = e.get("title") or e.get("filename") or "?"
                click.echo(f"{marker}{e['index']:3d}. {name}")


@main.group()
def properties():
    """Query arbitrary MPV properties."""


@properties.command("get")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
@click.option("--name", required=True, help="MPV property name (e.g. volume, pause, filename)")
def properties_get(as_json: bool, name: str):
    """Get any MPV property via IPC socket."""
    try:
        resp = _ipc_command(["get_property", name])
    except ConnectionError as e:
        result = {"error": str(e), "property": name, "value": None}
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Error: {e}")
        sys.exit(1)

    if resp.get("error") == "success":
        value = resp.get("data")
        result = {"property": name, "value": value, "source": "ipc"}
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"{name} = {value}")
    else:
        err_msg = resp.get("error", "unknown error")
        result = {"error": err_msg, "property": name, "value": None}
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Error getting '{name}': {err_msg}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _fmt_time(seconds: float | None) -> str:
    """Format seconds as H:MM:SS or M:SS."""
    if seconds is None:
        return "?"
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


if __name__ == "__main__":
    main()
