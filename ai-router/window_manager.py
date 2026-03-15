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


def _run(cmd: str, timeout: int = 5) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _run_hyprctl(args: str, timeout: int = 5) -> str:
    """Run a hyprctl command and return output."""
    return _run(f"hyprctl {args}", timeout=timeout)


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

    # Get focused monitor dimensions
    monitor = _get_focused_monitor(monitors)
    if not monitor:
        monitor = monitors[0] if monitors else None
    if not monitor:
        return {"action": "split_layout", "commands_run": [], "result": "No monitor found"}

    mon_x = monitor.get("x", 0)
    mon_y = monitor.get("y", 0)
    mon_w = monitor.get("width", 2560)
    mon_h = monitor.get("height", 1440)
    # Account for reserved area (waybar etc)
    reserved = monitor.get("reserved", [0, 0, 0, 0])
    work_x = mon_x + reserved[0]
    work_y = mon_y + reserved[1]
    work_w = mon_w - reserved[0] - reserved[2]
    work_h = mon_h - reserved[1] - reserved[3]

    half_w = work_w // 2
    left_addr = left_win["address"]
    right_addr = right_win["address"]

    commands = []

    # Make sure both are on the active workspace and tiled
    active_ws = _get_active_workspace()
    ws_id = active_ws["id"] if active_ws else 1

    # Move both to current workspace, set floating, position, then resize
    commands.append(f"movetoworkspacesilent {ws_id},address:{left_addr}")
    commands.append(f"movetoworkspacesilent {ws_id},address:{right_addr}")

    # Focus left window and position it
    commands.append(f"focuswindow address:{left_addr}")
    commands.append(f"setfloating address:{left_addr}")
    commands.append(f"resizewindowpixel exact {half_w} {work_h},address:{left_addr}")
    commands.append(f"movewindowpixel exact {work_x} {work_y},address:{left_addr}")

    # Focus right window and position it
    commands.append(f"focuswindow address:{right_addr}")
    commands.append(f"setfloating address:{right_addr}")
    commands.append(f"resizewindowpixel exact {half_w} {work_h},address:{right_addr}")
    commands.append(f"movewindowpixel exact {work_x + half_w} {work_y},address:{right_addr}")

    results = _dispatch_batch(commands)
    return {
        "action": "split_layout",
        "commands_run": commands,
        "result": "Split layout applied",
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
        monitor_summary.append(
            f"  - {m.get('name','?')}: {m.get('width','?')}x{m.get('height','?')} "
            f"at {m.get('x',0)},{m.get('y',0)} ws={m.get('activeWorkspace',{}).get('id','?')}"
        )

    active = _get_active_window()
    active_info = ""
    if active:
        active_info = f"Active window: class={active.get('class','')} addr={active.get('address','')}"

    prompt = f"""You are a Hyprland window manager command generator. Given the user's request and the current window state, output ONLY the hyprctl dispatch commands needed, one per line. No explanations, no markdown, just commands.

Available dispatches: movetoworkspace, movetoworkspacesilent, focuswindow, closewindow, togglefloating, setfloating, settiled, fullscreen, movewindowpixel, resizewindowpixel, swapnext, workspace, killactive

Current state:
Windows:
{chr(10).join(window_summary)}

Monitors:
{chr(10).join(monitor_summary)}

{active_info}

IMPORTANT: Output only lines like "dispatch movetoworkspace 3,address:0x..." — no other text.

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
            "togglefloating", "setfloating", "settiled", "fullscreen",
            "movewindowpixel", "resizewindowpixel", "swapnext", "swapwindow",
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


# --- Pattern to detect window management queries ---

WINDOW_MGMT_PATTERN = re.compile(
    r"\b((?:put|place|move|send)\b.+(?:left|right|workspace|monitor|screen)|"
    r"(?:tile|untile)\b.*(?:everything|all|window)|"
    r"(?:make|toggle|set)\b.*(?:full\s*screen|float|tile|maximiz)|"
    r"(?:close|kill|quit)\b.*(?:window|terminal|all|every|except)|"
    r"(?:swap)\b.*(?:window|and|with)|"
    r"(?:resize)\b.*(?:window|\d+\s*x\s*\d+)|"
    r"(?:split|side\s*by\s*side|left\s*and\s*right)|"
    r"(?:focus|switch\s+to|go\s+to)\b.*(?:window|editor|browser|terminal|firefox|chrome|code|ghostty|steam|discord|spotify)|"
    r"(?:move|send)\b.*(?:to\s+workspace|to\s+\d+)|"
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
    return _ollama_fallback(query, clients, monitors)
