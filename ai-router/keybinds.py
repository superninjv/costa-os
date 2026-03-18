"""Costa OS Keybinds Configurator — manage Hyprland keybinds and mouse buttons.

Provides a unified interface for listing, adding, removing, and modifying keybinds,
plus mouse button detection and remapping via evdev (any mouse) and optionally libratbag.

Used by:
  - costa-keybinds CLI tool
  - costa-keybinds-gui GTK4 app
  - costa-ai router (natural language keybind management)
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

HYPR_CONF = Path.home() / ".config" / "hypr" / "hyprland.conf"

# Hyprland bind line regex: bind[flags] = MODS, KEY, dispatcher, [args]
BIND_RE = re.compile(
    r"^(bind[melronitsd]*)\s*=\s*(.+)$", re.IGNORECASE
)

# Variable definition regex: $varName = value
VAR_RE = re.compile(r"^\$(\w+)\s*=\s*(.+)$")

# Well-known evdev button code → human name
EVDEV_BUTTON_NAMES = {
    272: "Left Click",
    273: "Right Click",
    274: "Middle Click",
    275: "Back",
    276: "Forward",
    277: "DPI Shift",
    278: "Extra 1",
    279: "Extra 2",
    280: "Extra 3",
    281: "Extra 4",
    282: "Extra 5",
}

# Mouse button names → evdev codes → Hyprland mouse: codes
MOUSE_BUTTON_MAP = {
    "left": {"evdev": 272, "hypr": "mouse:272", "ratbag": 0},
    "right": {"evdev": 273, "hypr": "mouse:273", "ratbag": 1},
    "middle": {"evdev": 274, "hypr": "mouse:274", "ratbag": 2},
    "back": {"evdev": 275, "hypr": "mouse:275", "ratbag": 3},
    "forward": {"evdev": 276, "hypr": "mouse:276", "ratbag": 4},
    "dpi": {"evdev": 277, "hypr": "mouse:277", "ratbag": 5},
    "g7": {"evdev": 278, "hypr": "mouse:278", "ratbag": 6},
    "g8": {"evdev": 279, "hypr": "mouse:279", "ratbag": 7},
    "g9": {"evdev": None, "hypr": None, "ratbag": 8},
    "scroll_right": {"evdev": None, "hypr": None, "ratbag": 9},
    "scroll_left": {"evdev": None, "hypr": None, "ratbag": 10},
}

# G502 physical layout for human reference (optional, not required)
G502_LAYOUT = {
    0: "Left Click",
    1: "Right Click",
    2: "Middle Click (scroll press)",
    3: "Back (thumb lower)",
    4: "Forward (thumb upper)",
    5: "DPI Shift (sniper, below scroll)",
    6: "G7 (left of left-click, back)",
    7: "G8 (left of left-click, front)",
    8: "G9 (profile button, behind scroll)",
    9: "Scroll Tilt Right",
    10: "Scroll Tilt Left",
}

# Dispatcher categories for grouping keybinds in the GUI
DISPATCHER_CATEGORIES = {
    "Window Management": {"killactive", "togglefloating", "fullscreen", "pseudo",
                          "togglesplit", "movewindow", "resizeactive", "movefocus",
                          "focuswindow", "pin", "centerwindow"},
    "Workspaces": {"workspace", "movetoworkspace", "movetoworkspacesilent",
                   "togglespecialworkspace"},
    "Applications": {"exec"},
    "Media": {"exec"},  # will match on playerctl/volume/brightness in args
    "Monitors": {"focusmonitor", "movecurrentworkspacetomonitor"},
    "Mouse": {"movewindow", "resizewindow"},  # for bindm entries
}


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5, **kwargs)


# ─── Variable resolution ───

def resolve_variables(conf_text: str) -> dict[str, str]:
    """Parse $variable = value definitions from hyprland config text."""
    variables = {}
    for line in conf_text.splitlines():
        m = VAR_RE.match(line.strip())
        if m:
            variables[m.group(1)] = m.group(2).strip()
    return variables


def substitute_variables(text: str, variables: dict[str, str]) -> str:
    """Replace $varName references with their values."""
    for name, value in variables.items():
        text = text.replace(f"${name}", value)
    return text


# ─── Active binds from Hyprland runtime ───

def get_active_binds() -> list[dict]:
    """Get currently active keybinds from Hyprland runtime via hyprctl binds -j."""
    r = _run(["hyprctl", "binds", "-j"])
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


# ─── Categorization ───

def categorize_keybinds(binds: list[dict]) -> dict[str, list[dict]]:
    """Group keybinds into named categories based on dispatcher and context."""
    categories: dict[str, list[dict]] = {}

    for b in binds:
        dispatcher = b["dispatcher"].lower()
        args_lower = b["args"].lower()
        bind_type = b["type"].lower()

        # Determine category
        if bind_type == "bindm":
            cat = "Mouse"
        elif dispatcher == "exec":
            if any(kw in args_lower for kw in ["playerctl", "volume", "wpctl", "brightness", "audio"]):
                cat = "Media"
            elif any(kw in args_lower for kw in ["screenshot", "grim", "slurp"]):
                cat = "Screenshots"
            elif any(kw in args_lower for kw in ["costa-ai", "push-to-talk", "ptt"]):
                cat = "Costa AI"
            elif any(kw in args_lower for kw in ["rofi", "cliphist"]):
                cat = "Launchers & Clipboard"
            else:
                cat = "Applications"
        elif dispatcher in ("workspace", "movetoworkspace", "movetoworkspacesilent",
                            "togglespecialworkspace"):
            cat = "Workspaces"
        elif dispatcher in ("movefocus", "movewindow", "resizeactive", "killactive",
                            "togglefloating", "fullscreen", "pseudo", "togglesplit",
                            "focuswindow", "pin", "centerwindow"):
            cat = "Window Management"
        elif dispatcher in ("focusmonitor", "movecurrentworkspacetomonitor"):
            cat = "Monitors"
        elif dispatcher == "exit":
            cat = "Session"
        else:
            cat = "Other"

        categories.setdefault(cat, []).append(b)

    return categories


# ─── Mouse device discovery (evdev) ───

def discover_mice() -> list[dict]:
    """Auto-discover connected mice via sysfs capabilities (no permissions needed).

    Falls back to evdev if sysfs parsing fails. Works without being in the
    input group — sysfs capability bitmaps are world-readable.
    """
    devices = []
    input_dir = Path("/sys/class/input")
    if not input_dir.exists():
        return []

    for dev_dir in sorted(input_dir.iterdir()):
        if not dev_dir.name.startswith("event"):
            continue
        name_file = dev_dir / "device" / "name"
        caps_file = dev_dir / "device" / "capabilities" / "key"
        if not name_file.exists() or not caps_file.exists():
            continue

        try:
            name = name_file.read_text().strip()
            key_caps = caps_file.read_text().strip()
        except OSError:
            continue

        # Parse hex bitmap: space-separated 64-bit words, MSB-first
        bits = set()
        words = key_caps.split()
        for i, word in enumerate(reversed(words)):
            val = int(word, 16)
            for bit in range(64):
                if val & (1 << bit):
                    bits.add(i * 64 + bit)

        # Mouse buttons live at codes 272-287 (BTN_MOUSE range)
        mouse_buttons = sorted(b for b in bits if 272 <= b <= 287)
        if len(mouse_buttons) >= 2:
            ev_name = dev_dir.name  # e.g. "event5"
            # Read phys for dedup (e.g. "usb-0000:07:00.3-4/input0")
            phys = ""
            phys_file = dev_dir / "device" / "phys"
            if phys_file.exists():
                try:
                    phys = phys_file.read_text().strip()
                except OSError:
                    pass
            devices.append({
                "name": name,
                "path": f"/dev/input/{ev_name}",
                "phys": phys,
                "buttons": mouse_buttons,
            })

    # Deduplicate: group by (manufacturer prefix, button set) — same physical mouse
    # appearing as both "USB Receiver" and "G502 HERO" gets merged
    if len(devices) > 1:
        groups: dict[tuple, list[dict]] = {}
        for d in devices:
            # Extract manufacturer (first word of name, e.g. "Logitech")
            mfr = d["name"].split()[0].lower() if d["name"] else ""
            key = (mfr, tuple(d["buttons"]))
            groups.setdefault(key, []).append(d)

        deduped = []
        for group_key, group in groups.items():
            if len(group) == 1:
                deduped.extend(group)
            else:
                # Prefer the device with the most descriptive name
                best = max(group, key=lambda d: (
                    "receiver" not in d["name"].lower(),
                    "dongle" not in d["name"].lower(),
                    len(d["name"]),
                ))
                deduped.append(best)
        devices = deduped

    return devices


def get_button_name(code: int) -> str:
    """Get human-readable name for an evdev button code."""
    if code in EVDEV_BUTTON_NAMES:
        return EVDEV_BUTTON_NAMES[code]
    try:
        import evdev.ecodes as ecodes
        name = ecodes.BTN.get(code)
        if name:
            if isinstance(name, list):
                name = name[0]
            return name.replace("BTN_", "").replace("_", " ").title()
    except (ImportError, AttributeError):
        pass
    return f"Button {code}"


def has_ratbagctl() -> bool:
    """Check if ratbagctl is available."""
    r = _run(["which", "ratbagctl"])
    return r.returncode == 0


def detect_mouse_button_evdev(device_path: Optional[str] = None,
                              timeout_secs: int = 10,
                              callback=None) -> Optional[dict]:
    """Listen for a mouse button press using evdev directly (no sudo needed).

    Args:
        device_path: specific device to listen on, or None for all mice
        timeout_secs: how long to wait
        callback: optional callable(result_dict) for async notification

    Returns dict with evdev_code, button_name, hypr_code, device_name or None on timeout.
    """
    try:
        import evdev
        import select
    except ImportError:
        return None

    devices = []
    if device_path:
        try:
            devices.append(evdev.InputDevice(device_path))
        except (PermissionError, OSError):
            return None
    else:
        for dev_info in discover_mice():
            try:
                devices.append(evdev.InputDevice(dev_info["path"]))
            except (PermissionError, OSError):
                continue

    if not devices:
        return None

    deadline = time.time() + timeout_secs
    try:
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            r, _, _ = select.select(devices, [], [], min(remaining, 0.5))
            for dev in r:
                try:
                    for event in dev.read():
                        # EV_KEY type = 1, value 1 = press
                        if event.type == 1 and event.value == 1:
                            code = event.code
                            # Skip left/right/middle
                            if code in (272, 273, 274):
                                continue
                            result = {
                                "evdev_code": code,
                                "button_name": get_button_name(code),
                                "hypr_code": f"mouse:{code}",
                                "device_name": dev.name,
                                "device_path": dev.path,
                            }
                            if callback:
                                callback(result)
                            return result
                except (OSError, IOError):
                    continue
    finally:
        for dev in devices:
            try:
                dev.close()
            except Exception:
                pass

    return None


# ─── Keybind parsing ───

def parse_keybinds() -> list[dict]:
    """Parse all keybinds from hyprland.conf."""
    binds = []
    lines = HYPR_CONF.read_text().splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        m = BIND_RE.match(stripped)
        if not m:
            continue
        bind_type = m.group(1)
        parts = [p.strip() for p in m.group(2).split(",")]
        if len(parts) < 3:
            continue
        mods = parts[0] if parts[0] else ""
        key = parts[1]
        dispatcher = parts[2]
        args = ", ".join(parts[3:]) if len(parts) > 3 else ""
        # Check for comment on previous line as description
        desc = ""
        if i > 0 and lines[i - 1].strip().startswith("#"):
            desc = lines[i - 1].strip().lstrip("# ")
        binds.append({
            "line": i + 1,
            "type": bind_type,
            "mods": mods,
            "key": key,
            "dispatcher": dispatcher,
            "args": args,
            "description": desc,
            "raw": stripped,
        })
    return binds


def list_keybinds(filter_key: Optional[str] = None, filter_mod: Optional[str] = None) -> list[dict]:
    """List keybinds, optionally filtered."""
    binds = parse_keybinds()
    if filter_key:
        fk = filter_key.lower()
        binds = [b for b in binds if fk in b["key"].lower() or fk in b["args"].lower() or fk in b["description"].lower()]
    if filter_mod:
        fm = filter_mod.upper()
        binds = [b for b in binds if fm in b["mods"].upper()]
    return binds


def format_keybinds(binds: list[dict], compact: bool = False) -> str:
    """Format keybinds for display."""
    if not binds:
        return "No keybinds found."
    lines = []
    for b in binds:
        combo = f"{b['mods']}+{b['key']}" if b["mods"] else b["key"]
        action = f"{b['dispatcher']} {b['args']}".strip()
        if compact:
            lines.append(f"  {combo:30s} → {action}")
        else:
            desc = f" — {b['description']}" if b["description"] else ""
            lines.append(f"  [{b['type']}] {combo:30s} → {action}{desc}")
    return "\n".join(lines)


def add_keybind(mods: str, key: str, dispatcher: str, args: str = "",
                bind_type: str = "bind", comment: str = "") -> dict:
    """Add a keybind to hyprland.conf."""
    parts = [mods, key, dispatcher]
    if args:
        parts.append(args)
    bind_line = f"{bind_type} = {', '.join(parts)}"

    content = HYPR_CONF.read_text()
    # Find the bind section (after last existing bind line)
    lines = content.splitlines()
    last_bind_idx = 0
    for i, line in enumerate(lines):
        if BIND_RE.match(line.strip()):
            last_bind_idx = i

    # Insert after last bind
    insert_lines = []
    if comment:
        insert_lines.append(f"# {comment}")
    insert_lines.append(bind_line)

    lines = lines[:last_bind_idx + 1] + insert_lines + lines[last_bind_idx + 1:]
    HYPR_CONF.write_text("\n".join(lines) + "\n")

    # Reload
    _run(["hyprctl", "reload"])
    errors = _run(["hyprctl", "configerrors"]).stdout.strip()
    if errors and errors != "ok":
        return {"success": False, "error": errors, "bind": bind_line}
    return {"success": True, "bind": bind_line}


def remove_keybind(mods: str, key: str) -> dict:
    """Remove a keybind by its mod+key combo."""
    content = HYPR_CONF.read_text()
    lines = content.splitlines()
    target_mods = mods.upper().replace(" ", "")
    target_key = key.strip()

    removed = []
    new_lines = []
    skip_comment = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = BIND_RE.match(stripped)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            if len(parts) >= 3:
                bm = parts[0].upper().replace(" ", "")
                bk = parts[1].strip()
                if bm == target_mods and bk == target_key:
                    removed.append(stripped)
                    # Also remove preceding comment if there is one
                    if new_lines and new_lines[-1].strip().startswith("#"):
                        new_lines.pop()
                    continue
        new_lines.append(line)

    if not removed:
        return {"success": False, "error": f"No keybind found for {mods}+{key}"}

    HYPR_CONF.write_text("\n".join(new_lines) + "\n")
    _run(["hyprctl", "reload"])
    return {"success": True, "removed": removed}


def modify_keybind(mods: str, key: str, new_dispatcher: str = None,
                   new_args: str = None, new_key: str = None, new_mods: str = None) -> dict:
    """Modify an existing keybind."""
    content = HYPR_CONF.read_text()
    lines = content.splitlines()
    target_mods = mods.upper().replace(" ", "")
    target_key = key.strip()

    modified = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = BIND_RE.match(stripped)
        if not m:
            continue
        parts = [p.strip() for p in m.group(2).split(",")]
        if len(parts) < 3:
            continue
        bm = parts[0].upper().replace(" ", "")
        bk = parts[1].strip()
        if bm == target_mods and bk == target_key:
            bind_type = m.group(1)
            if new_mods is not None:
                parts[0] = new_mods
            if new_key is not None:
                parts[1] = new_key
            if new_dispatcher is not None:
                parts[2] = new_dispatcher
            if new_args is not None:
                if len(parts) > 3:
                    parts[3:] = [new_args]
                else:
                    parts.append(new_args)
            lines[i] = f"{bind_type} = {', '.join(parts)}"
            modified = True
            break

    if not modified:
        return {"success": False, "error": f"No keybind found for {mods}+{key}"}

    HYPR_CONF.write_text("\n".join(lines) + "\n")
    _run(["hyprctl", "reload"])
    errors = _run(["hyprctl", "configerrors"]).stdout.strip()
    if errors and errors != "ok":
        return {"success": False, "error": errors}
    return {"success": True, "modified": lines[i].strip() if modified else ""}


# ─── Mouse button management ───

def get_ratbag_device() -> Optional[str]:
    """Get the ratbagctl device name."""
    r = _run(["ratbagctl", "list"])
    if r.returncode != 0:
        return None
    # Format: "name:  Device Name"
    for line in r.stdout.splitlines():
        if ":" in line:
            return line.split(":")[0].strip()
    return None


def get_mouse_buttons(device_path: Optional[str] = None) -> list[dict]:
    """Get mouse button info. Uses ratbag if available, falls back to evdev discovery.

    Args:
        device_path: optional evdev device path to query specific device
    """
    # Try ratbag first for detailed mapping info
    if has_ratbagctl():
        device = get_ratbag_device()
        if device:
            buttons = []
            for i in range(11):
                r = _run(["ratbagctl", device, "button", str(i), "get"])
                if r.returncode != 0:
                    continue
                mapping = r.stdout.strip()
                action_match = re.search(r"mapped to '(.+)'", mapping)
                action = action_match.group(1) if action_match else "unknown"
                physical = G502_LAYOUT.get(i, f"Button {i}")
                is_passthrough = action.startswith("button ")
                buttons.append({
                    "index": i,
                    "physical": physical,
                    "action": action,
                    "passthrough": is_passthrough,
                    "hypr_code": f"mouse:{272 + i}" if i <= 7 else None,
                })
            return buttons

    # Fallback: evdev discovery
    mice = discover_mice()
    if device_path:
        mice = [m for m in mice if m["path"] == device_path]

    buttons = []
    seen_codes = set()
    for mouse in mice:
        for code in mouse["buttons"]:
            if code in seen_codes:
                continue
            seen_codes.add(code)
            buttons.append({
                "index": code - 272 if code >= 272 else code,
                "physical": get_button_name(code),
                "action": "passthrough",
                "passthrough": True,
                "hypr_code": f"mouse:{code}",
                "device": mouse["name"],
            })
    return buttons


def remap_mouse_button(button_index: int, action: str = "button") -> dict:
    """Remap a mouse button via ratbag.

    action: "button" (passthrough to OS), "resolution-alternate", etc.
    To make a button available for Hyprland keybinds, set it to "button N+1".
    """
    device = get_ratbag_device()
    if not device:
        return {"success": False, "error": "No ratbag device found"}

    if action == "button":
        # Map to passthrough — button N maps to "button N+1" (1-indexed)
        action = f"button {button_index + 1}"

    r = _run(["ratbagctl", device, "button", str(button_index), "action", "set"] + action.split())
    if r.returncode != 0:
        return {"success": False, "error": r.stderr.strip() or r.stdout.strip()}
    return {"success": True, "button": button_index, "action": action,
            "physical": G502_LAYOUT.get(button_index, f"Button {button_index}")}


def detect_mouse_button(timeout_secs: int = 10, device_path: Optional[str] = None) -> Optional[dict]:
    """Listen for a mouse button press using evdev (no sudo required).

    Args:
        timeout_secs: seconds to wait for a press
        device_path: optional specific device, or None for all mice
    """
    return detect_mouse_button_evdev(device_path=device_path, timeout_secs=timeout_secs)


def enable_all_mouse_buttons() -> list[dict]:
    """Remap all hardware-only mouse buttons to passthrough so Hyprland can see them.
    Returns list of buttons that were remapped.
    """
    buttons = get_mouse_buttons()
    remapped = []
    for b in buttons:
        # Skip left/right/middle (0-2) and scroll tilt (9-10)
        if b["index"] <= 2 or b["index"] >= 9:
            continue
        if not b["passthrough"]:
            result = remap_mouse_button(b["index"], "button")
            if result["success"]:
                remapped.append(result)
    return remapped


# ─── AI integration ───

def keybind_context() -> str:
    """Generate context about keybinds for the AI router."""
    binds = parse_keybinds()
    buttons = get_mouse_buttons()

    mouse_lines = []
    for b in buttons:
        status = "→ OS" if b["passthrough"] else f"→ {b['action']} (hardware)"
        hypr = f" [{b['hypr_code']}]" if b["hypr_code"] and b["passthrough"] else ""
        mouse_lines.append(f"  {b['index']}: {b['physical']:40s} {status}{hypr}")

    return (
        f"=== Keybinds ({len(binds)} total) ===\n"
        + format_keybinds(binds, compact=True)
        + f"\n\n=== Mouse Buttons (G502 Hero) ===\n"
        + "\n".join(mouse_lines)
    )


# ─── Keybind query handling for AI router ───

KEYBIND_PATTERNS = re.compile(
    r"(bind|keybind|shortcut|hotkey|keyboard\s*shortcut|mouse\s*button|remap|rebind|"
    r"unbind|assign|map\s+(key|button)|what.s\s+bound|which\s+key|key\s+for)",
    re.IGNORECASE,
)


def is_keybind_query(query: str) -> bool:
    """Check if a query is about keybinds."""
    return bool(KEYBIND_PATTERNS.search(query))


def handle_keybind_query(query: str) -> dict:
    """Handle a natural language keybind query. Returns AI-router-compatible result."""
    q = query.lower()

    # List keybinds
    if re.search(r"(list|show|what|current)\s*(all\s*)?(key)?bind", q):
        binds = list_keybinds()
        return {
            "response": f"Current keybinds ({len(binds)}):\n{format_keybinds(binds, compact=True)}",
            "model": "keybinds",
            "route": "keybinds",
        }

    # Mouse button queries
    if re.search(r"mouse\s*button|remap\s*mouse|mouse\s*(config|setup|map)", q):
        buttons = get_mouse_buttons()
        lines = []
        for b in buttons:
            status = "passthrough (bindable)" if b["passthrough"] else f"{b['action']} (hardware-only)"
            lines.append(f"  {b['index']}: {b['physical']:40s} → {status}")
        return {
            "response": "Mouse button mappings (G502 Hero):\n" + "\n".join(lines),
            "model": "keybinds",
            "route": "keybinds",
        }

    # Enable all mouse buttons
    if re.search(r"(enable|unlock|free|activate)\s*(all\s*)?mouse\s*button", q):
        remapped = enable_all_mouse_buttons()
        if remapped:
            lines = [f"  Enabled: {r['physical']} → button passthrough" for r in remapped]
            return {
                "response": f"Enabled {len(remapped)} mouse buttons for keybinding:\n" + "\n".join(lines)
                    + "\n\nThese buttons now send events to Hyprland and can be bound with 'bind = , mouse:CODE, ...'",
                "model": "keybinds",
                "route": "keybinds",
            }
        return {
            "response": "All mouse buttons are already enabled for keybinding.",
            "model": "keybinds",
            "route": "keybinds",
        }

    # Detect a button press
    if re.search(r"(detect|identify|which|what)\s*(mouse\s*)?button|press\s*(a\s*)?button", q):
        return {
            "response": "detect_button",
            "model": "keybinds",
            "route": "keybinds",
        }

    # Fall through — return context for AI to handle
    return {
        "response": keybind_context(),
        "model": "keybinds",
        "route": "keybinds",
        "needs_ai": True,
    }
