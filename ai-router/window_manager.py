"""Natural Language Window Management for Costa OS.

Translates natural language queries into hyprctl dispatch commands.
Uses pattern matching for common requests, falls back to Ollama for complex ones.

Usage:
    from window_manager import execute_window_command
    result = execute_window_command("put my editor on the left and browser on the right")
"""

import subprocess
import json
import re
import os
from pathlib import Path


def _run(cmd: str | list[str], timeout: int = 5) -> str:
    """Run a command and return stdout.

    Accepts list (no shell) or string (shell=True). Prefer list form.
    """
    try:
        if isinstance(cmd, list):
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        else:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
        return result.stdout.strip()
    except Exception:
        return ""


def _run_hyprctl(args: str, timeout: int = 5) -> str:
    """Run a hyprctl command and return output."""
    return _run(["hyprctl"] + args.split(), timeout=timeout)


def _get_clients() -> list[dict]:
    """Get all window clients as a list of dicts."""
    raw = _run_hyprctl("clients -j")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _get_monitors() -> list[dict]:
    """Get monitor layout as a list of dicts."""
    raw = _run_hyprctl("monitors -j")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _get_active_window() -> dict | None:
    """Get the currently focused window."""
    raw = _run_hyprctl("activewindow -j")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _get_active_workspace() -> dict | None:
    """Get the currently focused workspace."""
    raw = _run_hyprctl("activeworkspace -j")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _dispatch(cmd: str) -> str:
    """Run a hyprctl dispatch command."""
    return _run_hyprctl(f"dispatch {cmd}")


def _dispatch_batch(commands: list[str]) -> list[str]:
    """Run multiple dispatch commands and return results."""
    results = []
    for cmd in commands:
        results.append(_dispatch(cmd))
    return results


def _find_window(identifier: str, clients: list[dict]) -> dict | None:
    """Find a window by class name, title substring, or address.

    Matches case-insensitively against common app names and aliases.
    """
    ident = identifier.lower().strip()

    # Common aliases
    aliases = {
        "editor": ["code", "code-oss", "vscodium", "neovim", "vim", "emacs", "kate"],
        "browser": ["firefox", "chromium", "chrome", "brave", "librewolf", "zen"],
        "terminal": ["ghostty", "kitty", "alacritty", "foot", "wezterm", "konsole"],
        "file manager": ["nautilus", "thunar", "dolphin", "nemo", "pcmanfm"],
        "files": ["nautilus", "thunar", "dolphin", "nemo", "pcmanfm"],
        "music": ["spotify", "rhythmbox", "lollypop", "cmus"],
        "discord": ["discord", "webcord", "vesktop"],
        "steam": ["steam"],
    }

    # Expand aliases
    search_terms = [ident]
    if ident in aliases:
        search_terms = aliases[ident]

    # Search by class name first (most reliable), then title
    for client in clients:
        cls = client.get("class", "").lower()
        title = client.get("title", "").lower()
        for term in search_terms:
            if term in cls:
                return client
    for client in clients:
        title = client.get("title", "").lower()
        for term in search_terms:
            if term in title:
                return client
    return None


def _get_costa_ai_address(clients: list[dict]) -> str | None:
    """Find the address of the terminal running costa-ai so we never close it."""
    active = _get_active_window()
    if active:
        cls = active.get("class", "").lower()
        if cls in ("ghostty", "kitty", "alacritty", "foot", "wezterm", "konsole"):
            return active.get("address")
    return None


def _get_focused_monitor(monitors: list[dict]) -> dict | None:
    """Get the focused monitor."""
    for m in monitors:
        if m.get("focused"):
            return m
    return None


# --- Pattern-based command handlers ---

def _handle_fullscreen(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle fullscreen requests."""
    m = re.search(r"(?:make|toggle|set)\s+(?:this\s+)?(?:window\s+)?(?:to\s+)?(?:full\s*screen|maximized?)", query, re.I)
    if not m and not re.search(r"full\s*screen", query, re.I):
        return None

    # Check if asking to exit fullscreen
    if re.search(r"(exit|leave|stop|unfull|un-full|disable)\s*(full\s*screen)?", query, re.I):
        result = _dispatch("fullscreen 0")
        return {"action": "exit_fullscreen", "commands_run": ["fullscreen 0"], "result": result}

    result = _dispatch("fullscreen 0")
    return {"action": "fullscreen", "commands_run": ["fullscreen 0"], "result": result}


def _handle_floating(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle floating/tiling toggle."""
    if not re.search(r"(float|tile|tiling|toggle\s*float)", query, re.I):
        return None

    if re.search(r"(make|set).*til(e|ing)", query, re.I) or re.search(r"unfloat", query, re.I):
        result = _dispatch("settiled")
        return {"action": "set_tiled", "commands_run": ["settiled"], "result": result}

    if re.search(r"(toggle\s*float|float.*toggle)", query, re.I):
        result = _dispatch("togglefloating")
        return {"action": "toggle_floating", "commands_run": ["togglefloating"], "result": result}

    if re.search(r"(make|set).*float", query, re.I):
        result = _dispatch("togglefloating")
        return {"action": "toggle_floating", "commands_run": ["togglefloating"], "result": result}

    return None


def _handle_move_to_workspace(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle moving windows to workspaces."""
    # "move X to workspace N" or "move X to N" or "send X to workspace N"
    m = re.search(
        r"(?:move|send|put)\s+(.+?)\s+to\s+(?:workspace\s+)?(\d+)",
        query, re.I
    )
    if not m:
        return None

    target_name = m.group(1).strip()
    workspace_num = m.group(2)

    # "this" / "this window" / "the focused window"
    if re.match(r"(this|the\s+focused|current|it)\b", target_name, re.I):
        result = _dispatch(f"movetoworkspace {workspace_num}")
        return {
            "action": "move_to_workspace",
            "commands_run": [f"movetoworkspace {workspace_num}"],
            "result": result,
        }

    window = _find_window(target_name, clients)
    if window:
        addr = window["address"]
        result = _dispatch(f"movetoworkspacesilent {workspace_num},address:{addr}")
        return {
            "action": "move_to_workspace",
            "commands_run": [f"movetoworkspacesilent {workspace_num},address:{addr}"],
            "result": result,
        }

    return {"action": "move_to_workspace", "commands_run": [], "result": f"Could not find window matching '{target_name}'"}


def _handle_focus_workspace(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle switching to a workspace."""
    m = re.search(r"(?:switch|go|jump)\s+to\s+(?:workspace\s+)?(\d+)", query, re.I)
    if not m:
        m = re.search(r"(?:workspace)\s+(\d+)", query, re.I)
    if not m:
        return None

    ws = m.group(1)
    result = _dispatch(f"workspace {ws}")
    return {"action": "focus_workspace", "commands_run": [f"workspace {ws}"], "result": result}


def _handle_split_layout(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle 'put X on the left and Y on the right' type requests."""
    m = re.search(
        r"(?:put|place|move|set)\s+(?:my\s+)?(.+?)\s+(?:on\s+)?(?:the\s+)?(?:left|first)\s+"
        r"(?:and|,)\s+(?:my\s+)?(.+?)\s+(?:on\s+)?(?:the\s+)?(?:right|second)",
        query, re.I
    )
    if not m:
        return None

    left_name = m.group(1).strip()
    right_name = m.group(2).strip()

    left_win = _find_window(left_name, clients)
    right_win = _find_window(right_name, clients)

    if not left_win:
        return {"action": "split_layout", "commands_run": [], "result": f"Could not find window matching '{left_name}'"}
    if not right_win:
        return {"action": "split_layout", "commands_run": [], "result": f"Could not find window matching '{right_name}'"}

    left_addr = left_win["address"]
    right_addr = right_win["address"]

    # Use Hyprland tiling — move both to current workspace, ensure tiled,
    # then arrange with focus/swap so left is left and right is right
    active_ws = _get_active_workspace()
    ws_id = active_ws["id"] if active_ws else 1

    commands = [
        # Ensure both are on the active workspace and tiled (not floating)
        f"movetoworkspacesilent {ws_id},address:{left_addr}",
        f"movetoworkspacesilent {ws_id},address:{right_addr}",
        f"settiled address:{left_addr}",
        f"settiled address:{right_addr}",
        # Focus left window first so it takes the left position
        f"focuswindow address:{left_addr}",
        # Swap right window next to it
        f"focuswindow address:{right_addr}",
    ]

    _dispatch_batch(commands)
    return {
        "action": "split_layout",
        "commands_run": commands,
        "result": f"Tiled {left_name} and {right_name} side by side",
    }


def _handle_tile_all(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle 'tile everything' / 'tile all windows'."""
    if not re.search(r"tile\s+(everything|all|every\s+window|windows)", query, re.I):
        return None

    commands = []
    active_ws = _get_active_workspace()
    ws_id = active_ws["id"] if active_ws else 1

    for client in clients:
        if client.get("workspace", {}).get("id") == ws_id and client.get("floating"):
            addr = client["address"]
            commands.append(f"settiled address:{addr}")

    if not commands:
        return {"action": "tile_all", "commands_run": [], "result": "No floating windows to tile"}

    results = _dispatch_batch(commands)
    return {
        "action": "tile_all",
        "commands_run": commands,
        "result": f"Tiled {len(commands)} window(s)",
    }


def _handle_close(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle close window requests, with safety for costa-ai."""
    # "close all terminals except the focused one"
    m_except = re.search(
        r"close\s+(?:all\s+)?(.+?)\s+(?:except|but\s+not|other\s+than)\s+(?:the\s+)?(?:focused|current|this)\s*(?:one)?",
        query, re.I
    )
    if m_except:
        target_class = m_except.group(1).strip().rstrip("s")  # "terminals" -> "terminal"
        active = _get_active_window()
        active_addr = active.get("address") if active else None
        costa_addr = _get_costa_ai_address(clients)

        commands = []
        for client in clients:
            win = _find_window(target_class, [client])
            if win and win["address"] != active_addr:
                # Safety: never close the window running costa-ai
                if costa_addr and win["address"] == costa_addr:
                    continue
                commands.append(f"closewindow address:{win['address']}")

        if not commands:
            return {"action": "close_except", "commands_run": [], "result": "No matching windows to close"}
        _dispatch_batch(commands)
        return {
            "action": "close_except",
            "commands_run": commands,
            "result": f"Closed {len(commands)} window(s)",
        }

    # "close X" / "close this window"
    m_close = re.search(r"close\s+(?:the\s+)?(.+?)(?:\s+window)?$", query, re.I)
    if m_close:
        target = m_close.group(1).strip()
        if re.match(r"(this|the\s+focused|current|it)$", target, re.I):
            active = _get_active_window()
            if active:
                costa_addr = _get_costa_ai_address(clients)
                if costa_addr and active.get("address") == costa_addr:
                    return {"action": "close", "commands_run": [], "result": "Refusing to close the terminal running costa-ai"}
                result = _dispatch("killactive")
                return {"action": "close", "commands_run": ["killactive"], "result": result}
        else:
            window = _find_window(target, clients)
            if window:
                costa_addr = _get_costa_ai_address(clients)
                if costa_addr and window.get("address") == costa_addr:
                    return {"action": "close", "commands_run": [], "result": "Refusing to close the terminal running costa-ai"}
                addr = window["address"]
                result = _dispatch(f"closewindow address:{addr}")
                return {"action": "close", "commands_run": [f"closewindow address:{addr}"], "result": result}
            return {"action": "close", "commands_run": [], "result": f"Could not find window matching '{target}'"}

    return None


def _handle_swap(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle swapping two windows."""
    # "swap these two windows" / "swap X and Y"
    if not re.search(r"swap", query, re.I):
        return None

    # "swap these two windows" / "swap the two windows"
    if re.search(r"swap\s+(?:these|the)\s+(?:two\s+)?windows", query, re.I):
        # Swap active window with the next one in layout
        result = _dispatch("swapnext")
        return {"action": "swap", "commands_run": ["swapnext"], "result": result}

    # "swap X and Y"
    m = re.search(r"swap\s+(?:my\s+)?(.+?)\s+(?:and|with)\s+(?:my\s+)?(.+?)$", query, re.I)
    if m:
        name_a = m.group(1).strip()
        name_b = m.group(2).strip()
        win_a = _find_window(name_a, clients)
        win_b = _find_window(name_b, clients)

        if not win_a:
            return {"action": "swap", "commands_run": [], "result": f"Could not find window matching '{name_a}'"}
        if not win_b:
            return {"action": "swap", "commands_run": [], "result": f"Could not find window matching '{name_b}'"}

        addr_a = win_a["address"]
        addr_b = win_b["address"]
        commands = [
            f"focuswindow address:{addr_a}",
            f"swapwindow address:{addr_b}",
        ]
        # hyprctl swapwindow doesn't take address — use swap by focusing + swapnext
        # Better approach: swap positions manually
        pos_a = win_a.get("at", [0, 0])
        size_a = win_a.get("size", [0, 0])
        pos_b = win_b.get("at", [0, 0])
        size_b = win_b.get("size", [0, 0])

        commands = [
            f"movewindowpixel exact {pos_b[0]} {pos_b[1]},address:{addr_a}",
            f"resizewindowpixel exact {size_b[0]} {size_b[1]},address:{addr_a}",
            f"movewindowpixel exact {pos_a[0]} {pos_a[1]},address:{addr_b}",
            f"resizewindowpixel exact {size_a[0]} {size_a[1]},address:{addr_b}",
        ]
        _dispatch_batch(commands)
        return {
            "action": "swap",
            "commands_run": commands,
            "result": f"Swapped {name_a} and {name_b}",
        }

    return None


def _handle_focus(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle focusing a specific window."""
    m = re.search(r"(?:focus|switch\s+to|go\s+to|show)\s+(?:my\s+)?(?:the\s+)?(.+?)(?:\s+window)?$", query, re.I)
    if not m:
        return None

    target = m.group(1).strip()

    # Don't capture workspace switches here
    if re.match(r"workspace\s+\d+", target, re.I):
        return None

    window = _find_window(target, clients)
    if window:
        addr = window["address"]
        ws = window.get("workspace", {}).get("id", 1)
        commands = [f"focuswindow address:{addr}"]
        _dispatch_batch(commands)
        return {
            "action": "focus",
            "commands_run": commands,
            "result": f"Focused {window.get('class', target)}",
        }

    return {"action": "focus", "commands_run": [], "result": f"Could not find window matching '{target}'"}


def _resolve_monitor_name(name: str, monitors: list[dict]) -> dict | None:
    """Map a natural language monitor name to a monitor dict.

    Uses spatial position (top/left/right/main) to find the right monitor.
    """
    name = name.lower().strip()

    # Direct output name match
    for m in monitors:
        if m.get("name", "").lower() == name:
            return m

    # Skip headless monitors for natural language matching
    real_monitors = [m for m in monitors if "HEADLESS" not in m.get("name", "")]
    if not real_monitors:
        return None

    # Sort by position to determine spatial relationships
    by_y = sorted(real_monitors, key=lambda m: m.get("y", 0))
    by_x = sorted(real_monitors, key=lambda m: m.get("x", 0))

    # Find the "main" / "primary" monitor (largest resolution, or DP-*)
    main = None
    for m in real_monitors:
        if m.get("name", "").startswith("DP-"):
            main = m
            break
    if not main:
        main = max(real_monitors, key=lambda m: m.get("width", 0) * m.get("height", 0))

    if name in ("main", "primary", "center", "middle", "big"):
        return main

    if name in ("top", "upper", "above"):
        # Monitor with lowest Y value (most negative = highest on screen)
        top = by_y[0]
        # Don't return main if it IS the topmost — they probably mean the one above main
        if top == main and len(by_y) > 1:
            return by_y[1] if by_y[1].get("y", 0) < main.get("y", 0) else top
        return top

    if name in ("bottom", "lower", "below"):
        return by_y[-1]

    if name in ("left", "portrait"):
        return by_x[0]

    if name in ("right"):
        return by_x[-1]

    return None


def _handle_move_to_monitor(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle moving windows to a specific monitor by name/position."""
    m = re.search(
        r"(?:put|place|move|send)\s+(?:my\s+)?(?:the\s+)?(.+?)\s+"
        r"(?:to|on|onto)\s+(?:the\s+)?"
        r"(top|upper|above|bottom|lower|below|left|right|main|primary|portrait|center|middle|big)\s+"
        r"(?:monitor|screen|display)",
        query, re.I
    )
    if not m:
        # Also match "put X on top" without "monitor" if context is clear
        m = re.search(
            r"(?:put|place|move|send)\s+(?:my\s+)?(?:the\s+)?(.+?)\s+"
            r"(?:to|on|onto)\s+(?:the\s+)?"
            r"(top|upper|above|bottom|lower|below|left|right|main|primary|portrait)\b",
            query, re.I
        )
    if not m:
        return None

    target_name = m.group(1).strip()
    monitor_name = m.group(2).strip()

    target_monitor = _resolve_monitor_name(monitor_name, monitors)
    if not target_monitor:
        return {"action": "move_to_monitor", "commands_run": [],
                "result": f"Could not find a '{monitor_name}' monitor"}

    # Get the workspace bound to that monitor
    target_ws = target_monitor.get("activeWorkspace", {}).get("id", 1)

    # Find the window
    if re.match(r"(this|the\s+focused|current|it)\b", target_name, re.I):
        active = _get_active_window()
        if not active:
            return {"action": "move_to_monitor", "commands_run": [],
                    "result": "No focused window"}
        addr = active["address"]
        window_desc = active.get("class", "window")
    else:
        window = _find_window(target_name, clients)
        if not window:
            return {"action": "move_to_monitor", "commands_run": [],
                    "result": f"Could not find window matching '{target_name}'"}
        addr = window["address"]
        window_desc = window.get("class", target_name)

    mon_name = target_monitor.get("name", "")
    commands = [
        f"movetoworkspace {target_ws},address:{addr}",
        f"movewindow mon:{mon_name},address:{addr}",
    ]
    for cmd in commands:
        _dispatch(cmd)
    return {
        "action": "move_to_monitor",
        "commands_run": commands,
        "result": f"Moved {window_desc} to {mon_name} (workspace {target_ws})",
    }


def _handle_open_on_monitor(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle 'open X on the Y monitor' — launch app then move it."""
    m = re.search(
        r"(?:open|launch|start)\s+(?:a\s+)?(?:new\s+)?(?:my\s+)?(?:the\s+)?(.+?)\s+"
        r"(?:window\s+)?(?:on|to|onto)\s+(?:the\s+)?"
        r"(top|upper|above|bottom|lower|below|left|right|main|primary|portrait|center|middle|big)"
        r"(?:\s+(?:monitor|screen|display))?",
        query, re.I
    )
    if not m:
        return None

    app_name = m.group(1).strip().rstrip(" window")
    monitor_name = m.group(2).strip()

    target_monitor = _resolve_monitor_name(monitor_name, monitors)
    if not target_monitor:
        return {"action": "open_on_monitor", "commands_run": [],
                "result": f"Could not find a '{monitor_name}' monitor"}

    mon_name = target_monitor.get("name", "")
    target_ws = target_monitor.get("activeWorkspace", {}).get("id", 1)

    # Map app names to launch commands
    app_commands = {
        "firefox": "firefox",
        "browser": "firefox",
        "terminal": "ghostty",
        "ghostty": "ghostty",
        "code": "code",
        "vscode": "code",
        "editor": "code",
        "file manager": "thunar",
        "files": "thunar",
        "thunar": "thunar",
        "spotify": "spotify-launcher",
        "steam": "steam",
        "discord": "vesktop",
        "gimp": "gimp",
    }

    app_key = app_name.lower()
    launch_cmd = app_commands.get(app_key, app_key)

    # Snapshot current window addresses before launch
    before_addrs = {c["address"] for c in clients}

    # Launch the app
    _dispatch(f"exec {launch_cmd}")

    # Wait for the new window to appear, then move it
    import time
    commands = [f"exec {launch_cmd}"]
    for _ in range(20):  # poll for up to 2 seconds
        time.sleep(0.1)
        new_clients = _get_clients()
        new_addrs = {c["address"] for c in new_clients} - before_addrs
        if new_addrs:
            # Move the new window to the target monitor
            for addr in new_addrs:
                move_cmd = f"movetoworkspacesilent {target_ws},address:{addr}"
                _dispatch(move_cmd)
                commands.append(move_cmd)
                # Also use movewindow to be sure
                _dispatch(f"movewindow mon:{mon_name},address:{addr}")
                commands.append(f"movewindow mon:{mon_name},address:{addr}")
            return {
                "action": "open_on_monitor",
                "commands_run": commands,
                "result": f"Opened {app_name} on {mon_name} (workspace {target_ws})",
            }

    # No new window detected — app may reuse existing process
    # Find the app window and move it instead
    for c in _get_clients():
        cls = c.get("class", "").lower()
        if app_key in cls or launch_cmd in cls:
            addr = c["address"]
            _dispatch(f"movetoworkspace {target_ws},address:{addr}")
            _dispatch(f"movewindow mon:{mon_name},address:{addr}")
            commands.extend([
                f"movetoworkspace {target_ws},address:{addr}",
                f"movewindow mon:{mon_name},address:{addr}",
            ])
            return {
                "action": "open_on_monitor",
                "commands_run": commands,
                "result": f"Moved {app_name} to {mon_name} (workspace {target_ws})",
            }

    return {
        "action": "open_on_monitor",
        "commands_run": commands,
        "result": f"Launched {app_name} but couldn't confirm window appeared",
    }


def _handle_open_app(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle 'open a new terminal/browser/etc' without a specific monitor."""
    m = re.search(
        r"(?:open|launch|start)\s+(?:a\s+)?(?:new\s+)?(?:my\s+)?(?:the\s+)?"
        r"(terminal|browser|editor|file\s*manager|files|firefox|ghostty|code|vscode|thunar|gimp|steam|discord|spotify)",
        query, re.I
    )
    if not m:
        return None

    app_name = m.group(1).strip()
    app_commands = {
        "terminal": "ghostty",
        "browser": "firefox",
        "firefox": "firefox",
        "editor": "code",
        "code": "code",
        "vscode": "code",
        "file manager": "thunar",
        "filemanager": "thunar",
        "files": "thunar",
        "thunar": "thunar",
        "gimp": "gimp",
        "steam": "steam",
        "discord": "vesktop",
        "spotify": "spotify-launcher",
        "ghostty": "ghostty",
    }
    launch_cmd = app_commands.get(app_name.lower(), app_name.lower())
    cmd = f"exec {launch_cmd}"
    _dispatch(cmd)
    return {
        "action": "open_app",
        "commands_run": [cmd],
        "result": f"Opened {app_name}",
    }


def _handle_resize(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Handle resize requests."""
    m = re.search(r"(?:resize|make)\s+(?:this\s+)?(?:window\s+)?(?:to\s+)?(\d+)\s*[xX]\s*(\d+)", query, re.I)
    if not m:
        return None

    w = m.group(1)
    h = m.group(2)
    result = _dispatch(f"resizewindowpixel exact {w} {h}")
    return {
        "action": "resize",
        "commands_run": [f"resizewindowpixel exact {w} {h}"],
        "result": result,
    }


# --- Ollama fallback for complex requests ---

def _label_monitor(monitor: dict, all_monitors: list[dict]) -> str:
    """Generate a human-readable spatial label for a monitor."""
    real = [m for m in all_monitors if "HEADLESS" not in m.get("name", "")]
    if not real:
        return ""

    name = monitor.get("name", "")
    if "HEADLESS" in name:
        return "[VIRTUAL]"

    by_y = sorted(real, key=lambda m: m.get("y", 0))
    by_x = sorted(real, key=lambda m: m.get("x", 0))

    # Find main (DP-* or largest)
    main = None
    for m in real:
        if m.get("name", "").startswith("DP-"):
            main = m
            break
    if not main:
        main = max(real, key=lambda m: m.get("width", 0) * m.get("height", 0))

    labels = []
    if monitor == main:
        labels.append("MAIN/PRIMARY")
    is_top = monitor == by_y[0] and monitor != main
    is_bottom = monitor == by_y[-1] and monitor != main and len(by_y) > 1
    is_left = monitor == by_x[0] and monitor != main
    # Only label RIGHT if not already TOP/BOTTOM (avoid confusing spatial labels)
    is_right = monitor == by_x[-1] and monitor != main and len(by_x) > 1 and not is_top and not is_bottom
    if is_top:
        labels.append("TOP")
    if is_bottom:
        labels.append("BOTTOM")
    if is_left:
        labels.append("LEFT")
    if is_right:
        labels.append("RIGHT")

    return f"[{'/'.join(labels)}]" if labels else ""


def _ollama_fallback(query: str, clients: list[dict], monitors: list[dict]) -> dict:
    """For complex requests, ask the local model to generate hyprctl commands."""
    # Build context about current window state
    window_summary = []
    for c in clients:
        ws_id = c.get("workspace", {}).get("id", "?")
        cls = c.get("class", "unknown")
        title = c.get("title", "")[:50]
        addr = c.get("address", "")
        floating = c.get("floating", False)
        pos = c.get("at", [0, 0])
        size = c.get("size", [0, 0])
        window_summary.append(
            f"  - class={cls} title=\"{title}\" addr={addr} ws={ws_id} "
            f"floating={floating} pos={pos[0]},{pos[1]} size={size[0]}x{size[1]}"
        )

    monitor_summary = []
    for m in monitors:
        label = _label_monitor(m, monitors)
        monitor_summary.append(
            f"  - {m.get('name','?')} {label}: {m.get('width','?')}x{m.get('height','?')} "
            f"at {m.get('x',0)},{m.get('y',0)} ws={m.get('activeWorkspace',{}).get('id','?')}"
        )

    active = _get_active_window()
    active_info = ""
    if active:
        active_info = f"Active window: class={active.get('class','')} addr={active.get('address','')}"

    prompt = f"""You are a Hyprland window manager command generator. Given the user's request and the current window state, output ONLY the hyprctl dispatch commands needed, one per line. No explanations, no markdown, just commands.

Available dispatches: movetoworkspace, movetoworkspacesilent, focuswindow, closewindow, settiled, fullscreen, swapnext, workspace, killactive

RULES:
- To move a window to a monitor, use movetoworkspace with that monitor's active workspace ID.
- NEVER use setfloating, togglefloating, movewindowpixel, or resizewindowpixel — always keep windows tiled.
- Use settiled if a window is floating and needs to be tiled.

Current state:
Windows:
{chr(10).join(window_summary)}

Monitors (labels show position — use the workspace ID to target a monitor):
{chr(10).join(monitor_summary)}

{active_info}

IMPORTANT: Output ONLY lines like "dispatch movetoworkspace 5,address:0x..." — no other text. No explanations.

User request: {query}"""

    # Get model from VRAM manager
    try:
        model = Path("/tmp/ollama-smart-model").read_text().strip()
    except Exception:
        model = "qwen2.5:14b"

    import json as _json
    payload = _json.dumps({
        "model": model,
        "prompt": prompt,
        "system": "You output hyprctl dispatch commands only. One command per line. No other text.",
        "stream": False,
        "keep_alive": "5m",
    })

    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/generate", "-d", payload],
            capture_output=True, text=True, timeout=30,
        )
        data = _json.loads(result.stdout)
        raw_response = data.get("response", "").strip()
    except Exception:
        return {"action": "ollama_fallback", "commands_run": [], "result": "Failed to query local model"}

    if not raw_response:
        return {"action": "ollama_fallback", "commands_run": [], "result": "No response from local model"}

    # Parse and execute commands
    commands_run = []
    for line in raw_response.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Strip "hyprctl " prefix if present
        if line.startswith("hyprctl "):
            line = line[len("hyprctl "):]
        # Strip "dispatch " prefix — we add it ourselves
        if line.startswith("dispatch "):
            line = line[len("dispatch "):]
        # Safety: skip anything that looks like it would close costa-ai
        if "killactive" in line or "closewindow" in line:
            # Only allow if the user explicitly asked to close something
            if not re.search(r"close|kill|quit|exit", query, re.I):
                continue
        # Validate it looks like a real dispatch command
        valid_dispatchers = [
            "movetoworkspace", "movetoworkspacesilent", "focuswindow", "closewindow",
            "settiled", "fullscreen", "swapnext", "swapwindow",
            "workspace", "killactive",
        ]
        first_word = line.split()[0] if line.split() else ""
        if first_word not in valid_dispatchers:
            continue
        _dispatch(line)
        commands_run.append(line)

    return {
        "action": "ollama_fallback",
        "commands_run": commands_run,
        "result": f"Executed {len(commands_run)} command(s) via local model" if commands_run else "No valid commands generated",
    }


def _claude_escalation(query: str, clients: list[dict], monitors: list[dict]) -> dict | None:
    """Escalate to Claude when local model can't handle window management."""
    try:
        from router import query_claude
    except ImportError:
        return None

    window_summary = []
    for c in clients:
        ws_id = c.get("workspace", {}).get("id", "?")
        cls = c.get("class", "unknown")
        addr = c.get("address", "")
        window_summary.append(f"  {cls} addr={addr} ws={ws_id}")

    monitor_summary = []
    for m in monitors:
        label = _label_monitor(m, monitors)
        ws = m.get("activeWorkspace", {}).get("id", "?")
        monitor_summary.append(f"  {m.get('name','?')} {label} ws={ws}")

    prompt = (
        f"Execute this Hyprland window management request: {query}\n\n"
        f"Windows:\n" + "\n".join(window_summary) + "\n\n"
        f"Monitors:\n" + "\n".join(monitor_summary) + "\n\n"
        f"Respond with ONLY the hyprctl dispatch commands, one per line. "
        f"To move a window to a monitor, use: movetoworkspace <ws_id>,address:<addr>\n"
        f"No explanations."
    )

    response = query_claude(
        prompt, model="haiku",
        system="You are a Hyprland window manager. Output only hyprctl dispatch commands, one per line. No other text.",
        timeout=15,
    )

    if not response:
        return None

    commands_run = []
    valid_dispatchers = [
        "movetoworkspace", "movetoworkspacesilent", "focuswindow", "closewindow",
        "togglefloating", "setfloating", "settiled", "fullscreen",
        "movewindowpixel", "resizewindowpixel", "swapnext", "swapwindow",
        "workspace", "killactive",
    ]

    for line in response.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("hyprctl "):
            line = line[len("hyprctl "):]
        if line.startswith("dispatch "):
            line = line[len("dispatch "):]
        # Strip backticks/markdown
        line = line.strip("`").strip()
        if not line:
            continue
        first_word = line.split()[0] if line.split() else ""
        if first_word not in valid_dispatchers:
            continue
        _dispatch(line)
        commands_run.append(line)

    if commands_run:
        return {
            "action": "claude_escalation",
            "commands_run": commands_run,
            "result": f"Executed {len(commands_run)} command(s) via Claude",
        }
    return None


# --- Pattern to detect window management queries ---

WINDOW_MGMT_PATTERN = re.compile(
    r"\b((?:open|launch|start)\s+(?:a\s+)?(?:new\s+)?(?:terminal|browser|editor|file\s*manager|files|firefox|ghostty|code|vscode|thunar|gimp|steam|discord|spotify)\b|"
    r"(?:open|launch|start)\b.+(?:on|to)\s+(?:the\s+)?(?:top|upper|above|bottom|lower|left|right|main|primary|portrait)\s*(?:monitor|screen|display)?|"
    r"(?:put|place|move|send)\b.+(?:left|right|top|upper|above|bottom|lower|main|primary|portrait|workspace|monitor|screen|display)|"
    r"(?:tile|untile)\b.*(?:everything|all|window)|"
    r"(?:make|toggle|set)\b.*(?:full\s*screen|float|tile|maximiz)|"
    r"(?:close|kill|quit)\b.*(?:window|terminal|all|every|except|firefox|chrome|chromium|brave|code|ghostty|steam|discord|spotify|gimp|thunar|browser|editor)|"
    r"(?:swap)\b.*(?:window|and|with)|"
    r"(?:resize)\b.*(?:window|\d+\s*x\s*\d+)|"
    r"(?:split|side\s*by\s*side|left\s*and\s*right)|"
    r"(?:switch|go|jump)\s+to\s+(?:workspace\s+)?\d+|"
    r"(?:focus|switch\s+to|go\s+to)\b.*(?:window|editor|browser|terminal|firefox|chrome|code|ghostty|steam|discord|spotify)|"
    r"(?:move|send)\b.*(?:to\s+(?:the\s+)?(?:top|upper|above|bottom|lower|main|primary|left|right|portrait)\s+(?:monitor|screen|display)|to\s+workspace|to\s+\d+)|"
    r"full\s*screen|"
    r"tile\s+everything)\b",
    re.IGNORECASE,
)


def is_window_command(query: str) -> bool:
    """Check if a query is a window management command."""
    return bool(WINDOW_MGMT_PATTERN.search(query))


def execute_window_command(query: str) -> dict:
    """Translate a natural language query into hyprctl commands and execute them.

    Returns:
        dict with keys:
            action: str — what was done
            commands_run: list[str] — hyprctl dispatch commands executed
            result: str — human-readable result
    """
    clients = _get_clients()
    monitors = _get_monitors()

    # Try each pattern handler in priority order
    handlers = [
        _handle_open_on_monitor,
        _handle_open_app,
        _handle_move_to_monitor,
        _handle_split_layout,
        _handle_tile_all,
        _handle_close,
        _handle_swap,
        _handle_fullscreen,
        _handle_floating,
        _handle_move_to_workspace,
        _handle_focus_workspace,
        _handle_resize,
        _handle_focus,
    ]

    for handler in handlers:
        result = handler(query, clients, monitors)
        if result is not None:
            return result

    # No pattern matched — fall back to Ollama
    result = _ollama_fallback(query, clients, monitors)

    # If Ollama produced no valid commands, escalate to Claude
    if not result.get("commands_run"):
        claude_result = _claude_escalation(query, clients, monitors)
        if claude_result and claude_result.get("commands_run"):
            return claude_result

    return result
