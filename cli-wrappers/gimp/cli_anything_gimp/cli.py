#!/usr/bin/env python3
"""CLI-Anything GIMP — deterministic CLI for GIMP image editor state.

Uses Script-Fu IPC socket for rich queries when GIMP is running with
its server enabled. Falls back to parsing Hyprland window titles and
reading GIMP config/recent files.

Usage:
    cli-anything-gimp status --json
    cli-anything-gimp images list --json
    cli-anything-gimp recent list --json
    cli-anything-gimp tools current --json
    cli-anything-gimp export --json --format png --path /tmp/out.png
"""

import json
import os
import re
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import click


# --- Helpers: Hyprland window parsing ---

def _get_gimp_windows() -> list[dict]:
    """Get GIMP windows from hyprctl clients."""
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
            if c.get("class", "").lower().startswith("gimp")
            or "gimp" in c.get("initialClass", "").lower()
        ]
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return []


def _is_gimp_running() -> bool:
    """Check if GIMP process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "gimp"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _parse_image_from_title(title: str) -> dict | None:
    """Extract image info from a GIMP window title.

    GIMP titles typically look like:
        *filename.xcf-2.0 (RGB color 8-bit gamma, 1920x1080) – GIMP
        filename.png (RGB color 8-bit gamma, 800x600) – GIMP
    The leading * indicates unsaved changes.
    """
    # Match: optional *, filename, optional dimensions/color info
    m = re.match(
        r"^(\*?)(.+?)\s+"
        r"\(([^)]*)\)"
        r"\s*[\u2013\u2014–—-]+\s*GIMP",
        title,
    )
    if not m:
        # Simpler pattern: "filename – GIMP"
        m2 = re.match(r"^(\*?)(.+?)\s*[\u2013\u2014–—-]+\s*GIMP", title)
        if m2:
            return {
                "filename": m2.group(2).strip(),
                "unsaved": m2.group(1) == "*",
                "details": None,
            }
        return None

    details_str = m.group(3)
    info = {
        "filename": m.group(2).strip(),
        "unsaved": m.group(1) == "*",
        "details": details_str,
    }

    # Try to extract dimensions from details like "1920x1080"
    dim = re.search(r"(\d+)\s*[x×]\s*(\d+)", details_str)
    if dim:
        info["width"] = int(dim.group(1))
        info["height"] = int(dim.group(2))

    return info


def _get_open_images() -> list[dict]:
    """Get list of open images from GIMP window titles."""
    windows = _get_gimp_windows()
    images = []
    seen = set()

    for w in windows:
        title = w.get("title", "")
        info = _parse_image_from_title(title)
        if info and info["filename"] not in seen:
            seen.add(info["filename"])
            images.append(info)

    return images


def _get_focused_gimp_window() -> dict | None:
    """Get the currently focused GIMP window, if any."""
    windows = _get_gimp_windows()
    for w in windows:
        if w.get("focusHistoryID", -1) == 0:
            return w
    # Fall back to first window
    return windows[0] if windows else None


# --- Helpers: GIMP config/recent files ---

def _find_gimp_config_dir() -> Path | None:
    """Find GIMP's config directory, checking common version paths."""
    base = Path.home() / ".config" / "GIMP"
    if not base.exists():
        return None

    # Check version dirs in descending order (prefer newer)
    versions = sorted(base.iterdir(), reverse=True)
    for v in versions:
        if v.is_dir() and re.match(r"\d+\.\d+", v.name):
            return v

    # Fall back to the base dir itself
    return base


def _read_recently_used_xbel() -> list[dict]:
    """Read GIMP's recently-used.xbel or the system-wide one."""
    entries = []

    # Try GIMP-specific recent file first
    gimp_dir = _find_gimp_config_dir()
    xbel_paths = []
    if gimp_dir:
        xbel_paths.append(gimp_dir / "recently-used.xbel")

    # Also check the freedesktop recently-used
    xbel_paths.append(Path.home() / ".local" / "share" / "recently-used.xbel")

    for xbel_path in xbel_paths:
        if not xbel_path.exists():
            continue
        try:
            tree = ET.parse(xbel_path)
            root = tree.getroot()

            # Handle both xbel namespaced and plain elements
            ns = {"xbel": "http://www.freedesktop.org/standards/xbel"}
            bookmarks = root.findall(".//bookmark", ns)
            if not bookmarks:
                bookmarks = root.findall(".//bookmark")
            if not bookmarks:
                # Try bare iteration for non-namespaced xbel
                bookmarks = [
                    el for el in root
                    if el.tag.endswith("bookmark") or el.tag == "bookmark"
                ]

            for bm in bookmarks:
                href = bm.get("href", "")
                if not href:
                    continue

                # Filter for image files when reading system-wide xbel
                if xbel_path.name == "recently-used.xbel" and gimp_dir and xbel_path.parent != gimp_dir:
                    # Check if GIMP is listed as an application
                    is_gimp = False
                    for app in bm.iter():
                        if "application" in app.tag.lower():
                            name = app.get("name", "").lower()
                            exec_attr = app.get("exec", "").lower()
                            if "gimp" in name or "gimp" in exec_attr:
                                is_gimp = True
                                break
                    if not is_gimp:
                        continue

                modified = bm.get("modified", "")
                visited = bm.get("visited", "")
                # Decode file URI
                if href.startswith("file://"):
                    filepath = href[7:]
                else:
                    filepath = href

                entries.append({
                    "path": filepath,
                    "filename": Path(filepath).name,
                    "modified": modified,
                    "visited": visited,
                    "uri": href,
                })

        except (ET.ParseError, OSError):
            continue

        # If we got results from GIMP-specific file, prefer those
        if entries and gimp_dir and xbel_path.parent == gimp_dir:
            break

    # Sort by modified date descending
    entries.sort(key=lambda e: e.get("modified", ""), reverse=True)
    return entries


# --- Helpers: Script-Fu IPC ---

def _find_scriptfu_socket() -> str | None:
    """Find GIMP's Script-Fu server socket/port.

    GIMP's Script-Fu console server listens on TCP port 10008 by default
    when started via Filters > Script-Fu > Start Server.
    """
    # Default Script-Fu server port
    port = 10008
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(("127.0.0.1", port))
        sock.close()
        return f"127.0.0.1:{port}"
    except (socket.error, OSError):
        return None


def _send_scriptfu(command: str) -> str | None:
    """Send a Script-Fu command to GIMP's server and return the response."""
    addr = _find_scriptfu_socket()
    if not addr:
        return None

    host, port = addr.split(":")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, int(port)))

        # Script-Fu server protocol: length-prefixed command
        # Header: 1 byte magic (G=0x47), 2 bytes length (big-endian)
        encoded = command.encode("utf-8")
        header = b"G" + len(encoded).to_bytes(2, "big")
        sock.sendall(header + encoded)

        # Read response: 4 bytes header (1 byte error flag, 3 bytes length)
        resp_header = sock.recv(4)
        if len(resp_header) < 4:
            sock.close()
            return None

        error_flag = resp_header[0]
        resp_len = int.from_bytes(resp_header[1:4], "big")
        response = b""
        while len(response) < resp_len:
            chunk = sock.recv(resp_len - len(response))
            if not chunk:
                break
            response += chunk

        sock.close()
        decoded = response.decode("utf-8", errors="replace").strip("\x00").strip()
        if error_flag != 0:
            return None
        return decoded
    except (socket.error, OSError):
        return None


def _scriptfu_available() -> bool:
    """Check if Script-Fu server is reachable."""
    return _find_scriptfu_socket() is not None


def _scriptfu_list_images() -> list[dict] | None:
    """List open images via Script-Fu."""
    result = _send_scriptfu(
        '(let* ((images (gimp-image-list))'
        '       (num (car images))'
        '       (ids (cadr images)))'
        '  (map (lambda (id)'
        '    (list id'
        '          (car (gimp-image-get-filename id))'
        '          (car (gimp-image-width id))'
        '          (car (gimp-image-height id))'
        '          (car (gimp-image-is-dirty id))))'
        '    (vector->list ids)))'
    )
    if not result:
        # Try simpler query
        result = _send_scriptfu("(car (gimp-image-list))")
        if result and result.isdigit():
            count = int(result)
            if count == 0:
                return []
        return None

    # Parse Script-Fu s-expression response
    # This is best-effort; fall back to window parsing if it fails
    try:
        images = []
        # Simple pattern extraction from nested lists
        for m in re.finditer(
            r'\((\d+)\s+"([^"]*)"\s+(\d+)\s+(\d+)\s+(\d+)\)',
            result,
        ):
            images.append({
                "id": int(m.group(1)),
                "filename": m.group(2),
                "width": int(m.group(3)),
                "height": int(m.group(4)),
                "unsaved": m.group(5) != "0",
            })
        return images if images else None
    except (ValueError, AttributeError):
        return None


def _scriptfu_export(image_id: int, path: str, fmt: str) -> bool:
    """Export an image via Script-Fu."""
    path_escaped = path.replace("\\", "\\\\").replace('"', '\\"')

    if fmt == "png":
        cmd = (
            f'(file-png-save RUN-NONINTERACTIVE {image_id} '
            f'(car (gimp-image-get-active-drawable {image_id})) '
            f'"{path_escaped}" "{Path(path).name}" '
            f'0 9 1 1 1 1 1)'
        )
    elif fmt in ("jpg", "jpeg"):
        cmd = (
            f'(file-jpeg-save RUN-NONINTERACTIVE {image_id} '
            f'(car (gimp-image-get-active-drawable {image_id})) '
            f'"{path_escaped}" "{Path(path).name}" '
            f'0.85 0 0 0 "" 0 1 0 2)'
        )
    elif fmt == "webp":
        cmd = (
            f'(file-webp-save RUN-NONINTERACTIVE {image_id} '
            f'(car (gimp-image-get-active-drawable {image_id})) '
            f'"{path_escaped}" "{Path(path).name}" '
            f'0 0 90 1 0 0 0 0 0 0 0 0 1 1)'
        )
    else:
        # Generic export via gimp-file-overwrite
        cmd = (
            f'(gimp-file-overwrite RUN-NONINTERACTIVE {image_id} '
            f'(car (gimp-image-get-active-drawable {image_id})) '
            f'"{path_escaped}" "{Path(path).name}")'
        )

    result = _send_scriptfu(cmd)
    return result is not None


# --- CLI Commands ---

@click.group()
def cli():
    """CLI-Anything GIMP — deterministic image editor state access."""
    pass


@cli.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def status(as_json):
    """Check if GIMP is running and get current image info."""
    running = _is_gimp_running()
    scriptfu = _scriptfu_available() if running else False
    current_image = None

    if running:
        focused = _get_focused_gimp_window()
        if focused:
            info = _parse_image_from_title(focused.get("title", ""))
            if info:
                current_image = info["filename"]

    data = {
        "running": running,
        "scriptfu_available": scriptfu,
        "current_image": current_image,
        "window_count": len(_get_gimp_windows()) if running else 0,
    }

    if as_json:
        click.echo(json.dumps(data))
    else:
        state = "running" if running else "not running"
        click.echo(f"GIMP: {state}")
        if current_image:
            click.echo(f"Current image: {current_image}")
        if scriptfu:
            click.echo("Script-Fu server: available")


@cli.group()
def images():
    """Query open images."""
    pass


@images.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def images_list(as_json):
    """List all open images in GIMP."""
    if not _is_gimp_running():
        data = {"images": [], "count": 0, "error": "GIMP is not running"}
        if as_json:
            click.echo(json.dumps(data))
        else:
            click.echo("GIMP is not running")
        return

    # Try Script-Fu first for richer data
    sf_images = _scriptfu_list_images()
    if sf_images is not None:
        data = {
            "images": sf_images,
            "count": len(sf_images),
            "source": "scriptfu",
        }
    else:
        # Fall back to window title parsing
        img_list = _get_open_images()
        data = {
            "images": img_list,
            "count": len(img_list),
            "source": "window_titles",
        }

    if as_json:
        click.echo(json.dumps(data))
    else:
        for img in data["images"]:
            name = img.get("filename", "unknown")
            dims = ""
            if "width" in img and "height" in img:
                dims = f" ({img['width']}x{img['height']})"
            dirty = " *" if img.get("unsaved") else ""
            click.echo(f"{name}{dims}{dirty}")


@cli.group()
def recent():
    """Recently opened files."""
    pass


@recent.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--limit", default=20, help="Number of entries to show")
def recent_list(as_json, limit):
    """List recently opened files in GIMP."""
    entries = _read_recently_used_xbel()[:limit]
    data = {
        "recent_files": entries,
        "count": len(entries),
    }

    if as_json:
        click.echo(json.dumps(data))
    else:
        for e in entries:
            click.echo(f"{e['filename']} — {e['path']}")


@cli.group()
def tools():
    """Tool state queries."""
    pass


@tools.command("current")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def tools_current(as_json):
    """Detect the current tool in GIMP."""
    if not _is_gimp_running():
        data = {"tool": None, "error": "GIMP is not running"}
        if as_json:
            click.echo(json.dumps(data))
        else:
            click.echo("GIMP is not running")
        return

    tool = None
    source = None

    # Try Script-Fu first
    if _scriptfu_available():
        result = _send_scriptfu("(car (gimp-context-get-paint-method))")
        if result:
            tool = result.strip('"')
            source = "scriptfu"

    # Fall back: read toolrc for last-used tool
    if not tool:
        gimp_dir = _find_gimp_config_dir()
        if gimp_dir:
            toolrc = gimp_dir / "toolrc"
            if toolrc.exists():
                try:
                    content = toolrc.read_text()
                    # toolrc lists tools; the first one is typically active
                    m = re.search(r'\(tool\s+"([^"]+)"', content)
                    if m:
                        tool = m.group(1)
                        source = "toolrc"
                except OSError:
                    pass

    # Fall back: check window titles for tool dialogs
    if not tool:
        windows = _get_gimp_windows()
        for w in windows:
            title = w.get("title", "").lower()
            # GIMP tool option windows often have the tool name
            for t in [
                "paintbrush", "pencil", "eraser", "airbrush", "clone",
                "heal", "smudge", "blur", "sharpen", "dodge", "burn",
                "text", "bucket fill", "gradient", "color picker",
                "measure", "move", "align", "crop", "rotate", "scale",
                "shear", "perspective", "flip", "cage",
                "rectangle select", "ellipse select", "free select",
                "fuzzy select", "by color select", "scissors",
                "foreground select", "paths",
            ]:
                if t in title:
                    tool = t
                    source = "window_title"
                    break
            if tool:
                break

    data = {
        "tool": tool,
        "source": source,
    }

    if as_json:
        click.echo(json.dumps(data))
    else:
        click.echo(tool or "unknown")


@cli.command("export")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--format", "fmt", default="png", help="Export format (png, jpg, webp)")
@click.option("--path", "output_path", required=True, help="Output file path")
def export_image(as_json, fmt, output_path):
    """Export the current image via Script-Fu."""
    if not _is_gimp_running():
        data = {"success": False, "error": "GIMP is not running"}
        if as_json:
            click.echo(json.dumps(data))
        else:
            click.echo("Error: GIMP is not running")
        sys.exit(1)

    if not _scriptfu_available():
        data = {
            "success": False,
            "error": "Script-Fu server not available. "
                     "Start it in GIMP: Filters > Script-Fu > Start Server",
        }
        if as_json:
            click.echo(json.dumps(data))
        else:
            click.echo(f"Error: {data['error']}")
        sys.exit(1)

    # Get the current (active) image ID
    result = _send_scriptfu("(car (gimp-image-list))")
    if not result:
        data = {"success": False, "error": "No images open in GIMP"}
        if as_json:
            click.echo(json.dumps(data))
        else:
            click.echo("Error: No images open")
        sys.exit(1)

    # gimp-image-list returns count first; get actual first image ID
    count_result = _send_scriptfu("(car (gimp-image-list))")
    ids_result = _send_scriptfu("(car (cdr (gimp-image-list)))")

    # Parse image ID — try to get the first image
    image_id = None
    if ids_result:
        m = re.search(r"(\d+)", ids_result)
        if m:
            image_id = int(m.group(1))

    if image_id is None:
        # Fallback: assume image ID 1
        image_id = 1

    output_path = os.path.expanduser(output_path)
    success = _scriptfu_export(image_id, output_path, fmt)

    data = {
        "success": success,
        "path": output_path,
        "format": fmt,
        "image_id": image_id,
    }
    if not success:
        data["error"] = "Export failed — check GIMP Script-Fu console for details"

    if as_json:
        click.echo(json.dumps(data))
    else:
        if success:
            click.echo(f"Exported to {output_path}")
        else:
            click.echo(f"Export failed")
            sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
