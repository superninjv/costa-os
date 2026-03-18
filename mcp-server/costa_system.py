#!/usr/bin/env python3
"""Costa OS System MCP Server — gives Claude Code agents eyes and hands.

PRIMARY: Text-based system reading (low token usage, fast)
- read_screen: full desktop state as structured text (windows, workspaces, focused app, media, clipboard)
- read_window: read text content from any app via AT-SPI accessibility tree (Firefox pages, GTK/Qt apps)

SECONDARY: Interaction tools
- type_text, send_key, click_window, scroll_window: interact with windows
- manage_window: focus, close, move, resize, fullscreen
- system_command: run shell commands

FALLBACK: screenshot (only when visual content truly needed — images, videos, layout verification)

All interactions are window-targeted — the user's cursor and keyboard
are never affected. The agent works in the background.
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, Resource

server = Server("costa-system")


def run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a command and return result."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def run_shell(cmd: str, timeout: int = 10) -> str:
    """Run a shell command and return stdout."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr.strip()}"


# ─── AT-SPI accessibility tree reader ────────────────────────

def _atspi_available() -> bool:
    """Check if AT-SPI Python bindings are available."""
    try:
        # Must use system python for GI bindings
        r = run(["/usr/bin/python3", "-c",
                 "import gi; gi.require_version('Atspi', '2.0'); from gi.repository import Atspi"])
        return r.returncode == 0
    except Exception:
        return False


def _read_atspi_tree(target_app: str = "", max_depth: int = 8, max_text: int = 8000) -> str:
    """Read text content from AT-SPI accessibility tree.

    Uses system python (has GI bindings) as a subprocess to avoid
    dependency issues with pyenv/venv python.
    """
    script = '''
import gi, json, sys
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

Atspi.init()

target = sys.argv[1].lower() if len(sys.argv) > 1 else ""
max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 8
max_text = int(sys.argv[3]) if len(sys.argv) > 3 else 8000

def get_node_text(node):
    """Get text from a node using the AT-SPI Text interface."""
    ti = node.get_text_iface()
    if ti:
        cc = Atspi.Text.get_character_count(ti)
        if cc > 0:
            text = Atspi.Text.get_text(ti, 0, min(cc, 2000))
            # Filter out object replacement characters
            return text.replace("\\ufffc", "").strip()
    return ""

collected_text = []
total_len = 0

def extract_text(node, depth=0):
    global total_len
    if depth > max_depth or not node or total_len > max_text:
        return
    try:
        name = (node.get_name() or "").strip()
        role = node.get_role_name() or ""
        text_content = get_node_text(node)
        total_len += len(text_content)

        indent = "  " * min(depth, 6)
        ROLES_WITH_TEXT = ("document web", "document frame", "heading", "link",
            "button", "text", "entry", "paragraph", "section", "list item",
            "menu item", "tab", "page tab", "table cell", "image",
            "combo box", "check box", "radio button", "status bar",
            "tool bar", "label")
        ROLES_NAME_ONLY = ("link", "button", "heading", "page tab", "entry",
            "label", "document web", "list item", "combo box", "check box")

        if role in ROLES_WITH_TEXT:
            if text_content:
                collected_text.append(f"{indent}[{role}] {text_content[:500]}")
            elif name and role in ROLES_NAME_ONLY:
                collected_text.append(f"{indent}[{role}] {name[:200]}")

        n_children = node.get_child_count()
        for i in range(min(n_children, 100)):
            if total_len > max_text:
                break
            extract_text(node.get_child_at_index(i), depth + 1)
    except Exception:
        pass

def extract_firefox(app):
    """Special extraction for Firefox — pulls tabs, URL, and page content."""
    frame = app.get_child_at_index(0)
    if not frame:
        return {}

    results = {}
    tabs = []
    url = ""

    def find_meta(node, depth=0):
        nonlocal url
        if depth > 6 or not node:
            return
        role = node.get_role_name() or ""
        name = node.get_name() or ""
        if role == "page tab" and name:
            tabs.append(name)
        if role == "entry" and "address" in name.lower():
            text = get_node_text(node)
            if text:
                url = text
        for j in range(min(node.get_child_count(), 30)):
            find_meta(node.get_child_at_index(j), depth + 1)

    find_meta(frame)

    # Build header
    header_lines = []
    if tabs:
        header_lines.append("Tabs: " + " | ".join(tabs))
    if url:
        header_lines.append(f"URL: {url}")

    # Find all document web nodes and extract their content
    docs_content = []
    def find_docs(node, depth=0):
        if depth > 8 or not node:
            return
        if node.get_role_name() == "document web":
            global collected_text, total_len
            collected_text = []
            total_len = 0
            extract_text(node, 0)
            doc_name = node.get_name() or "Page"
            if collected_text:
                docs_content.append((doc_name, "\\n".join(collected_text)))
            return  # Don't recurse into doc children again
        for j in range(min(node.get_child_count(), 30)):
            find_docs(node.get_child_at_index(j), depth + 1)

    find_docs(frame)

    title = frame.get_name() or "Firefox"
    content_parts = header_lines
    for doc_name, doc_text in docs_content:
        content_parts.append(f"\\n── {doc_name} ──")
        content_parts.append(doc_text)

    results[title] = "\\n".join(content_parts)
    return results

desktop = Atspi.get_desktop(0)
results = {}

for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    if not app:
        continue
    app_name = app.get_name() or "Unnamed"

    if target and target not in app_name.lower():
        match = False
        for j in range(app.get_child_count()):
            child = app.get_child_at_index(j)
            if child and target in (child.get_name() or "").lower():
                match = True
                break
        if not match:
            continue

    # Firefox gets special handling for tabs/URL extraction
    if app_name == "Firefox":
        results.update(extract_firefox(app))
        continue

    collected_text = []
    total_len = 0
    extract_text(app)

    if collected_text:
        title = app_name
        for j in range(app.get_child_count()):
            child = app.get_child_at_index(j)
            if child and child.get_name():
                title = child.get_name()
                break
        results[title] = "\\n".join(collected_text)

print(json.dumps(results))
'''
    args = ["/usr/bin/python3", "-c", script, target_app, str(max_depth), str(max_text)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return json.dumps({"error": r.stderr.strip() or "No AT-SPI data returned"})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "AT-SPI read timed out (15s)"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Knowledge resources ──────────────────────────────────────

KNOWLEDGE_DIR = Path.home() / ".config" / "costa" / "knowledge"


def _parse_knowledge_frontmatter(filepath: Path) -> dict:
    """Parse YAML frontmatter from a knowledge file."""
    try:
        raw = filepath.read_text()
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                import yaml
                meta = yaml.safe_load(raw[3:end])
                return meta or {}
    except Exception:
        pass
    return {}


def _read_knowledge_content(filepath: Path) -> str:
    """Read knowledge file content, stripping YAML frontmatter."""
    try:
        raw = filepath.read_text()
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                return raw[end + 3:].strip()
        return raw.strip()
    except Exception as e:
        return f"Error reading {filepath.name}: {e}"


@server.list_resources()
async def list_resources():
    """List all Costa OS knowledge files as MCP resources."""
    resources = []
    if KNOWLEDGE_DIR.exists():
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            if path.name.startswith("."):
                continue
            meta = _parse_knowledge_frontmatter(path)
            description = meta.get("l0", f"Costa OS knowledge: {path.stem}")
            resources.append(Resource(
                uri=f"costa://knowledge/{path.stem}",
                name=path.stem,
                description=description,
                mimeType="text/markdown",
            ))
    return resources


@server.read_resource()
async def read_resource(uri: str):
    """Read a specific Costa OS knowledge file."""
    # Parse URI: costa://knowledge/<name>
    if uri.startswith("costa://knowledge/"):
        name = uri.split("/")[-1]
        filepath = KNOWLEDGE_DIR / f"{name}.md"
        if filepath.exists():
            return _read_knowledge_content(filepath)
        return f"Knowledge file not found: {name}"
    return f"Unknown resource URI: {uri}"


# ─── Tool definitions ────────────────────────────────────────

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="read_screen",
            description=(
                "Get a complete text description of the current desktop state. "
                "Returns: all open windows (class, title, workspace, position, focus state), "
                "active workspace, monitor layout, media playback info, clipboard content, "
                "and system status. This is the PRIMARY way to understand what's on screen — "
                "use this FIRST before considering a screenshot. Very low token usage."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_clipboard": {
                        "type": "boolean",
                        "description": "Include current clipboard text content (default true)",
                        "default": True,
                    },
                    "include_media": {
                        "type": "boolean",
                        "description": "Include media player state via MPRIS (default true)",
                        "default": True,
                    },
                    "include_system": {
                        "type": "boolean",
                        "description": "Include basic system stats — CPU, memory, uptime (default false)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="read_window",
            description=(
                "Read the text content of a specific application window using the "
                "AT-SPI accessibility tree. Works with Firefox (web pages, tabs, URLs), "
                "GTK apps (Thunar, GIMP menus, dialogs), Qt apps (Strawberry, VLC), "
                "and most GUI applications. Returns structured text: headings, links, "
                "paragraphs, buttons, form fields, etc. "
                "Use this to READ what's in a window. Use 'screenshot' only if you "
                "need to see images, videos, or precise visual layout."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_class": {
                        "type": "string",
                        "description": (
                            "Window class or app name to read (e.g., 'firefox', 'thunar', "
                            "'strawberry', 'vesktop'). Case-insensitive partial match."
                        ),
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "How deep to traverse the UI tree (default 8, max 15)",
                        "default": 8,
                    },
                    "max_text": {
                        "type": "integer",
                        "description": "Maximum characters of text to return (default 8000)",
                        "default": 8000,
                    },
                },
                "required": ["window_class"],
            },
        ),
        Tool(
            name="screenshot",
            description=(
                "Take a screenshot. Returns the image for Claude to analyze visually. "
                "ONLY use this when you need to see visual content (images, videos, "
                "layout, colors) that can't be read as text. For text content, "
                "use read_window instead — it's faster and cheaper. "
                "Modes: 'full' (entire screen), 'window' (specific window), "
                "'region' (x,y,w,h coordinates)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["full", "window", "region"],
                        "description": "Screenshot mode",
                        "default": "full",
                    },
                    "target": {
                        "type": "string",
                        "description": "For 'window': class name. For 'region': 'x,y wxh'",
                    },
                    "monitor": {
                        "type": "string",
                        "description": "Monitor name for full screenshot (e.g., 'DP-1'). Default: focused.",
                    },
                },
            },
        ),
        Tool(
            name="list_windows",
            description=(
                "List all open windows with their class, title, position, size, "
                "workspace, and whether they're focused. Use this to find windows "
                "before interacting with them."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="type_text",
            description=(
                "Type text into a specific window WITHOUT affecting the user's keyboard. "
                "Does NOT move focus or cursor. Requires the window class name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_class": {
                        "type": "string",
                        "description": "Window class to type into",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Press Enter after typing",
                        "default": False,
                    },
                },
                "required": ["window_class", "text"],
            },
        ),
        Tool(
            name="send_key",
            description=(
                "Send a keyboard shortcut to a specific window. "
                "Does NOT affect the user's keyboard. Examples: 'ctrl+s', 'Return', 'Escape'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_class": {
                        "type": "string",
                        "description": "Window class to send key to",
                    },
                    "key": {
                        "type": "string",
                        "description": "Key or combo to send",
                    },
                },
                "required": ["window_class", "key"],
            },
        ),
        Tool(
            name="click_window",
            description=(
                "Click at a position within a specific window. Coordinates are relative "
                "to the window's top-left corner. Does NOT move the user's cursor."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_class": {
                        "type": "string",
                        "description": "Window class to click in",
                    },
                    "x": {"type": "integer", "description": "X coordinate relative to window"},
                    "y": {"type": "integer", "description": "Y coordinate relative to window"},
                    "button": {
                        "type": "integer",
                        "description": "Mouse button (1=left, 2=middle, 3=right)",
                        "default": 1,
                    },
                    "double_click": {
                        "type": "boolean",
                        "description": "Double-click instead of single",
                        "default": False,
                    },
                },
                "required": ["window_class", "x", "y"],
            },
        ),
        Tool(
            name="manage_window",
            description=(
                "Manage a window: focus, close, fullscreen, float, minimize, "
                "or move to a workspace. Uses Hyprland compositor commands."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_class": {
                        "type": "string",
                        "description": "Window class to manage",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["focus", "close", "fullscreen", "float", "minimize", "move_to_workspace"],
                        "description": "Action to perform",
                    },
                    "args": {
                        "type": "string",
                        "description": "Additional args (e.g., workspace number)",
                    },
                },
                "required": ["window_class", "action"],
            },
        ),
        Tool(
            name="system_command",
            description=(
                "Run a system command and return its output. Use for checking system state, "
                "reading configs, managing services. DANGEROUS commands are rejected."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 10)",
                        "default": 10,
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="scroll_window",
            description="Scroll within a specific window. Does NOT affect the user's cursor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "window_class": {
                        "type": "string",
                        "description": "Window class to scroll in",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "description": "Scroll direction",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Number of scroll clicks (default 3)",
                        "default": 3,
                    },
                },
                "required": ["window_class", "direction"],
            },
        ),
        Tool(
            name="nav_query",
            description=(
                "Ask questions about what's on screen using local AI (Ollama). "
                "Reads the app's accessibility tree and has Ollama interpret it. "
                "Returns compact JSON answers. MUCH cheaper than screenshot — use this first. "
                "Batch multiple queries in one call for efficiency."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "description": "App to read ('firefox', 'strawberry', 'desktop' for overall state)",
                    },
                    "page": {
                        "type": "string",
                        "description": "For Firefox: target a specific tab by partial name (e.g., 'vast', 'gmail')",
                    },
                    "queries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "Query ID for the result"},
                                "find": {"type": "string", "description": "What to find on screen"},
                            },
                            "required": ["id", "find"],
                        },
                        "description": "List of queries to answer from screen content",
                    },
                    "max_text": {
                        "type": "integer",
                        "description": "Max chars of screen content to send to Ollama (default 5000)",
                        "default": 5000,
                    },
                },
                "required": ["app", "queries"],
            },
        ),
        Tool(
            name="nav_plan",
            description=(
                "Execute a conditional navigation plan locally. The plan runs entirely "
                "on-device: AT-SPI reads screen content, Ollama interprets it, actions "
                "(click/type/scroll) execute mechanically, conditions branch automatically. "
                "Claude gets back compact results — one round trip for complex multi-step tasks. "
                "Step types: query, assert, condition (with then/else), action, wait, loop, fallback, read. "
                "See knowledge/costa-nav.md for plan patterns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "description": "Target app ('firefox', 'strawberry', etc.)",
                    },
                    "page": {
                        "type": "string",
                        "description": "For Firefox: target tab by partial name",
                    },
                    "max_text": {
                        "type": "integer",
                        "description": "Max chars per screen read (default 5000)",
                        "default": 5000,
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Plan steps. Types: "
                            "query {id, find}, "
                            "assert {id, expect}, "
                            "condition {check, then:[], else:[]}, "
                            "action {action, target, ...}, "
                            "wait {ms}, "
                            "loop {find, scroll, max_iterations, until}, "
                            "fallback {try:[], catch:[]}, "
                            "read {id}"
                        ),
                    },
                },
                "required": ["app", "steps"],
            },
        ),
        Tool(
            name="nav_routine",
            description=(
                "Run a saved navigation routine by name. Routines are proven plans "
                "saved from previous executions. Use nav_routine_list to see available routines. "
                "Use nav_routine_save to save a new one."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Routine name to run (e.g., 'vast-status')",
                    },
                },
                "required": ["name"],
            },
        ),
    ]


# ─── Tool implementations ────────────────────────────────────

COSTA_NAV = str(Path(__file__).parent.parent / "ai-router" / "costa-nav")


def find_x11_window(class_name: str) -> str | None:
    """Find X11 window ID by class name."""
    r = run(["xdotool", "search", "--class", class_name])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("\n")[0]
    r = run(["xdotool", "search", "--name", class_name])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("\n")[0]
    return None


def find_hypr_window(class_name: str, prefer_workspace: str = "") -> dict | None:
    """Find Hyprland window by class name.

    When multiple windows match (e.g. two Firefox instances), prefers:
    1. Window on the specified workspace (if given)
    2. Window on Claude's headless workspace (ws 7)
    3. First match as fallback
    """
    r = run(["hyprctl", "clients", "-j"])
    if r.returncode != 0:
        return None
    clients = json.loads(r.stdout)
    matches = []
    for c in clients:
        if class_name.lower() in c.get("class", "").lower():
            matches.append(c)
        elif class_name.lower() in c.get("title", "").lower():
            matches.append(c)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Multiple matches — prefer the one on the target or Claude's workspace
    for ws in [prefer_workspace, "7"]:
        if ws:
            for m in matches:
                if str(m.get("workspace", {}).get("id", "")) == ws or \
                   str(m.get("workspace", {}).get("name", "")) == ws:
                    return m
    # Also check for Claude's saved browser address
    claude_addr_file = Path.home() / ".config" / "costa" / "claude-browser-address"
    if claude_addr_file.exists():
        addr = claude_addr_file.read_text().strip()
        for m in matches:
            if m["address"] == addr:
                return m
    return matches[0]


import re as _re

# Regex-based dangerous command deny list — matches shell metacharacter attacks,
# destructive system commands, and code execution via pipes.
_DANGEROUS_PATTERN_LIST = [
    r"\brm\s+(-rf?|--recursive)",
    r"\bdd\s+",
    r"\bmkfs\b",
    r"\bsudo\s+(rm|dd|mkfs|fdisk|parted|wipefs)",
    r"\bpacman\s+-R",
    r">\s*/dev/",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\binit\s+[06]\b",
    r":\(\)\s*\{.*\}",                 # fork bomb
    r"\bmv\s+/\*",                     # mv /* ...
    r"\bchmod\s+(-R\s+)?777\s+/",     # chmod 777 /
    r"\bcurl\b.*\|\s*\bbash\b",       # curl ... | bash
    r"\bwget\b.*\|\s*\bsh\b",         # wget ... | sh
    r"\bpython[23]?\s+-c\b",          # python -c ...
    r"\bperl\s+-e\b",                 # perl -e ...
    r"\beval\b",                       # eval
    r"\bexec\b",                       # exec
]
DANGEROUS_RE = _re.compile("|".join(_DANGEROUS_PATTERN_LIST), _re.IGNORECASE)

# Keep old name for backward compatibility in the substring check loop
DANGEROUS_PATTERNS = [
    ":(){ :|:& };:",
]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        handler = {
            "nav_query": handle_nav_query,
            "nav_plan": handle_nav_plan,
            "nav_routine": handle_nav_routine,
            "read_screen": handle_read_screen,
            "read_window": handle_read_window,
            "screenshot": handle_screenshot,
            "list_windows": handle_list_windows,
            "type_text": handle_type_text,
            "send_key": handle_send_key,
            "click_window": handle_click_window,
            "manage_window": handle_manage_window,
            "system_command": handle_system_command,
            "scroll_window": handle_scroll_window,
        }.get(name)
        if handler:
            return await handler(arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ─── nav_query / nav_plan / nav_routine ───────────────────────

async def _run_costa_nav(args: list[str], timeout: int = 60) -> str:
    """Run costa-nav CLI and return output."""
    try:
        r = subprocess.run(
            [COSTA_NAV] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr.strip() or r.stdout.strip()}"
    except subprocess.TimeoutExpired:
        return '{"error": "costa-nav timed out"}'
    except FileNotFoundError:
        return '{"error": "costa-nav not found"}'


async def handle_nav_query(args: dict):
    request = {
        "app": args.get("app", ""),
        "queries": args.get("queries", []),
    }
    if args.get("page"):
        request["page"] = args["page"]
    if args.get("max_text"):
        request["max_text"] = args["max_text"]

    output = await _run_costa_nav(["query", json.dumps(request)], timeout=45)
    return [TextContent(type="text", text=output)]


async def handle_nav_plan(args: dict):
    plan = {
        "app": args.get("app", ""),
        "steps": args.get("steps", []),
    }
    if args.get("page"):
        plan["page"] = args["page"]
    if args.get("max_text"):
        plan["max_text"] = args["max_text"]

    output = await _run_costa_nav(["plan", json.dumps(plan)], timeout=120)
    return [TextContent(type="text", text=output)]


async def handle_nav_routine(args: dict):
    name = args.get("name", "")
    output = await _run_costa_nav(["routine", name], timeout=120)
    return [TextContent(type="text", text=output)]


# ─── read_screen ──────────────────────────────────────────────

async def handle_read_screen(args: dict):
    include_clipboard = args.get("include_clipboard", True)
    include_media = args.get("include_media", True)
    include_system = args.get("include_system", False)

    sections = []

    # ── Windows & workspaces ──
    r = run(["hyprctl", "clients", "-j"])
    if r.returncode == 0:
        clients = json.loads(r.stdout)
        active = run(["hyprctl", "activewindow", "-j"])
        active_addr = ""
        if active.returncode == 0 and active.stdout.strip():
            try:
                active_addr = json.loads(active.stdout).get("address", "")
            except json.JSONDecodeError:
                pass

        # Group by workspace
        workspaces = {}
        for c in clients:
            ws = c["workspace"]["name"]
            workspaces.setdefault(ws, []).append(c)

        lines = []
        for ws_name in sorted(workspaces.keys(), key=lambda x: (not x.isdigit(), x)):
            lines.append(f"  Workspace {ws_name}:")
            for c in workspaces[ws_name]:
                focused = " ← FOCUSED" if c["address"] == active_addr else ""
                xw = " (XWayland)" if c.get("xwayland") else ""
                floating = " [floating]" if c.get("floating") else ""
                fullscreen = " [fullscreen]" if c.get("fullscreen") else ""
                lines.append(
                    f"    {c['class']}: {c['title'][:60]}"
                    f" | {c['size'][0]}x{c['size'][1]}{xw}{floating}{fullscreen}{focused}"
                )
        sections.append("WINDOWS:\n" + "\n".join(lines))
    else:
        sections.append("WINDOWS: (failed to query)")

    # ── Monitors ──
    r = run(["hyprctl", "monitors", "-j"])
    if r.returncode == 0:
        monitors = json.loads(r.stdout)
        lines = []
        for m in monitors:
            focused = " ← ACTIVE" if m.get("focused") else ""
            lines.append(
                f"  {m['name']}: {m['width']}x{m['height']}@{m.get('refreshRate', '?')}Hz"
                f" — ws:{m.get('activeWorkspace', {}).get('name', '?')}{focused}"
                f" ({m.get('description', '')[:40]})"
            )
        sections.append("MONITORS:\n" + "\n".join(lines))

    # ── Active workspace ──
    r = run(["hyprctl", "activeworkspace", "-j"])
    if r.returncode == 0 and r.stdout.strip():
        try:
            ws = json.loads(r.stdout)
            sections.append(f"ACTIVE WORKSPACE: {ws.get('name', '?')} (monitor: {ws.get('monitor', '?')}, windows: {ws.get('windows', '?')})")
        except json.JSONDecodeError:
            pass

    # ── Clipboard ──
    if include_clipboard:
        clip = run_shell("wl-paste --no-newline 2>/dev/null | head -c 500")
        if clip and not clip.startswith("ERROR"):
            sections.append(f"CLIPBOARD:\n  {clip[:500]}")
        else:
            sections.append("CLIPBOARD: (empty)")

    # ── Media ──
    if include_media:
        media = run_shell("playerctl metadata --format '{{artist}} — {{title}} [{{status}}] ({{playerName}})' 2>/dev/null")
        if media and not media.startswith("ERROR") and "No players found" not in media:
            sections.append(f"MEDIA: {media}")

    # ── System stats ──
    if include_system:
        uptime = run_shell("uptime -p")
        mem = run_shell("free -h | awk '/Mem:/ {printf \"%s / %s (%.0f%%)\", $3, $2, $3/$2*100}'")
        cpu = run_shell("awk '{printf \"%.1f%%\", ($1+$2)*100/($1+$2+$4)}' /proc/stat 2>/dev/null | head -1")
        gpu_vram = run_shell("cat /sys/class/drm/card*/device/mem_info_vram_used 2>/dev/null | head -1")
        gpu_total = run_shell("cat /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null | head -1")
        gpu_str = ""
        if gpu_vram and gpu_total and not gpu_vram.startswith("ERROR"):
            try:
                used_gb = int(gpu_vram) / (1024**3)
                total_gb = int(gpu_total) / (1024**3)
                gpu_str = f"  VRAM: {used_gb:.1f}GB / {total_gb:.1f}GB"
            except ValueError:
                pass
        sections.append(f"SYSTEM:\n  Uptime: {uptime}\n  Memory: {mem}{gpu_str}")

    return [TextContent(type="text", text="\n\n".join(sections))]


# ─── read_window ──────────────────────────────────────────────

async def handle_read_window(args: dict):
    window_class = args["window_class"]
    max_depth = min(args.get("max_depth", 8), 15)
    max_text = min(args.get("max_text", 8000), 30000)

    # First verify the window exists
    win = find_hypr_window(window_class)
    if not win:
        return [TextContent(type="text", text=f"Window '{window_class}' not found. Use list_windows to see available windows.")]

    # Read AT-SPI tree
    raw = _read_atspi_tree(target_app=window_class, max_depth=max_depth, max_text=max_text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"error": f"Failed to parse AT-SPI output: {raw[:200]}"}

    if "error" in data:
        # AT-SPI failed — fall back to basic window info
        return [TextContent(type="text", text=(
            f"AT-SPI read failed: {data['error']}\n\n"
            f"Window info from compositor:\n"
            f"  Class: {win['class']}\n"
            f"  Title: {win['title']}\n"
            f"  Size: {win['size'][0]}x{win['size'][1]}\n"
            f"  Workspace: {win['workspace']['name']}\n"
            f"  Floating: {win.get('floating', False)}\n\n"
            f"Tip: If this is Firefox, it needs MOZ_ENABLE_A11Y=1. "
            f"Restart Firefox after setting this env var."
        ))]

    # Format output
    lines = []
    lines.append(f"Window: {win['class']} — {win['title']}")
    lines.append(f"Size: {win['size'][0]}x{win['size'][1]} | Workspace: {win['workspace']['name']}")
    lines.append("")

    for window_title, content in data.items():
        lines.append(f"── {window_title} ──")
        lines.append(content)
        lines.append("")

    text = "\n".join(lines)
    if not any(v.strip() for v in data.values()):
        text += (
            "\n(No text content found via AT-SPI. "
            "This app may not expose accessibility data. "
            "Use screenshot as fallback.)"
        )

    return [TextContent(type="text", text=text)]


# ─── screenshot ───────────────────────────────────────────────

async def handle_screenshot(args: dict):
    mode = args.get("mode", "full")
    target = args.get("target", "")
    monitor = args.get("monitor", "")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        if mode == "window" and target:
            win = find_hypr_window(target)
            if not win:
                return [TextContent(type="text", text=f"Window '{target}' not found")]
            x, y = win["at"]
            w, h = win["size"]
            run(["grim", "-g", f"{x},{y} {w}x{h}", tmp_path])
        elif mode == "region" and target:
            run(["grim", "-g", target, tmp_path])
        elif monitor:
            run(["grim", "-o", monitor, tmp_path])
        else:
            run(["grim", tmp_path])

        with open(tmp_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode()

        return [
            ImageContent(type="image", data=img_data, mimeType="image/png"),
            TextContent(type="text", text=f"Screenshot taken ({mode}){f' of {target}' if target else ''}")
        ]
    finally:
        os.unlink(tmp_path)


# ─── list_windows ─────────────────────────────────────────────

async def handle_list_windows(args: dict):
    r = run(["hyprctl", "clients", "-j"])
    if r.returncode != 0:
        return [TextContent(type="text", text="Failed to list windows")]

    clients = json.loads(r.stdout)
    active = run(["hyprctl", "activewindow", "-j"])
    active_addr = ""
    if active.returncode == 0 and active.stdout.strip():
        try:
            active_addr = json.loads(active.stdout).get("address", "")
        except json.JSONDecodeError:
            pass

    lines = []
    for c in clients:
        focused = " [FOCUSED]" if c["address"] == active_addr else ""
        xw = " (XWayland)" if c.get("xwayland") else ""
        lines.append(
            f"  {c['class']:<30s} | {c['title'][:50]:<50s} | "
            f"ws:{c['workspace']['name']:<4s} | pos:{c['at']} size:{c['size']}{xw}{focused}"
        )

    return [TextContent(type="text", text=f"Windows ({len(clients)}):\n" + "\n".join(lines))]


# ─── type_text ────────────────────────────────────────────────

async def handle_type_text(args: dict):
    win_class = args["window_class"]
    text = args["text"]
    press_enter = args.get("press_enter", False)

    wid = find_x11_window(win_class)
    if wid:
        run(["xdotool", "type", "--window", wid, "--clearmodifiers", "--delay", "12", text])
        if press_enter:
            run(["xdotool", "key", "--window", wid, "Return"])
        return [TextContent(type="text", text=f"Typed {len(text)} chars into {win_class} (X11)")]
    else:
        win = find_hypr_window(win_class)
        if not win:
            return [TextContent(type="text", text=f"Window '{win_class}' not found")]

        prev = run(["hyprctl", "activewindow", "-j"])
        prev_addr = ""
        if prev.returncode == 0 and prev.stdout.strip():
            try:
                prev_addr = json.loads(prev.stdout).get("address", "")
            except json.JSONDecodeError:
                pass

        run(["hyprctl", "dispatch", "focuswindow", f"address:{win['address']}"])
        await asyncio.sleep(0.15)
        run(["wtype", "-d", "12", text])
        if press_enter:
            run(["wtype", "-k", "Return"])
        await asyncio.sleep(0.05)

        if prev_addr:
            run(["hyprctl", "dispatch", "focuswindow", f"address:{prev_addr}"])

        return [TextContent(type="text", text=f"Typed {len(text)} chars into {win_class} (Wayland)")]


# ─── send_key ─────────────────────────────────────────────────

async def handle_send_key(args: dict):
    win_class = args["window_class"]
    key = args["key"]

    wid = find_x11_window(win_class)
    if wid:
        run(["xdotool", "key", "--window", wid, "--clearmodifiers", key])
        return [TextContent(type="text", text=f"Sent {key} to {win_class}")]
    else:
        win = find_hypr_window(win_class)
        if not win:
            return [TextContent(type="text", text=f"Window '{win_class}' not found")]

        prev = run(["hyprctl", "activewindow", "-j"])
        prev_addr = ""
        if prev.returncode == 0 and prev.stdout.strip():
            try:
                prev_addr = json.loads(prev.stdout).get("address", "")
            except json.JSONDecodeError:
                pass

        run(["hyprctl", "dispatch", "focuswindow", f"address:{win['address']}"])
        await asyncio.sleep(0.15)

        parts = key.split("+")
        wtype_args = []
        for p in parts[:-1]:
            wtype_args.extend(["-M", p])
        wtype_args.extend(["-k", parts[-1]])
        for p in reversed(parts[:-1]):
            wtype_args.extend(["-m", p])
        run(["wtype"] + wtype_args)
        await asyncio.sleep(0.05)

        if prev_addr:
            run(["hyprctl", "dispatch", "focuswindow", f"address:{prev_addr}"])

        return [TextContent(type="text", text=f"Sent {key} to {win_class} (Wayland)")]


# ─── click_window ─────────────────────────────────────────────

async def handle_click_window(args: dict):
    win_class = args["window_class"]
    x = args["x"]
    y = args["y"]
    button = args.get("button", 1)
    double = args.get("double_click", False)

    wid = find_x11_window(win_class)
    if wid:
        run(["xdotool", "mousemove", "--window", wid, str(x), str(y)])
        click_cmd = ["xdotool", "click", "--window", wid]
        if double:
            click_cmd.extend(["--repeat", "2", "--delay", "50"])
        click_cmd.append(str(button))
        run(click_cmd)
        return [TextContent(type="text", text=f"Clicked ({x},{y}) button {button} in {win_class}")]
    else:
        win = find_hypr_window(win_class)
        if not win:
            return [TextContent(type="text", text=f"Window '{win_class}' not found")]

        abs_x = win["at"][0] + x
        abs_y = win["at"][1] + y

        prev = run(["hyprctl", "activewindow", "-j"])
        prev_addr = ""
        if prev.returncode == 0 and prev.stdout.strip():
            try:
                prev_addr = json.loads(prev.stdout).get("address", "")
            except json.JSONDecodeError:
                pass

        run(["hyprctl", "dispatch", "focuswindow", f"address:{win['address']}"])
        await asyncio.sleep(0.1)
        run(["hyprctl", "dispatch", "movecursor", str(abs_x), str(abs_y)])
        await asyncio.sleep(0.05)
        # ydotool click is more reliable than xdotool on Wayland
        # ydotool button codes: 0x00=left, 0x01=right, 0x02=middle
        ydo_button = {1: "0x00", 2: "0x02", 3: "0x01"}.get(button, "0x00")
        r_click = run(["ydotool", "click", ydo_button])
        if r_click.returncode != 0:
            # fallback to xdotool if ydotool not available
            run(["xdotool", "click", str(button)])
        if double:
            await asyncio.sleep(0.05)
            run(["ydotool", "click", ydo_button]) if r_click.returncode == 0 else run(["xdotool", "click", str(button)])
        await asyncio.sleep(0.05)

        if prev_addr:
            run(["hyprctl", "dispatch", "focuswindow", f"address:{prev_addr}"])

        return [TextContent(type="text", text=f"Clicked ({x},{y}) [abs: {abs_x},{abs_y}] in {win_class} (Wayland)")]


# ─── manage_window ────────────────────────────────────────────

async def handle_manage_window(args: dict):
    win_class = args["window_class"]
    action = args["action"]
    extra = args.get("args", "")

    win = find_hypr_window(win_class)
    if not win:
        return [TextContent(type="text", text=f"Window '{win_class}' not found")]

    addr = win["address"]
    result = ""

    if action == "focus":
        run(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"])
        result = "Focused"
    elif action == "close":
        run(["hyprctl", "dispatch", "closewindow", f"address:{addr}"])
        result = "Closed"
    elif action == "fullscreen":
        run(["hyprctl", "dispatch", "fullscreen", "0"])
        result = "Toggled fullscreen"
    elif action == "float":
        run(["hyprctl", "dispatch", "togglefloating", f"address:{addr}"])
        result = "Toggled floating"
    elif action == "minimize":
        run(["hyprctl", "dispatch", "movetoworkspacesilent", f"special:minimized,address:{addr}"])
        result = "Minimized"
    elif action == "move_to_workspace":
        ws = extra or "1"
        run(["hyprctl", "dispatch", "movetoworkspacesilent", f"{ws},address:{addr}"])
        result = f"Moved to workspace {ws}"

    return [TextContent(type="text", text=f"{result}: {win_class} ({win['title'][:40]})")]


# ─── system_command ───────────────────────────────────────────

async def handle_system_command(args: dict):
    command = args["command"]
    timeout = args.get("timeout", 10)

    cmd_lower = command.lower().strip()

    # Regex-based deny list (covers shell injection patterns)
    m = DANGEROUS_RE.search(cmd_lower)
    if m:
        return [TextContent(type="text", text=f"BLOCKED: dangerous command pattern '{m.group()}'")]

    # Legacy substring checks (fork bomb etc.)
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return [TextContent(type="text", text=f"BLOCKED: dangerous command pattern '{pattern}'")]

    output = run_shell(command, timeout=timeout)
    if len(output) > 4000:
        output = output[:4000] + "\n... (truncated)"

    return [TextContent(type="text", text=output if output else "(no output)")]


# ─── scroll_window ────────────────────────────────────────────

async def handle_scroll_window(args: dict):
    win_class = args["window_class"]
    direction = args["direction"]
    amount = args.get("amount", 3)

    wid = find_x11_window(win_class)
    button_map = {"up": 4, "down": 5, "left": 6, "right": 7}
    btn = button_map.get(direction, 5)

    if wid:
        for _ in range(amount):
            run(["xdotool", "click", "--window", wid, str(btn)])
        return [TextContent(type="text", text=f"Scrolled {direction} {amount}x in {win_class}")]
    else:
        return [TextContent(type="text", text=f"Window '{win_class}' not found in X11 — scroll requires XWayland")]


# ─── Main ────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
