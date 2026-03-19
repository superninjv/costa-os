#!/usr/bin/env python3
"""CLI-Anything OBS Studio — deterministic CLI for OBS state.

Uses the obs-websocket 5.x protocol (built into OBS 28+) via raw TCP to query
OBS state. Falls back to reading config files when OBS is not running or the
websocket is unavailable.

Usage:
    cli-anything-obs status --json
    cli-anything-obs scenes list --json
    cli-anything-obs scenes current --json
    cli-anything-obs sources list --json
    cli-anything-obs recording status --json
    cli-anything-obs streaming status --json
"""

import base64
import configparser
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import click


# ---------------------------------------------------------------------------
# obs-websocket 5.x helpers (raw TCP, no external deps)
# ---------------------------------------------------------------------------

OBS_WS_HOST = "localhost"
OBS_WS_PORT = 4455
OBS_WS_TIMEOUT = 3  # seconds


def _ws_handshake(sock: socket.socket, host: str, port: int) -> None:
    """Perform a minimal WebSocket upgrade handshake."""
    import secrets

    key = base64.b64encode(secrets.token_bytes(16)).decode()
    request = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Protocol: obswebsocket.json\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())
    # Read until we see end of HTTP headers
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("WebSocket handshake failed: connection closed")
        response += chunk
    if b"101" not in response.split(b"\r\n")[0]:
        raise ConnectionError(f"WebSocket handshake rejected: {response.split(b'\\r\\n')[0]}")


def _ws_recv_frame(sock: socket.socket) -> bytes:
    """Read a single WebSocket frame and return the payload."""
    header = sock.recv(2)
    if len(header) < 2:
        raise ConnectionError("WebSocket: incomplete frame header")
    payload_len = header[1] & 0x7F
    if payload_len == 126:
        raw = sock.recv(2)
        payload_len = struct.unpack("!H", raw)[0]
    elif payload_len == 127:
        raw = sock.recv(8)
        payload_len = struct.unpack("!Q", raw)[0]
    data = b""
    while len(data) < payload_len:
        chunk = sock.recv(payload_len - len(data))
        if not chunk:
            break
        data += chunk
    return data


def _ws_send_frame(sock: socket.socket, payload: bytes) -> None:
    """Send a masked WebSocket text frame."""
    import secrets

    mask_key = secrets.token_bytes(4)
    header = bytearray()
    header.append(0x81)  # FIN + text opcode
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)  # MASK bit set
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask_key)
    masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + bytes(masked))


def _obs_ws_identify(sock: socket.socket, hello: dict, password: str | None = None) -> dict:
    """Respond to obs-websocket Hello with Identify message."""
    auth = hello.get("d", {}).get("authentication")
    identify_data: dict = {"rpcVersion": 1}

    if auth and password:
        challenge = auth["challenge"]
        salt = auth["salt"]
        # obs-websocket auth: base64(sha256(base64(sha256(password + salt)) + challenge))
        secret = base64.b64encode(
            hashlib.sha256((password + salt).encode()).digest()
        ).decode()
        auth_string = base64.b64encode(
            hashlib.sha256((secret + challenge).encode()).digest()
        ).decode()
        identify_data["authentication"] = auth_string
    elif auth and not password:
        raise ConnectionError("OBS websocket requires authentication but no password provided")

    msg = json.dumps({"op": 1, "d": identify_data})
    _ws_send_frame(sock, msg.encode())
    resp = json.loads(_ws_recv_frame(sock))
    if resp.get("op") != 2:  # Identified
        raise ConnectionError(f"OBS identify failed: {resp}")
    return resp


def _obs_ws_request(sock: socket.socket, request_type: str, request_data: dict | None = None) -> dict:
    """Send an obs-websocket request and return the response data."""
    import secrets

    request_id = secrets.token_hex(8)
    msg: dict = {
        "op": 6,  # Request
        "d": {
            "requestType": request_type,
            "requestId": request_id,
        },
    }
    if request_data:
        msg["d"]["requestData"] = request_data
    _ws_send_frame(sock, json.dumps(msg).encode())

    # Read responses until we get our RequestResponse (op 7)
    for _ in range(20):
        frame_data = _ws_recv_frame(sock)
        resp = json.loads(frame_data)
        if resp.get("op") == 7 and resp.get("d", {}).get("requestId") == request_id:
            return resp.get("d", {}).get("responseData") or {}
    raise TimeoutError(f"No response for {request_type}")


class OBSConnection:
    """Manages a websocket connection to OBS Studio."""

    def __init__(self, host: str = OBS_WS_HOST, port: int = OBS_WS_PORT,
                 password: str | None = None):
        self.host = host
        self.port = port
        self.password = password or os.environ.get("OBS_WEBSOCKET_PASSWORD")
        self.sock: socket.socket | None = None

    def connect(self) -> bool:
        """Connect and authenticate. Returns True on success."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(OBS_WS_TIMEOUT)
            self.sock.connect((self.host, self.port))
            _ws_handshake(self.sock, self.host, self.port)
            # Read Hello (op 0)
            hello = json.loads(_ws_recv_frame(self.sock))
            if hello.get("op") != 0:
                raise ConnectionError(f"Expected Hello, got op {hello.get('op')}")
            _obs_ws_identify(self.sock, hello, self.password)
            return True
        except (ConnectionError, ConnectionRefusedError, TimeoutError, OSError):
            self.close()
            return False

    def request(self, request_type: str, request_data: dict | None = None) -> dict:
        if not self.sock:
            raise ConnectionError("Not connected")
        return _obs_ws_request(self.sock, request_type, request_data)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Config file fallback
# ---------------------------------------------------------------------------

OBS_CONFIG_DIR = Path.home() / ".config" / "obs-studio"


def _obs_is_running() -> bool:
    """Check if OBS is running via process list."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "obs"],
            capture_output=True, timeout=2,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _read_profile_ini() -> configparser.ConfigParser | None:
    """Read the first available OBS profile basic.ini."""
    profiles_dir = OBS_CONFIG_DIR / "basic" / "profiles"
    if not profiles_dir.exists():
        return None
    for profile in profiles_dir.iterdir():
        ini_path = profile / "basic.ini"
        if ini_path.exists():
            config = configparser.ConfigParser()
            config.read(str(ini_path))
            return config
    return None


def _read_scene_collection() -> dict | None:
    """Read the current scene collection JSON."""
    collections_dir = OBS_CONFIG_DIR / "basic" / "scenes"
    if not collections_dir.exists():
        return None
    # Try to find the active collection from global.ini
    global_ini = OBS_CONFIG_DIR / "global.ini"
    active_collection = None
    if global_ini.exists():
        config = configparser.ConfigParser()
        config.read(str(global_ini))
        active_collection = config.get("Basic", "SceneCollection", fallback=None)

    for scene_file in collections_dir.glob("*.json"):
        if active_collection and scene_file.stem != active_collection:
            continue
        try:
            return json.loads(scene_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

    # If active collection not found, try any JSON file
    for scene_file in collections_dir.glob("*.json"):
        try:
            return json.loads(scene_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _scenes_from_config() -> list[dict]:
    """Extract scene list from config files."""
    collection = _read_scene_collection()
    if not collection:
        return []
    scenes = []
    for scene in collection.get("sources", []):
        if scene.get("id") == "scene":
            scenes.append({
                "name": scene.get("name", ""),
                "index": len(scenes),
            })
    # Also check top-level "scene_order" if present
    if not scenes and "scene_order" in collection:
        for i, s in enumerate(collection["scene_order"]):
            scenes.append({"name": s.get("name", ""), "index": i})
    return scenes


def _current_scene_from_config() -> str | None:
    """Get the current scene name from config."""
    collection = _read_scene_collection()
    if not collection:
        return None
    return collection.get("current_scene")


def _sources_from_config(scene_name: str | None = None) -> list[dict]:
    """Extract sources for a scene from config files."""
    collection = _read_scene_collection()
    if not collection:
        return []
    target = scene_name or collection.get("current_scene")
    sources = []
    for item in collection.get("sources", []):
        if item.get("id") == "scene" and item.get("name") == target:
            # Scene found; extract its child sources from settings.items
            settings = item.get("settings", {})
            for child in settings.get("items", []):
                sources.append({
                    "name": child.get("name", ""),
                    "type": child.get("id", "unknown"),
                    "visible": child.get("visible", True),
                })
            break
    # Fallback: list all non-scene sources
    if not sources:
        for item in collection.get("sources", []):
            if item.get("id") != "scene":
                sources.append({
                    "name": item.get("name", ""),
                    "type": item.get("id", "unknown"),
                    "visible": True,
                })
    return sources


def _recording_path_from_config() -> str | None:
    """Get the configured recording output path."""
    profile = _read_profile_ini()
    if not profile:
        return None
    return profile.get("SimpleOutput", "FilePath", fallback=None) or \
        profile.get("AdvOut", "RecFilePath", fallback=None)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _output(data: dict, as_json: bool):
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for k, v in data.items():
            click.echo(f"{k}: {v}")


def _error(msg: str, as_json: bool):
    if as_json:
        click.echo(json.dumps({"error": msg}))
    else:
        click.echo(f"Error: {msg}", err=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """CLI-Anything OBS Studio — deterministic OBS state access."""
    pass


@cli.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--password", envvar="OBS_WEBSOCKET_PASSWORD", default=None, help="Websocket password")
def status(as_json, password):
    """Overall OBS status: recording/streaming state, scene, FPS, dropped frames."""
    conn = OBSConnection(password=password)
    if conn.connect():
        try:
            stats = conn.request("GetStats")
            stream = conn.request("GetStreamStatus")
            record = conn.request("GetRecordStatus")
            scene = conn.request("GetCurrentProgramScene")
            data = {
                "running": True,
                "websocket": True,
                "currentScene": scene.get("currentProgramSceneName", ""),
                "fps": stats.get("activeFps", 0),
                "renderTotalFrames": stats.get("renderTotalFrames", 0),
                "renderSkippedFrames": stats.get("renderSkippedFrames", 0),
                "outputTotalFrames": stats.get("outputTotalFrames", 0),
                "outputSkippedFrames": stats.get("outputSkippedFrames", 0),
                "cpuUsage": stats.get("cpuUsage", 0),
                "memoryUsage": stats.get("memoryUsage", 0),
                "recording": record.get("outputActive", False),
                "recordingDuration": record.get("outputTimecode", "00:00:00"),
                "streaming": stream.get("outputActive", False),
                "streamingDuration": stream.get("outputTimecode", "00:00:00"),
            }
            _output(data, as_json)
        finally:
            conn.close()
    else:
        # Fallback to config
        running = _obs_is_running()
        current = _current_scene_from_config()
        data = {
            "running": running,
            "websocket": False,
            "currentScene": current or "(unknown)",
            "fps": "(unavailable — websocket not connected)",
            "renderSkippedFrames": "(unavailable)",
            "outputSkippedFrames": "(unavailable)",
            "recording": "(unavailable — websocket not connected)",
            "streaming": "(unavailable — websocket not connected)",
            "note": "OBS websocket not available. Live stats require OBS running with websocket enabled on port 4455.",
        }
        _output(data, as_json)


# --- Scenes ---

@cli.group()
def scenes():
    """Scene management."""
    pass


@scenes.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--password", envvar="OBS_WEBSOCKET_PASSWORD", default=None)
def scenes_list(as_json, password):
    """List all scenes."""
    conn = OBSConnection(password=password)
    if conn.connect():
        try:
            resp = conn.request("GetSceneList")
            scene_list = [
                {"name": s.get("sceneName", ""), "index": s.get("sceneIndex", i)}
                for i, s in enumerate(resp.get("scenes", []))
            ]
            current = resp.get("currentProgramSceneName", "")
            _output({"scenes": scene_list, "currentScene": current, "count": len(scene_list)}, as_json)
        finally:
            conn.close()
    else:
        scene_list = _scenes_from_config()
        current = _current_scene_from_config()
        _output({
            "scenes": scene_list,
            "currentScene": current or "(unknown)",
            "count": len(scene_list),
            "source": "config_file",
        }, as_json)


@scenes.command("current")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--password", envvar="OBS_WEBSOCKET_PASSWORD", default=None)
def scenes_current(as_json, password):
    """Show the current active scene."""
    conn = OBSConnection(password=password)
    if conn.connect():
        try:
            resp = conn.request("GetCurrentProgramScene")
            _output({"currentScene": resp.get("currentProgramSceneName", "")}, as_json)
        finally:
            conn.close()
    else:
        current = _current_scene_from_config()
        _output({
            "currentScene": current or "(unknown)",
            "source": "config_file",
        }, as_json)


# --- Sources ---

@cli.group()
def sources():
    """Source management."""
    pass


@sources.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--password", envvar="OBS_WEBSOCKET_PASSWORD", default=None)
def sources_list(as_json, password):
    """List sources in the current scene."""
    conn = OBSConnection(password=password)
    if conn.connect():
        try:
            scene_resp = conn.request("GetCurrentProgramScene")
            scene_name = scene_resp.get("currentProgramSceneName", "")
            items_resp = conn.request("GetSceneItemList", {"sceneName": scene_name})
            source_list = [
                {
                    "name": item.get("sourceName", ""),
                    "type": item.get("inputKind", item.get("sourceType", "unknown")),
                    "id": item.get("sceneItemId"),
                    "visible": item.get("sceneItemEnabled", True),
                }
                for item in items_resp.get("sceneItems", [])
            ]
            _output({
                "scene": scene_name,
                "sources": source_list,
                "count": len(source_list),
            }, as_json)
        finally:
            conn.close()
    else:
        current = _current_scene_from_config()
        source_list = _sources_from_config(current)
        _output({
            "scene": current or "(unknown)",
            "sources": source_list,
            "count": len(source_list),
            "source": "config_file",
        }, as_json)


# --- Recording ---

@cli.group()
def recording():
    """Recording state."""
    pass


@recording.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--password", envvar="OBS_WEBSOCKET_PASSWORD", default=None)
def recording_status(as_json, password):
    """Show recording status: active, duration, output path."""
    conn = OBSConnection(password=password)
    if conn.connect():
        try:
            resp = conn.request("GetRecordStatus")
            output_path = _recording_path_from_config()
            data = {
                "active": resp.get("outputActive", False),
                "paused": resp.get("outputPaused", False),
                "duration": resp.get("outputTimecode", "00:00:00"),
                "bytes": resp.get("outputBytes", 0),
                "outputPath": output_path or "(check OBS settings)",
            }
            _output(data, as_json)
        finally:
            conn.close()
    else:
        output_path = _recording_path_from_config()
        data = {
            "active": "(unavailable — websocket not connected)",
            "paused": "(unavailable)",
            "duration": "(unavailable)",
            "outputPath": output_path or "(not found in config)",
            "note": "Live recording status requires OBS running with websocket enabled.",
        }
        _output(data, as_json)


# --- Streaming ---

@cli.group()
def streaming():
    """Streaming state."""
    pass


@streaming.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--password", envvar="OBS_WEBSOCKET_PASSWORD", default=None)
def streaming_status(as_json, password):
    """Show streaming status: active, duration, viewer count if available."""
    conn = OBSConnection(password=password)
    if conn.connect():
        try:
            resp = conn.request("GetStreamStatus")
            data = {
                "active": resp.get("outputActive", False),
                "reconnecting": resp.get("outputReconnecting", False),
                "duration": resp.get("outputTimecode", "00:00:00"),
                "congestion": resp.get("outputCongestion", 0),
                "bytes": resp.get("outputBytes", 0),
                "skippedFrames": resp.get("outputSkippedFrames", 0),
                "totalFrames": resp.get("outputTotalFrames", 0),
            }
            _output(data, as_json)
        finally:
            conn.close()
    else:
        data = {
            "active": "(unavailable — websocket not connected)",
            "duration": "(unavailable)",
            "note": "Live streaming status requires OBS running with websocket enabled.",
        }
        _output(data, as_json)


def main():
    cli()


if __name__ == "__main__":
    main()
