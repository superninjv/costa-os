"""Claude Tool Use — structured function calling for Costa OS.

Defines 30+ tools Claude can call via the tool_use API, organized into:
- System Query Tools (read-only)
- Safe Action Tools (auto-execute)
- Ask-first Tools (need confirmation)

Each tool has a JSON schema definition and a handler function.
"""

import json
import os
import shlex
import subprocess
import re
from pathlib import Path


def _run(cmd: str | list[str], timeout: int = 10) -> str:
    """Run a command and return stdout.

    Accepts either a list (no shell) or a string (shell=True for pipes/redirects).
    Prefer list form for safety; use string form only when shell features are needed.
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
    except subprocess.TimeoutExpired:
        return "(timed out)"
    except Exception as e:
        return f"(error: {e})"


# Allowlist pattern for identifiers used in service names, package names, etc.
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_.@:+-]+$")


# ---------------------------------------------------------------------------
# Tool definitions — JSON schema for Claude API
# ---------------------------------------------------------------------------

SYSTEM_QUERY_TOOLS = [
    {
        "name": "get_system_info",
        "description": "Get CPU, RAM, kernel version, uptime, and hostname",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_gpu_status",
        "description": "Get current GPU utilization, VRAM usage, and temperature",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_disk_usage",
        "description": "Get disk mount points, sizes, used space, and available space",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_running_services",
        "description": "Get systemd service units and their status",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Filter services by name substring",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_running_processes",
        "description": "Get top processes by CPU or memory usage",
        "input_schema": {
            "type": "object",
            "properties": {
                "sort_by": {
                    "type": "string",
                    "enum": ["cpu", "memory"],
                    "description": "Sort by CPU or memory usage (default: memory)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of processes to return (default: 10)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_network_status",
        "description": "Get network interfaces, IP addresses, and listening ports",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_ports": {
                    "type": "boolean",
                    "description": "Include listening ports (default: false)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_audio_devices",
        "description": "Get audio sinks, sources, default device, and volume levels",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_open_windows",
        "description": "Get all open windows with class, title, workspace, and address",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_monitors",
        "description": "Get monitor names, resolutions, positions, and refresh rates",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_installed_packages",
        "description": "Query installed packages by name or check if a specific package is installed",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {
                    "type": "string",
                    "description": "Specific package name to check",
                },
                "search": {
                    "type": "string",
                    "description": "Search term to filter packages by name",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_ollama_models",
        "description": "Get loaded and available Ollama models",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_files",
        "description": "Find files by name, content, or type using natural language",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language file search query, e.g. 'rust file with websocket code'",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_projects",
        "description": "List available project configurations with name, directory, and workspace",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_knowledge",
        "description": "Search the Costa OS knowledge base for information about the system",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic to search for, e.g. 'pipewire audio setup'",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_service_status",
        "description": "Get detailed status of a specific systemd service",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name, e.g. 'docker' or 'pipewire'",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file (first 100 lines)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path (supports ~ expansion)",
                },
            },
            "required": ["path"],
        },
    },
]

SAFE_ACTION_TOOLS = [
    {
        "name": "set_volume",
        "description": "Set the system audio volume",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level 0-100 as percentage",
                },
            },
            "required": ["level"],
        },
    },
    {
        "name": "set_mute",
        "description": "Toggle audio mute on or off",
        "input_schema": {
            "type": "object",
            "properties": {
                "mute": {
                    "type": "boolean",
                    "description": "True to mute, false to unmute",
                },
            },
            "required": ["mute"],
        },
    },
    {
        "name": "media_control",
        "description": "Control media playback (play, pause, next, previous, stop)",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "play-pause", "next", "previous", "stop"],
                    "description": "Media action to perform",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "switch_workspace",
        "description": "Switch to a specific Hyprland workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "workspace": {
                    "type": "integer",
                    "description": "Workspace number (1-10)",
                },
            },
            "required": ["workspace"],
        },
    },
    {
        "name": "move_window",
        "description": "Move a window to a different workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "description": "Window identifier: class name, title substring, or 'focused' for current window",
                },
                "workspace": {
                    "type": "integer",
                    "description": "Target workspace number",
                },
            },
            "required": ["window", "workspace"],
        },
    },
    {
        "name": "focus_window",
        "description": "Focus (bring to front) a window by class name or title",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "description": "Window identifier: class name or title substring, e.g. 'firefox', 'code', 'ghostty'",
                },
            },
            "required": ["window"],
        },
    },
    {
        "name": "toggle_fullscreen",
        "description": "Toggle fullscreen on the focused window",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "toggle_floating",
        "description": "Toggle floating mode on the focused window",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reload_config",
        "description": "Reload Hyprland config, restart Waybar, or restart Dunst",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "enum": ["hyprland", "waybar", "dunst", "all"],
                    "description": "What to reload (default: hyprland)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "send_notification",
        "description": "Send a desktop notification via dunst",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "body": {"type": "string", "description": "Notification body text"},
                "urgency": {
                    "type": "string",
                    "enum": ["low", "normal", "critical"],
                    "description": "Urgency level (default: normal)",
                },
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "switch_project",
        "description": "Switch to a project workspace with full context (terminal, editor, env vars)",
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Project name or search term",
                },
            },
            "required": ["project"],
        },
    },
]

ASK_FIRST_TOOLS = [
    {
        "name": "run_command",
        "description": "Execute a shell command. Use for commands not covered by other tools. The user will be asked to confirm before execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "install_package",
        "description": "Install a package via pacman or yay (AUR). Requires user confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {
                    "type": "string",
                    "description": "Package name to install",
                },
                "aur": {
                    "type": "boolean",
                    "description": "Use yay for AUR packages (default: false, uses pacman)",
                },
            },
            "required": ["package"],
        },
    },
    {
        "name": "manage_service",
        "description": "Start, stop, restart, or enable/disable a systemd service. Requires user confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name",
                },
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "restart", "enable", "disable"],
                    "description": "Action to perform",
                },
                "user": {
                    "type": "boolean",
                    "description": "User-level service (--user flag, default: false)",
                },
            },
            "required": ["service", "action"],
        },
    },
]

# All tools combined
ALL_TOOLS = SYSTEM_QUERY_TOOLS + SAFE_ACTION_TOOLS + ASK_FIRST_TOOLS

# Dangerous command patterns — never execute via run_command
DANGEROUS_PATTERNS = [
    r"\brm\s+(-rf?|--recursive)",
    r"\bdd\s+",
    r"\bmkfs\b",
    r"\bsudo\s+(rm|dd|mkfs|fdisk|parted|wipefs)",
    r"\bpacman\s+-R",
    r">\s*/dev/",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
]
DANGEROUS_RE = re.compile("|".join(DANGEROUS_PATTERNS))


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def handle_get_system_info(**kwargs) -> str:
    uname = _run("uname -a")
    uptime = _run("uptime -p")
    hostname = _run("hostname")
    cpu = _run("lscpu | grep 'Model name' | head -1")
    mem = _run("free -h | grep Mem")
    return f"Hostname: {hostname}\n{cpu}\nMemory: {mem}\nUptime: {uptime}\nKernel: {uname}"


def handle_get_gpu_status(**kwargs) -> str:
    vram_used = _run("cat /sys/class/drm/card*/device/mem_info_vram_used 2>/dev/null")
    vram_total = _run("cat /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null")
    gpu_busy = _run("cat /sys/class/drm/card*/device/gpu_busy_percent 2>/dev/null")
    temp = _run("cat /sys/class/drm/card*/device/hwmon/hwmon*/temp1_input 2>/dev/null")

    parts = []
    if vram_used and vram_total:
        try:
            used_mb = int(vram_used) // (1024 * 1024)
            total_mb = int(vram_total) // (1024 * 1024)
            parts.append(f"VRAM: {used_mb}MB / {total_mb}MB ({used_mb * 100 // total_mb}%)")
        except ValueError:
            parts.append(f"VRAM used: {vram_used}, total: {vram_total}")
    if gpu_busy:
        parts.append(f"GPU busy: {gpu_busy}%")
    if temp:
        try:
            temp_c = int(temp) // 1000
            parts.append(f"Temperature: {temp_c}°C")
        except ValueError:
            pass
    return "\n".join(parts) if parts else "GPU info unavailable"


def handle_get_disk_usage(**kwargs) -> str:
    return _run("df -h --output=source,fstype,size,used,avail,pcent,target -x tmpfs -x devtmpfs 2>/dev/null")


def handle_get_running_services(filter: str = "", **kwargs) -> str:
    base = _run(["systemctl", "list-units", "--type=service", "--state=running",
                 "--no-pager", "--no-legend"])
    if not base:
        return ""
    lines = base.splitlines()
    if filter:
        filter_lower = filter.lower()
        lines = [l for l in lines if filter_lower in l.lower()]
    return "\n".join(lines[:30])


def handle_get_running_processes(sort_by: str = "memory", limit: int = 10, **kwargs) -> str:
    sort_flag = "-%mem" if sort_by == "memory" else "-%cpu"
    limit = max(1, min(limit, 100))
    ps_out = _run(["ps", "aux", f"--sort={sort_flag}"])
    if not ps_out:
        return ""
    lines = ps_out.splitlines()[:limit + 1]
    return "\n".join(lines)


def handle_get_network_status(include_ports: bool = False, **kwargs) -> str:
    result = _run("ip -brief addr show 2>/dev/null")
    if include_ports:
        ports = _run("ss -tlnp 2>/dev/null | head -20")
        if ports:
            result += f"\n\nListening ports:\n{ports}"
    return result


def handle_get_audio_devices(**kwargs) -> str:
    result = _run(["wpctl", "status"])
    if result:
        return "\n".join(result.splitlines()[:40])
    return ""


def handle_get_open_windows(**kwargs) -> str:
    raw = _run(["hyprctl", "clients", "-j"])
    if not raw:
        return "No windows or Hyprland not running"
    try:
        clients = json.loads(raw)
        lines = []
        for c in clients:
            ws = c.get("workspace", {}).get("id", "?")
            cls = c.get("class", "unknown")
            title = c.get("title", "")[:60]
            addr = c.get("address", "")
            floating = "float" if c.get("floating") else "tiled"
            lines.append(f"[ws:{ws}] {cls}: \"{title}\" ({floating}, addr:{addr})")
        return "\n".join(lines) if lines else "No windows open"
    except json.JSONDecodeError:
        return raw


def handle_get_monitors(**kwargs) -> str:
    raw = _run(["hyprctl", "monitors", "-j"])
    if not raw:
        return "No monitors or Hyprland not running"
    try:
        monitors = json.loads(raw)
        lines = []
        for m in monitors:
            name = m.get("name", "?")
            w = m.get("width", "?")
            h = m.get("height", "?")
            rate = m.get("refreshRate", "?")
            x = m.get("x", 0)
            y = m.get("y", 0)
            focused = " (focused)" if m.get("focused") else ""
            ws = m.get("activeWorkspace", {}).get("id", "?")
            lines.append(f"{name}: {w}x{h}@{rate}Hz at ({x},{y}) workspace:{ws}{focused}")
        return "\n".join(lines)
    except json.JSONDecodeError:
        return raw


def handle_get_installed_packages(package: str = "", search: str = "", **kwargs) -> str:
    if package:
        if not _SAFE_IDENTIFIER_RE.match(package):
            return f"Invalid package name: {package}"
        result = _run(["pacman", "-Qi", package])
        if not result or result.startswith("(error"):
            result = _run(["yay", "-Qi", package])
        if not result or result.startswith("(error"):
            avail_out = _run(["pacman", "-Si", package])
            if avail_out and not avail_out.startswith("(error"):
                avail = "\n".join(avail_out.splitlines()[:5])
                return f"{package} is available but NOT installed:\n{avail}"
            return f"{package} is not installed and not found in repositories"
        return result
    elif search:
        all_pkgs = _run(["pacman", "-Qq"])
        if not all_pkgs:
            return ""
        search_lower = search.lower()
        matched = [p for p in all_pkgs.splitlines() if search_lower in p.lower()]
        return "\n".join(matched[:30])
    return "Specify 'package' for info or 'search' to filter installed packages"


def handle_get_ollama_models(**kwargs) -> str:
    models = _run(["ollama", "list"])
    running = _run(["ollama", "ps"])
    result = f"Available models:\n{models}" if models else "Ollama not running"
    if running:
        result += f"\n\nCurrently loaded:\n{running}"
    return result


def handle_search_files(query: str, **kwargs) -> str:
    try:
        from file_search import search_files, format_results
        results = search_files(query)
        return format_results(results)
    except Exception as e:
        return f"File search error: {e}"


def handle_list_projects(**kwargs) -> str:
    try:
        from project_switch import list_projects_formatted
        return list_projects_formatted()
    except Exception as e:
        return f"Error listing projects: {e}"


def handle_search_knowledge(query: str, **kwargs) -> str:
    try:
        from knowledge import select_knowledge_tiered
        return select_knowledge_tiered(query, "claude") or "No relevant knowledge found"
    except Exception as e:
        return f"Knowledge search error: {e}"


def handle_get_service_status(service: str, **kwargs) -> str:
    if not _SAFE_IDENTIFIER_RE.match(service):
        return f"Invalid service name: {service}"
    result = _run(["systemctl", "status", service])
    if result:
        result = "\n".join(result.splitlines()[:20])
    if not result:
        result = _run(["systemctl", "--user", "status", service])
        if result:
            result = "\n".join(result.splitlines()[:20])
    return result or f"Service '{service}' not found"


def handle_read_file(path: str, **kwargs) -> str:
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return f"File not found: {path}"
    if not os.path.isfile(expanded):
        return f"Not a file: {path}"
    try:
        with open(expanded) as f:
            lines = f.readlines()[:100]
        return "".join(lines)
    except Exception as e:
        return f"Error reading {path}: {e}"


def handle_set_volume(level: int, **kwargs) -> str:
    level = max(0, min(100, level))
    return _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level}%"])


def handle_set_mute(mute: bool, **kwargs) -> str:
    val = "1" if mute else "0"
    return _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", val])


def handle_media_control(action: str, **kwargs) -> str:
    allowed_actions = {"play", "pause", "play-pause", "next", "previous", "stop"}
    if action not in allowed_actions:
        return f"Invalid media action: {action}"
    return _run(["playerctl", action])


def handle_switch_workspace(workspace: int, **kwargs) -> str:
    return _run(["hyprctl", "dispatch", "workspace", str(workspace)])


def handle_move_window(window: str, workspace: int, **kwargs) -> str:
    if window.lower() in ("focused", "current", "this", "active"):
        return _run(["hyprctl", "dispatch", "movetoworkspace", str(workspace)])

    # Find window by class/title
    raw = _run(["hyprctl", "clients", "-j"])
    if not raw:
        return "Could not get window list"
    try:
        clients = json.loads(raw)
    except json.JSONDecodeError:
        return "Could not parse window list"

    for c in clients:
        cls = c.get("class", "").lower()
        title = c.get("title", "").lower()
        if window.lower() in cls or window.lower() in title:
            addr = c["address"]
            return _run(["hyprctl", "dispatch", "movetoworkspacesilent",
                         f"{workspace},address:{addr}"])

    return f"No window matching '{window}' found"


def handle_focus_window(window: str, **kwargs) -> str:
    raw = _run(["hyprctl", "clients", "-j"])
    if not raw:
        return "Could not get window list"
    try:
        clients = json.loads(raw)
    except json.JSONDecodeError:
        return "Could not parse window list"

    for c in clients:
        cls = c.get("class", "").lower()
        title = c.get("title", "").lower()
        if window.lower() in cls or window.lower() in title:
            addr = c["address"]
            return _run(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"])

    return f"No window matching '{window}' found"


def handle_toggle_fullscreen(**kwargs) -> str:
    return _run(["hyprctl", "dispatch", "fullscreen", "0"])


def handle_toggle_floating(**kwargs) -> str:
    return _run(["hyprctl", "dispatch", "togglefloating"])


def handle_reload_config(target: str = "hyprland", **kwargs) -> str:
    results = []
    if target in ("hyprland", "all"):
        results.append(f"Hyprland: {_run(['hyprctl', 'reload'])}")
    if target in ("waybar", "all"):
        _run(["killall", "waybar"])
        subprocess.Popen(["waybar"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        results.append("Waybar: restarted")
    if target in ("dunst", "all"):
        _run(["killall", "dunst"])
        subprocess.Popen(["dunst"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        results.append("Dunst: restarted")
    return "\n".join(results)


def handle_send_notification(title: str, body: str, urgency: str = "normal", **kwargs) -> str:
    if urgency not in ("low", "normal", "critical"):
        urgency = "normal"
    _run(["notify-send", "-u", urgency, "-a", "Costa AI", title, body])
    return f"Notification sent: {title}"


def handle_switch_project(project: str, **kwargs) -> str:
    try:
        from project_switch import switch_project
        success = switch_project(project)
        return f"Switched to {project}" if success else f"Failed to switch to {project}"
    except Exception as e:
        return f"Project switch error: {e}"


def handle_run_command(command: str, timeout: int = 30, **kwargs) -> str:
    if DANGEROUS_RE.search(command):
        return f"BLOCKED: This command matches a dangerous pattern and cannot be executed: {command}"
    return _run(command, timeout=timeout)


def handle_install_package(package: str, aur: bool = False, **kwargs) -> str:
    if not _SAFE_IDENTIFIER_RE.match(package):
        return f"Invalid package name: {package}"
    if aur:
        return _run(["yay", "-S", "--noconfirm", package], timeout=120)
    return _run(["sudo", "pacman", "-S", "--noconfirm", package], timeout=120)


def handle_manage_service(service: str, action: str, user: bool = False, **kwargs) -> str:
    if not _SAFE_IDENTIFIER_RE.match(service):
        return f"Invalid service name: {service}"
    allowed_actions = {"start", "stop", "restart", "enable", "disable"}
    if action not in allowed_actions:
        return f"Invalid action: {action}"
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd.extend([action, service])
    return _run(cmd)


# Handler dispatch map
HANDLERS = {
    "get_system_info": handle_get_system_info,
    "get_gpu_status": handle_get_gpu_status,
    "get_disk_usage": handle_get_disk_usage,
    "get_running_services": handle_get_running_services,
    "get_running_processes": handle_get_running_processes,
    "get_network_status": handle_get_network_status,
    "get_audio_devices": handle_get_audio_devices,
    "get_open_windows": handle_get_open_windows,
    "get_monitors": handle_get_monitors,
    "get_installed_packages": handle_get_installed_packages,
    "get_ollama_models": handle_get_ollama_models,
    "search_files": handle_search_files,
    "list_projects": handle_list_projects,
    "search_knowledge": handle_search_knowledge,
    "get_service_status": handle_get_service_status,
    "read_file": handle_read_file,
    "set_volume": handle_set_volume,
    "set_mute": handle_set_mute,
    "media_control": handle_media_control,
    "switch_workspace": handle_switch_workspace,
    "move_window": handle_move_window,
    "focus_window": handle_focus_window,
    "toggle_fullscreen": handle_toggle_fullscreen,
    "toggle_floating": handle_toggle_floating,
    "reload_config": handle_reload_config,
    "send_notification": handle_send_notification,
    "switch_project": handle_switch_project,
    "run_command": handle_run_command,
    "install_package": handle_install_package,
    "manage_service": handle_manage_service,
}

# Tool names by safety category
SAFE_TOOL_NAMES = {t["name"] for t in SYSTEM_QUERY_TOOLS + SAFE_ACTION_TOOLS}
ASK_FIRST_TOOL_NAMES = {t["name"] for t in ASK_FIRST_TOOLS}


def execute_tool(name: str, inputs: dict) -> str:
    """Execute a tool by name with the given inputs.

    Returns the tool result as a string.
    """
    handler = HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        result = handler(**inputs)
        return result if result else "(no output)"
    except Exception as e:
        return f"Tool error ({name}): {e}"


def get_tools_for_route(route: str) -> list[dict]:
    """Get the appropriate tool definitions for a given route.

    - local (Ollama): No tools (doesn't support tool_use well)
    - haiku escalation: System query + safe action tools only
    - haiku+web: System query tools only (web search handled separately)
    - sonnet/opus: All tools
    """
    if route in ("local", "local+weather", "local+escalated"):
        return []
    elif route == "haiku+web":
        return SYSTEM_QUERY_TOOLS
    elif route == "haiku":
        return SYSTEM_QUERY_TOOLS + SAFE_ACTION_TOOLS
    elif route in ("sonnet", "opus"):
        return ALL_TOOLS
    return []


def get_tool_names() -> list[str]:
    """Get all available tool names."""
    return list(HANDLERS.keys())
