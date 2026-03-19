#!/usr/bin/env python3
"""costa-nav — Local AI navigation agent for Claude Code.

Levels:
  0: costa-nav read <app>           — raw AT-SPI dump (no Ollama)
  1: costa-nav query '{...}'        — batch questions, Ollama interprets
  2: costa-nav plan '{...}'         — conditional plans with actions, local execution loop
  3: costa-nav routine <name>       — saved named plans, one-word triggers

Knowledge:
  - General tool knowledge: knowledge/costa-nav.md (ships with Costa OS)
  - Per-user site knowledge: ~/.config/costa/nav-sites/<domain>.md (auto-learned)
  - Saved routines: ~/.config/costa/nav-routines/<name>.json

Claude sends a plan, costa-nav executes it entirely locally (AT-SPI reads +
mechanical actions + Ollama interpretation), and returns compact results.
One round trip for complex multi-step tasks.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# CLI-Anything fast path — deterministic CLI wrappers for supported apps
try:
    from cli_registry import lookup as cli_lookup, match_query_to_command, run_cli
    _CLI_AVAILABLE = True
except ImportError:
    _CLI_AVAILABLE = False

# ─── Paths ────────────────────────────────────────────────────

COSTA_DIR = Path.home() / ".config" / "costa"
SITE_KNOWLEDGE_DIR = COSTA_DIR / "nav-sites"
ROUTINES_DIR = COSTA_DIR / "nav-routines"
TOOL_KNOWLEDGE_PATH = Path(__file__).parent.parent / "knowledge" / "costa-nav.md"

for d in (SITE_KNOWLEDGE_DIR, ROUTINES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─── Config ───────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Claude's dedicated virtual monitor — headless, takes no physical screen space
# Set by first-boot.sh or env vars. Falls back to detecting any headless monitor.
def _load_nav_config():
    """Load monitor/workspace config from env, config file, or auto-detect."""
    monitor = os.environ.get("COSTA_NAV_MONITOR", "")
    workspace = os.environ.get("COSTA_NAV_WORKSPACE", "")

    if not monitor:
        # Try config file from first-boot
        nav_conf = COSTA_DIR / "nav.conf"
        if nav_conf.exists():
            for line in nav_conf.read_text().splitlines():
                if line.startswith("COSTA_NAV_MONITOR="):
                    monitor = line.split("=", 1)[1].strip()
                elif line.startswith("COSTA_NAV_WORKSPACE="):
                    workspace = line.split("=", 1)[1].strip()

    if not monitor:
        # Auto-detect: find any headless monitor
        try:
            r = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                import json as _json
                for m in _json.loads(r.stdout):
                    if m["name"].startswith("HEADLESS"):
                        monitor = m["name"]
                        workspace = str(m.get("activeWorkspace", {}).get("name", "7"))
                        break
        except Exception:
            pass

    return monitor or "HEADLESS-1", workspace or "7"


CLAUDE_MONITOR, CLAUDE_WORKSPACE = _load_nav_config()
CLAUDE_BROWSER_CLASS = "firefox-claude"  # intended class (Firefox may ignore on Wayland)
CLAUDE_BROWSER_STATE = COSTA_DIR / "claude-browser-address"  # tracks Claude's browser window


def get_model():
    env = os.environ.get("COSTA_NAV_MODEL", "")
    if env:
        return env
    try:
        return Path("/tmp/ollama-smart-model").read_text().strip()
    except FileNotFoundError:
        return "qwen2.5:14b"


# ─── Knowledge loading ───────────────────────────────────────

def load_tool_knowledge() -> str:
    """Load general costa-nav usage knowledge."""
    try:
        return TOOL_KNOWLEDGE_PATH.read_text()
    except FileNotFoundError:
        return ""


def load_site_knowledge(app: str, url: str = "") -> str:
    """Load per-user knowledge about a specific app/site."""
    candidates = []
    # Match by app name
    app_file = SITE_KNOWLEDGE_DIR / f"{app.lower().replace(' ', '-')}.md"
    if app_file.exists():
        candidates.append(app_file.read_text())
    # Match by domain from URL
    if url:
        domain = url.split("/")[0] if "/" in url else url
        domain = domain.replace(".", "-")
        domain_file = SITE_KNOWLEDGE_DIR / f"{domain}.md"
        if domain_file.exists():
            candidates.append(domain_file.read_text())
    return "\n\n".join(candidates)


def save_site_knowledge(app: str, url: str, learnings: list[dict]):
    """Append new learnings to site knowledge file."""
    if not learnings:
        return
    # Use domain from URL if available, else app name
    if url:
        domain = url.split("/")[0] if "/" in url else url
        filename = domain.replace(".", "-") + ".md"
    else:
        filename = app.lower().replace(" ", "-") + ".md"

    filepath = SITE_KNOWLEDGE_DIR / filename
    existing = filepath.read_text() if filepath.exists() else f"# {app} Navigation Knowledge\n\n"

    new_entries = []
    for learn in learnings:
        entry = f"- {learn['fact']}"
        if learn.get("context"):
            entry += f" (learned: {learn['context']})"
        # Don't duplicate
        if entry not in existing:
            new_entries.append(entry)

    if new_entries:
        filepath.write_text(existing.rstrip() + "\n" + "\n".join(new_entries) + "\n")


# ─── AT-SPI reader ───────────────────────────────────────────

ATSPI_SCRIPT = r'''
import gi, json, sys
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

Atspi.init()

target = sys.argv[1].lower() if len(sys.argv) > 1 else ""
max_text = int(sys.argv[2]) if len(sys.argv) > 2 else 12000

def get_text(node):
    ti = node.get_text_iface()
    if ti:
        cc = Atspi.Text.get_character_count(ti)
        if cc > 0:
            t = Atspi.Text.get_text(ti, 0, min(cc, 2000))
            return t.replace("\ufffc", "").strip()
    return ""

total = 0

def extract(node, depth=0, max_depth=12):
    global total
    if depth > max_depth or not node or total > max_text:
        return []
    lines = []
    try:
        name = (node.get_name() or "").strip()
        role = node.get_role_name() or ""
        text = get_text(node)
        total += len(text)

        indent = "  " * min(depth, 6)
        TEXT_ROLES = ("document web", "document frame", "heading", "link",
            "button", "text", "entry", "paragraph", "section", "list item",
            "menu item", "page tab", "table cell", "combo box", "check box",
            "radio button", "status bar", "tool bar", "label", "image")
        NAME_ROLES = ("link", "button", "heading", "page tab", "entry",
            "label", "document web", "list item", "combo box", "check box")

        if role in TEXT_ROLES:
            if text:
                lines.append(f"{indent}[{role}] {text[:500]}")
            elif name and role in NAME_ROLES:
                lines.append(f"{indent}[{role}] {name[:200]}")

        for i in range(min(node.get_child_count(), 100)):
            if total > max_text:
                break
            lines.extend(extract(node.get_child_at_index(i), depth + 1, max_depth))
    except Exception:
        pass
    return lines

def read_firefox(app):
    frame = app.get_child_at_index(0)
    if not frame:
        return {"error": "no frame"}

    tabs, url = [], ""
    def find_meta(node, depth=0):
        nonlocal url
        if depth > 6 or not node:
            return
        role = node.get_role_name() or ""
        name = node.get_name() or ""
        if role == "page tab" and name:
            tabs.append(name)
        if role == "entry" and "address" in name.lower():
            t = get_text(node)
            if t:
                url = t
        for j in range(min(node.get_child_count(), 30)):
            find_meta(node.get_child_at_index(j), depth + 1)
    find_meta(frame)

    docs = []
    def find_docs(node, depth=0):
        if depth > 8 or not node:
            return
        if node.get_role_name() == "document web":
            global total
            total = 0
            content = extract(node, 0)
            docs.append({"title": node.get_name() or "Page", "content": "\n".join(content)})
            return
        for j in range(min(node.get_child_count(), 30)):
            find_docs(node.get_child_at_index(j), depth + 1)
    find_docs(frame)

    result = {"window": frame.get_name() or "Firefox", "tabs": tabs, "url": url, "pages": {}}
    for doc in docs:
        result["pages"][doc["title"]] = doc["content"]
    return result

def read_app(app):
    global total
    total = 0
    lines = extract(app)
    title = app.get_name() or "App"
    for j in range(app.get_child_count()):
        child = app.get_child_at_index(j)
        if child and child.get_name():
            title = child.get_name()
            break
    return {"window": title, "content": "\n".join(lines)}

# ─── Main ───
mode = "read"
if "--list-apps" in sys.argv:
    mode = "list"

desktop = Atspi.get_desktop(0)

if mode == "list":
    apps = []
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app:
            name = app.get_name() or "Unnamed"
            children = app.get_child_count()
            title = ""
            for j in range(children):
                c = app.get_child_at_index(j)
                if c and c.get_name():
                    title = c.get_name()
                    break
            apps.append({"app": name, "window_title": title, "children": children})
    print(json.dumps(apps))
    sys.exit(0)

# Collect all matching apps (important for multiple Firefox instances)
merged_firefox = None
found_any = False

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

    found_any = True

    if app_name == "Firefox":
        data = read_firefox(app)
        if merged_firefox is None:
            merged_firefox = data
        else:
            # Merge tabs and pages from additional Firefox instances
            merged_firefox["tabs"].extend(data.get("tabs", []))
            merged_firefox["pages"].update(data.get("pages", {}))
    else:
        print(json.dumps(read_app(app)))
        sys.exit(0)

if merged_firefox:
    print(json.dumps(merged_firefox))
elif not found_any:
    print(json.dumps({"error": f"App '{target}' not found in AT-SPI tree"}))
'''


def read_atspi(app: str, max_text: int = 12000) -> dict:
    """Read AT-SPI tree for an app."""
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "-c", ATSPI_SCRIPT, app, str(max_text)],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
        return {"error": r.stderr.strip() or "No output from AT-SPI reader"}
    except subprocess.TimeoutExpired:
        return {"error": "AT-SPI read timed out"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}


def list_atspi_apps() -> list:
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "-c", ATSPI_SCRIPT, "", "0", "--list-apps"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            return json.loads(r.stdout)
    except Exception:
        pass
    return []


def read_screen_state() -> str:
    """Desktop state from hyprctl as structured text."""
    sections = []
    try:
        r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5)
        clients = json.loads(r.stdout)
        r2 = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=5)
        active_addr = ""
        if r2.returncode == 0 and r2.stdout.strip():
            try:
                active_addr = json.loads(r2.stdout).get("address", "")
            except json.JSONDecodeError:
                pass

        workspaces = {}
        for c in clients:
            ws = c["workspace"]["name"]
            workspaces.setdefault(ws, []).append(c)

        lines = []
        for ws in sorted(workspaces, key=lambda x: (not x.isdigit(), x)):
            for c in workspaces[ws]:
                focused = " [FOCUSED]" if c["address"] == active_addr else ""
                lines.append(f"ws:{ws} | {c['class']}: {c['title'][:50]}{focused}")
        sections.append("Windows:\n" + "\n".join(lines))
    except Exception as e:
        sections.append(f"Windows: error ({e})")

    try:
        r = subprocess.run(
            ["playerctl", "metadata", "--format", "{{artist}} — {{title}} [{{status}}]"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            sections.append(f"Media: {r.stdout.strip()}")
    except Exception:
        pass

    return "\n\n".join(sections)


# ─── Tiered query system ──────────────────────────────────────
#
# Tier 0: Regex/pattern — <50ms, extracts labeled values directly from AT-SPI text
# Tier 1: Fast model — ~300ms, simple yes/no and value questions
# Tier 2: Smart model — ~3s, complex interpretation, conditions, assertions
#
# Auto-routes based on query complexity. Adapts to user's hardware:
# - 2GB VRAM (1.5b only): regex + 1.5b, plan conditions disabled
# - 4GB VRAM (3b + 1.5b): full 3-tier with 1.5b as fast
# - 8GB+ VRAM (7b/14b + 3b): full 3-tier

import re


def get_fast_model() -> str | None:
    """Get the fast/small model if available (separate from the smart model)."""
    env = os.environ.get("COSTA_NAV_FAST_MODEL", "")
    if env:
        return env
    try:
        return Path("/tmp/ollama-fast-model").read_text().strip()
    except FileNotFoundError:
        pass
    # Try config file
    try:
        config = json.loads((COSTA_DIR / "config.json").read_text())
        fast = config.get("ollama_fast_model", "")
        smart = config.get("ollama_smart_model", "")
        # Only use fast if it's different from smart (otherwise no point)
        if fast and fast != smart:
            return fast
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def get_model_capability() -> str:
    """Estimate the smart model's capability tier.
    Returns 'high' (14b+), 'medium' (7b), 'low' (3b).
    3b is the minimum supported model for navigation."""
    model = get_model()
    if not model:
        return "low"
    model_lower = model.lower()
    for size in ("32b", "30b", "27b", "24b", "22b", "20b", "14b"):
        if size in model_lower:
            return "high"
    for size in ("8b", "7b"):
        if size in model_lower:
            return "medium"
    return "low"


# ─── Tier -1: CLI-Anything fast path ─────────────────────────

def try_cli_query(app: str, query: str) -> dict | None:
    """Try answering via a CLI-Anything wrapper (~50ms, 0 LLM tokens).

    Returns {"value": ..., "tier": "cli", "confidence": "high"} or None.
    Falls through silently on any failure so AT-SPI/Ollama takes over.
    """
    if not _CLI_AVAILABLE:
        return None

    entry = cli_lookup(app)
    if not entry:
        return None

    cmd = match_query_to_command(entry, query)
    if not cmd:
        return None

    result = run_cli(entry, cmd)
    if result is None:
        return None

    # CLI returned valid JSON — wrap it as a tiered result
    # If result is a simple value dict, extract it; otherwise return as-is
    if isinstance(result, dict):
        # Common patterns: {"url": "..."}, {"tabs": [...]}, {"value": ...}
        if "value" in result:
            return {"value": result["value"], "tier": "cli", "confidence": "high"}
        # Single-key result — extract the value
        keys = [k for k in result if not k.startswith("_")]
        if len(keys) == 1:
            return {"value": result[keys[0]], "tier": "cli", "confidence": "high"}
        return {"value": result, "tier": "cli", "confidence": "high"}
    elif isinstance(result, list):
        return {"value": result, "tier": "cli", "confidence": "high"}

    return None


# ─── Tier 0: Regex pattern extraction ────────────────────────

# Patterns for common value types found in AT-SPI text
_MONEY_PATTERN = re.compile(r'\$[\d,]+\.?\d*')
_PERCENT_PATTERN = re.compile(r'\d+\.?\d*\s*%')
_COUNT_PATTERN = re.compile(r'\b(\d+)\b')
_URL_PATTERN = re.compile(r'(?:https?://)?[\w.-]+\.[a-z]{2,}(?:/\S*)?')

# Query patterns that regex can handle (keyword → what to look for)
_REGEX_EXTRACTORS = {
    # Money/balance queries
    r'(?:credit|balance|cost|price|charge|fee|total|amount)\b': _MONEY_PATTERN,
    # URL queries
    r'\b(?:url|address|link|href|page address)\b': _URL_PATTERN,
    # Percentage queries
    r'\b(?:percent|usage|utilization|progress|battery|cpu|memory|disk)\b': _PERCENT_PATTERN,
}

# Queries that can be answered by reading AT-SPI structure directly
_STRUCTURAL_QUERIES = {
    r'\b(?:tabs?|open tabs)\b': 'tabs',
    r'\b(?:url|address bar|current url|page url)\b': 'url',
}


def try_regex_extract(query: str, content: str, atspi_data: dict) -> dict | None:
    """Try to answer a query using regex on the AT-SPI content.
    Returns {"value": ..., "tier": "regex"} or None if can't handle it."""
    query_lower = query.lower()

    # Check structural queries first (tabs, url — from atspi metadata)
    for pattern, field in _STRUCTURAL_QUERIES.items():
        if re.search(pattern, query_lower):
            if field == 'tabs' and 'tabs' in atspi_data:
                return {"value": atspi_data["tabs"], "tier": "regex", "confidence": "high"}
            if field == 'url' and atspi_data.get("url"):
                return {"value": atspi_data["url"], "tier": "regex", "confidence": "high"}

    # Check value extraction queries
    for query_pattern, value_pattern in _REGEX_EXTRACTORS.items():
        if re.search(query_pattern, query_lower):
            # Search near the keyword in context
            matches = value_pattern.findall(content)
            if matches:
                # For money, return the first match (usually the most prominent)
                if value_pattern == _MONEY_PATTERN:
                    return {"value": matches[0], "tier": "regex", "confidence": "high"}
                return {"value": matches[0], "tier": "regex", "confidence": "medium"}

    # Count queries: "how many instances/items/tabs"
    count_match = re.search(r'how many (\w+)', query_lower)
    if count_match:
        target = count_match.group(1)
        # Look for "Target (N)" or "N targets" patterns in content
        pattern = re.compile(rf'{target}\w*\s*\((\d+)\)', re.IGNORECASE)
        m = pattern.search(content)
        if m:
            return {"value": int(m.group(1)), "tier": "regex", "confidence": "high"}
        # Count occurrences of the target in structural elements
        pattern2 = re.compile(rf'\[(?:heading|section|list item)\]\s*.*{target}', re.IGNORECASE)
        count = len(pattern2.findall(content))
        if count > 0:
            return {"value": count, "tier": "regex", "confidence": "medium"}

    return None


# ─── Tier 1/2: Ollama query ──────────────────────────────────

def _is_simple_query(query: str) -> bool:
    """Determine if a query is simple enough for the fast model.
    Simple: yes/no, exists/not, single value extraction, list enumeration.
    Complex: comparisons, conditions, descriptions, multi-part questions."""
    query_lower = query.lower()

    # Complex indicators → needs smart model
    complex_patterns = [
        r'\b(?:describe|explain|summarize|compare|evaluate|analyze)\b',
        r'\b(?:if|whether|condition|based on|depending)\b',
        r'\b(?:and|both|also|as well as)\b.*\b(?:and|both|also)\b',  # multi-part
        r'\b(?:why|how does|what happens)\b',
        r'\b(?:most|least|best|worst|largest|smallest)\b',
    ]
    for p in complex_patterns:
        if re.search(p, query_lower):
            return False

    # Simple indicators → fast model OK
    simple_patterns = [
        r'^(?:is there|does it have|are there)\b',  # boolean
        r'^(?:what is|what\'s) the \w+$',  # single value
        r'\b(?:list|show|what tabs|what buttons|what links)\b',  # enumeration
        r'\b(?:find|locate|where is)\b',  # element finding
        r'\b(?:count|how many|number of)\b',  # counting
    ]
    for p in simple_patterns:
        if re.search(p, query_lower):
            return True

    # Default: simple if query is short
    return len(query.split()) <= 8


def query_ollama(system_prompt: str, user_prompt: str, json_mode: bool = True,
                 model_override: str = "") -> str:
    """Send a query to local Ollama. Uses specified model or default smart model."""
    model = model_override or get_model()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2000},
    }
    if json_mode:
        payload["format"] = "json"

    try:
        r = subprocess.run(
            ["curl", "-s", f"{OLLAMA_URL}/api/chat", "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            resp = json.loads(r.stdout)
            return resp.get("message", {}).get("content", "")
        return json.dumps({"error": f"Ollama failed: {r.stderr}"})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Ollama timed out (30s)"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tiered_query(query: str, content: str, atspi_data: dict,
                 system_prompt: str, force_smart: bool = False,
                 app: str = "") -> dict:
    """Route a query through the fastest capable tier.

    Tier -1 (CLI-Anything): ~50ms — deterministic CLI wrapper (0 LLM tokens)
    Tier 0 (regex): <50ms — structured value extraction
    Tier 1 (fast model): ~300ms — simple interpretation
    Tier 2 (smart model): ~3s — complex reasoning

    Adapts to available hardware. Falls up to next tier on low confidence.
    """
    # ── Tier -1: CLI-Anything ──
    if not force_smart and app:
        cli_result = try_cli_query(app, query)
        if cli_result:
            return cli_result

    # ── Tier 0: Regex ──
    if not force_smart:
        regex_result = try_regex_extract(query, content, atspi_data)
        if regex_result and regex_result.get("confidence") == "high":
            return regex_result

    # ── Tier 1: Fast model (if available and query is simple) ──
    fast_model = get_fast_model()
    if fast_model and not force_smart and _is_simple_query(query):
        prompt = (
            f"Screen content:\n{content}\n\n"
            f"Find: {query}\n\n"
            f'Return JSON: {{"value": <answer>, "confidence": "high"|"low"}}'
        )
        raw = query_ollama(system_prompt, prompt, model_override=fast_model)
        try:
            result = json.loads(raw)
            if result.get("confidence") == "high" and result.get("value") is not None:
                result["tier"] = "fast"
                return result
            # Low confidence → fall through to smart model
        except json.JSONDecodeError:
            pass

    # ── Tier 2: Smart model ──
    prompt = (
        f"Screen content:\n{content}\n\n"
        f"Find: {query}\n\n"
        f'Return JSON: {{"value": <answer>, "confidence": "high"|"low", "debug": "<if not found>"}}'
    )
    raw = query_ollama(system_prompt, prompt)
    try:
        result = json.loads(raw)
        result["tier"] = "smart"
        return result
    except json.JSONDecodeError:
        return {"value": None, "tier": "smart", "confidence": "low",
                "debug": f"Parse error: {raw[:200]}"}


# ─── Action execution ────────────────────────────────────────

def find_hypr_window(class_name: str, prefer_workspace: str = "") -> dict | None:
    """Find Hyprland window by class name.

    When multiple windows match (e.g. two Firefox instances), prefers:
    1. Window on the specified workspace
    2. Window on Claude's headless workspace
    3. Claude's saved browser address
    4. First match as fallback
    """
    r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return None
    matches = []
    for c in json.loads(r.stdout):
        if class_name.lower() in c.get("class", "").lower():
            matches.append(c)
        elif class_name.lower() in c.get("title", "").lower():
            matches.append(c)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Multiple matches — prefer target workspace or Claude's workspace
    for ws in [prefer_workspace, CLAUDE_WORKSPACE]:
        if ws:
            for m in matches:
                if str(m.get("workspace", {}).get("id", "")) == ws or \
                   str(m.get("workspace", {}).get("name", "")) == ws:
                    return m
    # Check for Claude's saved browser address
    if CLAUDE_BROWSER_STATE.exists():
        addr = CLAUDE_BROWSER_STATE.read_text().strip()
        for m in matches:
            if m["address"] == addr:
                return m
    return matches[0]


def get_focused_monitor() -> str:
    """Get the monitor the user is currently focused on."""
    r = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3)
    if r.returncode == 0:
        for m in json.loads(r.stdout):
            if m.get("focused"):
                return m.get("name", "")
    return ""


def get_window_monitor(win: dict) -> str:
    """Get which monitor a window is on."""
    r = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3)
    if r.returncode != 0:
        return ""
    win_ws = win.get("workspace", {}).get("name", "")
    for m in json.loads(r.stdout):
        if m.get("activeWorkspace", {}).get("name") == win_ws:
            return m.get("name", "")
    return ""


def is_on_user_monitor(win: dict) -> bool:
    """Check if a window is on a monitor the user is actively using (not Claude's).

    Safe to interact if:
    - Window is on Claude's headless monitor regardless of user focus
    - Window is on an unfocused monitor that isn't Claude's

    Blocked if:
    - Window is on the user's currently focused monitor (not Claude's monitor)
    """
    win_monitor = get_window_monitor(win)
    # Always safe to interact with windows on Claude's monitor
    if win_monitor == CLAUDE_MONITOR:
        return False
    # If user is focused on this monitor, don't touch it
    user_monitor = get_focused_monitor()
    return win_monitor == user_monitor


def ensure_on_claude_workspace(win: dict) -> bool:
    """Move a window to Claude's workspace if it's not already there.
    Returns True if the window is now on Claude's workspace."""
    win_ws = win.get("workspace", {}).get("name", "")
    if win_ws == CLAUDE_WORKSPACE:
        return True
    # Don't move user's windows — only move if explicitly Claude's (by class)
    if CLAUDE_BROWSER_CLASS in win.get("class", "").lower():
        subprocess.run(
            ["hyprctl", "dispatch", "movetoworkspacesilent",
             f"{CLAUDE_WORKSPACE},address:{win['address']}"],
            capture_output=True, timeout=3
        )
        return True
    return False


def focus_on_claude_monitor(win: dict):
    """Focus a window on Claude's monitor without affecting user's monitor focus."""
    # Use focuswindow which changes focus on that monitor but doesn't switch
    # the user's active monitor if they're on a different one
    subprocess.run(
        ["hyprctl", "dispatch", "focuswindow", f"address:{win['address']}"],
        capture_output=True, timeout=3
    )


def _get_firefox_windows() -> list[dict]:
    """Get all Firefox windows with their addresses."""
    r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return []
    return [c for c in json.loads(r.stdout) if "firefox" in c.get("class", "").lower()]


def open_claude_browser(url: str = "") -> dict:
    """Open a Firefox instance on Claude's dedicated monitor.
    Uses a separate profile so it doesn't interfere with user's browser."""
    profile_dir = COSTA_DIR / "claude-browser-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Write user.js for the profile to enable a11y
    user_js = profile_dir / "user.js"
    if not user_js.exists():
        user_js.write_text(
            'user_pref("accessibility.force_disabled", 0);\n'
            'user_pref("browser.shell.checkDefaultBrowser", false);\n'
            'user_pref("browser.startup.homepage_override.mstone", "ignore");\n'
            'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
        )

    # Snapshot existing Firefox windows before launch
    before = {c["address"] for c in _get_firefox_windows()}

    # Use hyprland window rules to put the new window on Claude's workspace
    # Set a temporary rule matching the class
    subprocess.run(
        ["hyprctl", "keyword", "windowrule",
         f"match:class ^(firefox)$ match:title ^(Mozilla Firefox)$, workspace {CLAUDE_WORKSPACE} silent"],
        capture_output=True, timeout=3
    )

    cmd = ["firefox", "--profile", str(profile_dir), "--new-window"]
    if url:
        cmd.append(url)

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for the new window to appear (poll for up to 5s)
    new_win = None
    for _ in range(25):
        time.sleep(0.2)
        after = _get_firefox_windows()
        for c in after:
            if c["address"] not in before:
                new_win = c
                break
        if new_win:
            break

    # Clean up temporary rule
    subprocess.run(
        ["hyprctl", "keyword", "windowrule",
         f"unset match:class ^(firefox)$ match:title ^(Mozilla Firefox)$"],
        capture_output=True, timeout=3
    )

    if not new_win:
        return {"ok": False, "error": "Could not find new browser window after launch (5s timeout)"}

    # Move to Claude's workspace
    subprocess.run(
        ["hyprctl", "dispatch", "movetoworkspacesilent",
         f"{CLAUDE_WORKSPACE},address:{new_win['address']}"],
        capture_output=True, timeout=3
    )

    # Save the window address so we can find it later
    CLAUDE_BROWSER_STATE.write_text(new_win["address"])

    return {"ok": True, "address": new_win["address"], "workspace": CLAUDE_WORKSPACE}


def find_claude_browser() -> dict | None:
    """Find Claude's browser window by saved address, falling back to class match."""
    # Try saved address first
    if CLAUDE_BROWSER_STATE.exists():
        addr = CLAUDE_BROWSER_STATE.read_text().strip()
        r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for c in json.loads(r.stdout):
                if c["address"] == addr:
                    return c
        # Address stale — browser was closed
        CLAUDE_BROWSER_STATE.unlink(missing_ok=True)

    # Fallback: try by class (may work on some setups)
    return find_hypr_window(CLAUDE_BROWSER_CLASS)


def navigate_claude_browser(url: str) -> dict:
    """Navigate Claude's browser to a URL."""
    win = find_claude_browser()
    if not win:
        # No browser open — open one
        return open_claude_browser(url)

    # Focus Claude's browser and navigate via keyboard
    focus_on_claude_monitor(win)
    time.sleep(0.15)
    # Ctrl+L to focus address bar, type URL, Enter
    subprocess.run(["wtype", "-M", "ctrl", "-k", "l", "-m", "ctrl"], capture_output=True, timeout=3)
    time.sleep(0.2)
    # Select all existing text and replace
    subprocess.run(["wtype", "-M", "ctrl", "-k", "a", "-m", "ctrl"], capture_output=True, timeout=3)
    time.sleep(0.05)
    subprocess.run(["wtype", "-d", "8", url], capture_output=True, timeout=10)
    time.sleep(0.05)
    subprocess.run(["wtype", "-k", "Return"], capture_output=True, timeout=3)

    return {"ok": True, "url": url, "window": win["class"]}


def execute_action(action: dict) -> dict:
    """Execute a mechanical action with focus protection.

    Actions that require focus (click, type, key) will:
    1. Refuse to interact with windows on the user's active workspace
    2. Prefer operating on Claude's dedicated workspace/monitor
    3. Never move the user's cursor or steal keyboard focus from their monitor

    AT-SPI reads are always safe — they don't require focus.
    """
    act = action.get("action", "")
    target = action.get("target", "")
    result = {"action": act, "ok": False}

    try:
        if act == "wait":
            ms = action.get("ms", 500)
            time.sleep(ms / 1000)
            result["ok"] = True

        elif act == "click":
            win = find_hypr_window(target)
            if not win:
                result["error"] = f"Window '{target}' not found"
                return result

            # Focus protection: don't click on user's active workspace
            if is_on_user_monitor(win) and not action.get("force", False):
                result["error"] = (
                    f"Window '{target}' is on user's active monitor "
                    f"({win['workspace']['name']}). Use AT-SPI to read it instead, "
                    f"or open a browser on Claude's workspace with open_browser."
                )
                return result

            x, y = action.get("x", 0), action.get("y", 0)
            abs_x, abs_y = win["at"][0] + x, win["at"][1] + y
            focus_on_claude_monitor(win)
            time.sleep(0.15)
            subprocess.run(["hyprctl", "dispatch", "movecursor", str(abs_x), str(abs_y)],
                          capture_output=True, timeout=3)
            time.sleep(0.05)
            subprocess.run(["xdotool", "click", str(action.get("button", 1))],
                          capture_output=True, timeout=3)
            result["ok"] = True

        elif act == "type":
            text = action.get("text", "")
            win = find_hypr_window(target)
            if not win:
                result["error"] = f"Window '{target}' not found"
                return result

            if is_on_user_monitor(win) and not action.get("force", False):
                result["error"] = (
                    f"Window '{target}' is on user's active monitor. "
                    f"Cannot type without interrupting user."
                )
                return result

            focus_on_claude_monitor(win)
            time.sleep(0.15)
            subprocess.run(["wtype", "-d", "12", text], capture_output=True, timeout=10)
            if action.get("press_enter"):
                subprocess.run(["wtype", "-k", "Return"], capture_output=True, timeout=3)
            result["ok"] = True

        elif act == "key":
            key = action.get("key", "")
            win = find_hypr_window(target)
            if not win:
                result["error"] = f"Window '{target}' not found"
                return result

            if is_on_user_monitor(win) and not action.get("force", False):
                result["error"] = (
                    f"Window '{target}' is on user's active monitor. "
                    f"Cannot send keys without interrupting user."
                )
                return result

            focus_on_claude_monitor(win)
            time.sleep(0.15)
            parts = key.split("+")
            wtype_args = []
            for p in parts[:-1]:
                wtype_args.extend(["-M", p])
            wtype_args.extend(["-k", parts[-1]])
            for p in reversed(parts[:-1]):
                wtype_args.extend(["-m", p])
            subprocess.run(["wtype"] + wtype_args, capture_output=True, timeout=3)
            result["ok"] = True

        elif act == "scroll":
            direction = action.get("direction", "down")
            amount = action.get("amount", 3)
            r = subprocess.run(["xdotool", "search", "--class", target],
                              capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                wid = r.stdout.strip().split("\n")[0]
                btn_map = {"up": 4, "down": 5, "left": 6, "right": 7}
                for _ in range(amount):
                    subprocess.run(["xdotool", "click", "--window", wid, str(btn_map.get(direction, 5))],
                                  capture_output=True, timeout=3)
                result["ok"] = True
            else:
                result["error"] = "Window not found in X11 (scroll requires XWayland)"

        elif act == "focus":
            win = find_hypr_window(target)
            if win:
                if is_on_user_monitor(win) and not action.get("force", False):
                    result["error"] = f"Window '{target}' is on user's active monitor"
                    return result
                focus_on_claude_monitor(win)
                result["ok"] = True
            else:
                result["error"] = f"Window '{target}' not found"

        elif act == "workspace":
            ws = action.get("workspace", CLAUDE_WORKSPACE)
            subprocess.run(["hyprctl", "dispatch", "workspace", str(ws)],
                          capture_output=True, timeout=3)
            result["ok"] = True

        # ── Browser management ──

        elif act == "open_browser":
            url = action.get("url", "")
            r = open_claude_browser(url)
            result.update(r)

        elif act == "navigate":
            url = action.get("url", "")
            if not url:
                result["error"] = "No URL specified"
                return result
            win = find_claude_browser()
            if not win:
                # No browser open — open one with the URL
                r = open_claude_browser(url)
                result.update(r)
            else:
                # Navigate existing browser via keyboard
                focus_on_claude_monitor(win)
                time.sleep(0.15)
                subprocess.run(["wtype", "-M", "ctrl", "-k", "l", "-m", "ctrl"],
                              capture_output=True, timeout=3)
                time.sleep(0.2)
                subprocess.run(["wtype", "-M", "ctrl", "-k", "a", "-m", "ctrl"],
                              capture_output=True, timeout=3)
                time.sleep(0.05)
                subprocess.run(["wtype", "-d", "8", url], capture_output=True, timeout=10)
                time.sleep(0.05)
                subprocess.run(["wtype", "-k", "Return"], capture_output=True, timeout=3)
                result["ok"] = True
                result["url"] = url
                result["address"] = win["address"]

        elif act == "close_browser":
            win = find_claude_browser()
            if win:
                subprocess.run(
                    ["hyprctl", "dispatch", "closewindow", f"address:{win['address']}"],
                    capture_output=True, timeout=3
                )
                CLAUDE_BROWSER_STATE.unlink(missing_ok=True)
                result["ok"] = True
            else:
                result["error"] = "Claude's browser not open"

        elif act == "cli":
            # Execute a CLI-Anything command directly
            if not _CLI_AVAILABLE:
                result["error"] = "CLI-Anything not available"
            else:
                entry = cli_lookup(target) if target else None
                cli_cmd = action.get("command", "")
                if not entry:
                    result["error"] = f"No CLI wrapper for '{target}'"
                elif not cli_cmd:
                    result["error"] = "No command specified for cli action"
                else:
                    cli_out = run_cli(entry, cli_cmd, timeout=action.get("timeout", 10))
                    if cli_out is not None:
                        result["ok"] = True
                        result["output"] = cli_out
                    else:
                        result["error"] = f"CLI command failed: {cli_cmd}"

        else:
            result["error"] = f"Unknown action: {act}"

    except Exception as e:
        result["error"] = str(e)

    return result


# ─── Content helpers ──────────────────────────────────────────

def get_screen_content(app: str, page: str = "", max_text: int = 8000) -> tuple[str, dict]:
    """Read AT-SPI and return (formatted_content, raw_atspi_data)."""
    atspi = read_atspi(app, max_text=max_text)
    if "error" in atspi:
        return f"ERROR: {atspi['error']}", atspi

    parts = []
    if "tabs" in atspi:
        parts.append(f"Tabs: {', '.join(atspi['tabs'])}")
    if "url" in atspi:
        parts.append(f"URL: {atspi['url']}")
    if "pages" in atspi:
        if page:
            page_lower = page.lower()
            # Match against page titles first
            matched = False
            for title, content in atspi["pages"].items():
                if page_lower in title.lower():
                    parts.append(f"\n── {title} ──\n{content}")
                    matched = True
                    break
            # Search tab names, then search page content for the keyword
            if not matched:
                for title, content in atspi["pages"].items():
                    if page_lower in content.lower()[:500]:
                        parts.append(f"\n── {title} ──\n{content}")
                        matched = True
                        break
            # Fallback to first page
            if not matched:
                for title, content in list(atspi["pages"].items())[:1]:
                    parts.append(f"\n── {title} ──\n{content}")
        else:
            for title, content in list(atspi["pages"].items())[:1]:
                parts.append(f"\n── {title} ──\n{content}")
    elif "content" in atspi:
        parts.append(atspi["content"])

    return "\n".join(parts), atspi


# ─── Level 1: Batch query ────────────────────────────────────

QUERY_SYSTEM = """You are a screen reader assistant. You receive accessibility tree content from an application and a set of queries.

For each query, find the answer in the content. Return a JSON object with query IDs as keys.

Rules:
- Be precise and concise — just the data, no explanations
- For values, return just the value
- If not found, return null
- For buttons/links, return {"found": true/false, "label": "text"}
- For lists, return arrays
- Never fabricate — only return what's in the content
- If unsure, include "confidence": "low" in the value"""


def handle_query(request: dict) -> dict:
    app = request.get("app", "")
    queries = request.get("queries", [])
    page = request.get("page", "")

    if not app:
        return {"error": "No app specified"}
    if not queries:
        return {"error": "No queries specified"}

    if app == "desktop":
        return handle_desktop_query(queries)

    content, atspi = get_screen_content(app, page, request.get("max_text", 8000))
    if content.startswith("ERROR"):
        return {"error": content}

    site_knowledge = load_site_knowledge(app, atspi.get("url", ""))
    system_prompt = QUERY_SYSTEM
    if site_knowledge:
        system_prompt += f"\n\nKnown patterns for this site:\n{site_knowledge}"

    # Route each query through the tiered system individually
    result = {}
    tiers_used = set()
    remaining_queries = []

    for q in queries:
        qid = q.get("id", "unknown")
        find = q.get("find", "")

        # Try CLI-Anything first (deterministic, ~50ms)
        cli_result = try_cli_query(app, find)
        if cli_result:
            result[qid] = cli_result.get("value")
            tiers_used.add("cli")
            continue

        # Try regex (instant)
        regex_result = try_regex_extract(find, content, atspi)
        if regex_result and regex_result.get("confidence") == "high":
            result[qid] = regex_result.get("value")
            tiers_used.add("regex")
            continue

        remaining_queries.append(q)

    # Batch remaining queries — separate simple vs complex
    fast_model = get_fast_model()
    simple_qs = []
    complex_qs = []

    for q in remaining_queries:
        if fast_model and _is_simple_query(q["find"]):
            simple_qs.append(q)
        else:
            complex_qs.append(q)

    # Send simple queries to fast model in one batch
    if simple_qs:
        query_lines = [f'- "{q["id"]}": {q["find"]}' for q in simple_qs]
        prompt = (
            f"Application: {app}\nWindow: {atspi.get('window', app)}\n\n"
            f"Screen content:\n{content}\n\nQueries:\n{chr(10).join(query_lines)}\n\n"
            f"Return JSON with query IDs as keys."
        )
        raw = query_ollama(system_prompt, prompt, model_override=fast_model)
        try:
            batch_result = json.loads(raw)
            # Check confidence — move low-confidence ones to complex
            for q in simple_qs:
                qid = q["id"]
                val = batch_result.get(qid)
                if val is not None:
                    result[qid] = val
                    tiers_used.add("fast")
                else:
                    complex_qs.append(q)
        except json.JSONDecodeError:
            complex_qs.extend(simple_qs)

    # Send complex queries to smart model in one batch
    if complex_qs:
        query_lines = [f'- "{q["id"]}": {q["find"]}' for q in complex_qs]
        prompt = (
            f"Application: {app}\nWindow: {atspi.get('window', app)}\n\n"
            f"Screen content:\n{content}\n\nQueries:\n{chr(10).join(query_lines)}\n\n"
            f"Return JSON with query IDs as keys."
        )
        raw = query_ollama(system_prompt, prompt)
        try:
            batch_result = json.loads(raw)
            for q in complex_qs:
                result[q["id"]] = batch_result.get(q["id"])
            tiers_used.add("smart")
        except json.JSONDecodeError:
            for q in complex_qs:
                result[q["id"]] = None

    # Check if CLI wrapper was used
    cli_entry = cli_lookup(app) if _CLI_AVAILABLE else None
    result["_meta"] = {
        "model": get_model(),
        "fast_model": fast_model or "(none)",
        "cli_wrapper": cli_entry.get("entry_point") if cli_entry else "(none)",
        "tiers_used": sorted(tiers_used),
        "app": app,
        "window": atspi.get("window", ""),
        "content_chars": len(content),
    }
    return result


def handle_desktop_query(queries: list) -> dict:
    screen = read_screen_state()
    query_lines = [f'- "{q["id"]}": {q["find"]}' for q in queries]
    prompt = f"Desktop state:\n{screen}\n\nQueries:\n{chr(10).join(query_lines)}\n\nReturn JSON."
    raw = query_ollama(QUERY_SYSTEM, prompt)
    try:
        result = json.loads(raw)
        result["_meta"] = {"model": get_model(), "source": "desktop"}
        return result
    except json.JSONDecodeError:
        return {"error": "Parse error", "raw": raw[:500]}


# ─── Level 2: Plan executor ──────────────────────────────────

PLAN_SYSTEM = """You are a screen navigation assistant executing a step-by-step plan.

You receive:
1. The current screen content (from accessibility tree)
2. A step to evaluate (a query, assertion, or condition)
3. Any site-specific knowledge

For QUERY steps: find the requested information and return it.
For ASSERT steps: check if the assertion is true and return {"pass": true/false, "actual": "what you see"}.
For CONDITION steps: evaluate the condition against screen content and return {"result": true/false, "value": "the relevant value"}.

Always return JSON. Include "confidence": "low" if uncertain.
If something isn't found, include "debug": "nearest matches or likely cause" to help diagnosis."""


def execute_plan(plan: dict) -> dict:
    """Execute a conditional plan with steps, branches, and fallbacks.

    Plan format:
    {
        "app": "firefox",
        "page": "vast",          # optional: target tab
        "steps": [
            {"type": "query", "id": "credit", "find": "credit balance"},
            {"type": "action", "action": "click", "target": "firefox", "x": 100, "y": 200},
            {"type": "wait", "ms": 500},
            {"type": "query", "id": "dialog", "find": "describe any dialog that appeared"},
            {"type": "assert", "id": "logged_in", "expect": "user is logged in"},
            {"type": "condition", "check": "credit < $5", "then": [...steps], "else": [...steps]},
            {"type": "loop", "find": "next list item", "scroll": "down", "max_iterations": 10,
             "collect": "item_text", "until": "no more items"},
            {"type": "fallback", "try": [...steps], "catch": [...steps]},
        ]
    }
    """
    app = plan.get("app", "")
    page = plan.get("page", "")
    max_text = plan.get("max_text", 8000)
    steps = plan.get("steps", [])

    results = {}
    step_log = []
    learnings = []
    url = ""

    last_atspi = {}  # cache atspi data for tiered queries

    def read_current_screen(override_app: str = "", override_page: str = "") -> str:
        nonlocal url, last_atspi
        read_app = override_app or app
        read_page = override_page or page
        if read_app == "desktop":
            last_atspi = {}
            return read_screen_state()
        content, atspi = get_screen_content(read_app, read_page, max_text)
        last_atspi = atspi
        url = atspi.get("url", url)
        return content

    def ask_ollama(step_prompt: str) -> dict:
        site_kb = load_site_knowledge(app, url)
        full_prompt = ""
        if site_kb:
            full_prompt += f"Site knowledge:\n{site_kb}\n\n"
        full_prompt += step_prompt
        raw = query_ollama(PLAN_SYSTEM, full_prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"error": "parse_error", "raw": raw[:300]}

    def run_steps(steps_list: list, depth: int = 0) -> bool:
        """Execute a list of steps. Returns False if a step critically failed."""
        if depth > 5:
            step_log.append({"error": "Max nesting depth reached"})
            return False

        for step in steps_list:
            step_type = step.get("type", "")
            step_id = step.get("id", f"step_{len(step_log)}")

            if step_type == "query":
                content = read_current_screen(step.get("app", ""), step.get("page", ""))
                site_kb = load_site_knowledge(app, url)
                sys_prompt = PLAN_SYSTEM
                if site_kb:
                    sys_prompt += f"\n\nSite knowledge:\n{site_kb}"
                answer = tiered_query(step["find"], content, last_atspi, sys_prompt, app=app)
                results[step_id] = answer.get("value", answer)
                step_log.append({"step": step_id, "type": "query",
                                "tier": answer.get("tier", "?"), "result": answer})

                # Learn from low confidence or null results
                if answer.get("confidence") == "low" or answer.get("value") is None:
                    debug = answer.get("debug", "")
                    if debug:
                        learnings.append({
                            "fact": f"Query '{step['find']}' returned null/low-confidence. Debug: {debug}",
                            "context": f"plan execution, app={app}"
                        })

            elif step_type == "assert":
                content = read_current_screen(step.get("app", ""), step.get("page", ""))
                answer = ask_ollama(
                    f"Screen content:\n{content}\n\n"
                    f"Assert: {step['expect']}\n\n"
                    f"Return JSON: {{\"pass\": true/false, \"actual\": \"what you see\", \"confidence\": \"high\"|\"low\"}}"
                )
                results[step_id] = answer
                step_log.append({"step": step_id, "type": "assert", "result": answer})

                if not answer.get("pass", False):
                    # Assertion failed — learn what was actually there
                    learnings.append({
                        "fact": f"Expected '{step['expect']}' but found: {answer.get('actual', 'unknown')}",
                        "context": f"assertion failure, app={app}"
                    })

            elif step_type == "condition":
                content = read_current_screen(step.get("app", ""), step.get("page", ""))
                answer = ask_ollama(
                    f"Screen content:\n{content}\n\n"
                    f"Evaluate condition: {step['check']}\n\n"
                    f"Return JSON: {{\"result\": true/false, \"value\": \"the relevant value\"}}"
                )
                step_log.append({"step": step_id, "type": "condition", "check": step["check"], "result": answer})
                results[step_id] = answer

                if answer.get("result", False):
                    if "then" in step:
                        run_steps(step["then"], depth + 1)
                else:
                    if "else" in step:
                        run_steps(step["else"], depth + 1)

            elif step_type == "action":
                action_result = execute_action(step)
                step_log.append({"step": step_id, "type": "action", "result": action_result})
                if not action_result.get("ok"):
                    results[step_id] = {"error": action_result.get("error", "action failed")}

            elif step_type == "wait":
                ms = step.get("ms", 500)
                time.sleep(ms / 1000)
                step_log.append({"step": step_id, "type": "wait", "ms": ms})

            elif step_type == "loop":
                collected = []
                for iteration in range(step.get("max_iterations", 10)):
                    content = read_current_screen(step.get("app", ""), step.get("page", ""))
                    answer = ask_ollama(
                        f"Screen content:\n{content}\n\n"
                        f"Find: {step['find']}\n"
                        f"Already collected: {json.dumps(collected)}\n"
                        f"Stop condition: {step.get('until', 'no new items')}\n\n"
                        f"Return JSON: {{\"items\": [<new items>], \"done\": true/false}}"
                    )
                    new_items = answer.get("items", [])
                    if new_items:
                        collected.extend(new_items)
                    if answer.get("done", False) or not new_items:
                        break
                    # Scroll to get more
                    if step.get("scroll"):
                        execute_action({
                            "action": "scroll",
                            "target": app,
                            "direction": step["scroll"],
                            "amount": step.get("scroll_amount", 3)
                        })
                        time.sleep(0.3)

                results[step_id] = collected
                step_log.append({"step": step_id, "type": "loop", "iterations": iteration + 1,
                                "items_collected": len(collected)})

            elif step_type == "fallback":
                # Try the primary steps, fall back to catch steps on failure
                try_steps = step.get("try", [])
                catch_steps = step.get("catch", [])

                # Run try steps — check if any returned errors
                pre_results = dict(results)
                ok = run_steps(try_steps, depth + 1)

                # Check if any new results have errors or null values
                has_problem = False
                for k, v in results.items():
                    if k not in pre_results:
                        if v is None or (isinstance(v, dict) and v.get("error")):
                            has_problem = True
                            break

                if has_problem and catch_steps:
                    step_log.append({"step": step_id, "type": "fallback", "triggered": True})
                    learnings.append({
                        "fact": f"Primary approach failed, fallback was needed",
                        "context": f"fallback triggered, app={app}"
                    })
                    run_steps(catch_steps, depth + 1)
                else:
                    step_log.append({"step": step_id, "type": "fallback", "triggered": False})

            elif step_type == "cli_query":
                # Direct CLI-Anything query — skip AT-SPI entirely
                cli_app = step.get("app", app)
                cli_cmd = step.get("command", "")
                if isinstance(cli_cmd, list):
                    cli_cmd = " ".join(cli_cmd)
                cli_result = None
                if _CLI_AVAILABLE and cli_cmd:
                    entry = cli_lookup(cli_app)
                    if entry:
                        cli_result = run_cli(entry, cli_cmd, timeout=step.get("timeout", 10))
                if cli_result is not None:
                    results[step_id] = cli_result
                    step_log.append({"step": step_id, "type": "cli_query", "tier": "cli"})
                else:
                    # Fall back to AT-SPI query if CLI fails
                    content = read_current_screen(cli_app)
                    find = step.get("find", cli_cmd)
                    answer = tiered_query(find, content, last_atspi,
                                          PLAN_SYSTEM, app=cli_app)
                    results[step_id] = answer.get("value", answer)
                    step_log.append({"step": step_id, "type": "cli_query",
                                    "tier": answer.get("tier", "fallback")})

            elif step_type == "read":
                # Just read and store the current screen content
                content = read_current_screen()
                results[step_id] = content[:2000]  # truncate for result
                step_log.append({"step": step_id, "type": "read", "chars": len(content)})

        return True

    # ── Execute ──
    t0 = time.time()
    run_steps(steps)
    elapsed = round((time.time() - t0) * 1000)

    # Save any learnings
    save_site_knowledge(app, url, learnings)

    return {
        "results": results,
        "_meta": {
            "model": get_model(),
            "app": app,
            "elapsed_ms": elapsed,
            "steps_executed": len(step_log),
            "learnings": len(learnings),
        },
        "_log": step_log,
    }


# ─── Level 3: Routines ───────────────────────────────────────

def save_routine(name: str, plan: dict, description: str = ""):
    """Save a plan as a named routine."""
    routine = {
        "name": name,
        "description": description,
        "plan": plan,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "run_count": 0,
    }
    path = ROUTINES_DIR / f"{name}.json"
    path.write_text(json.dumps(routine, indent=2))
    return {"saved": name, "path": str(path)}


def run_routine(name: str) -> dict:
    """Load and execute a saved routine."""
    path = ROUTINES_DIR / f"{name}.json"
    if not path.exists():
        return {"error": f"Routine '{name}' not found. Available: {list_routines()}"}

    routine = json.loads(path.read_text())
    result = execute_plan(routine["plan"])

    # Update run count
    routine["run_count"] = routine.get("run_count", 0) + 1
    routine["last_run"] = time.strftime("%Y-%m-%d %H:%M")
    path.write_text(json.dumps(routine, indent=2))

    result["_routine"] = name
    return result


def list_routines() -> list:
    """List all saved routines."""
    routines = []
    for f in ROUTINES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            routines.append({
                "name": data["name"],
                "description": data.get("description", ""),
                "run_count": data.get("run_count", 0),
                "last_run": data.get("last_run", "never"),
            })
        except Exception:
            pass
    return routines


# ─── CLI ──────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "usage": {
                "read": "costa-nav read <app> — raw AT-SPI dump",
                "query": "costa-nav query '{json}' — batch questions via Ollama",
                "plan": "costa-nav plan '{json}' — conditional plan execution",
                "routine": "costa-nav routine <name> — run saved routine",
                "routine-save": "costa-nav routine-save <name> '{plan_json}' — save routine",
                "routine-list": "costa-nav routine-list — list saved routines",
                "screen": "costa-nav screen — desktop state",
                "apps": "costa-nav apps — list accessible apps",
                "knowledge": "costa-nav knowledge [app] — show loaded knowledge",
                "cli-registry": "costa-nav cli-registry [list|refresh|check <app>] — CLI-Anything wrappers",
            }
        }, indent=2))
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "query":
        request = json.loads(sys.argv[2])
        print(json.dumps(handle_query(request), indent=2))

    elif cmd == "plan":
        plan = json.loads(sys.argv[2])
        print(json.dumps(execute_plan(plan), indent=2))

    elif cmd == "read":
        app = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(read_atspi(app), indent=2))

    elif cmd == "screen":
        print(read_screen_state())

    elif cmd == "apps":
        print(json.dumps(list_atspi_apps(), indent=2))

    elif cmd == "routine":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Specify routine name"}))
            sys.exit(1)
        print(json.dumps(run_routine(sys.argv[2]), indent=2))

    elif cmd == "routine-save":
        if len(sys.argv) < 4:
            print(json.dumps({"error": "Usage: routine-save <name> '{plan_json}'"}))
            sys.exit(1)
        name = sys.argv[2]
        plan = json.loads(sys.argv[3])
        desc = sys.argv[4] if len(sys.argv) > 4 else ""
        print(json.dumps(save_routine(name, plan, desc), indent=2))

    elif cmd == "routine-list":
        print(json.dumps(list_routines(), indent=2))

    elif cmd == "knowledge":
        app = sys.argv[2] if len(sys.argv) > 2 else ""
        result = {"tool_knowledge": load_tool_knowledge()[:2000]}
        if app:
            result["site_knowledge"] = load_site_knowledge(app)
        # List all site knowledge files
        result["site_files"] = [f.name for f in SITE_KNOWLEDGE_DIR.glob("*.md")]
        print(json.dumps(result, indent=2))

    elif cmd == "cli-registry":
        if not _CLI_AVAILABLE:
            print(json.dumps({"error": "CLI registry module not available"}))
            sys.exit(1)
        from cli_registry import list_registry, refresh_registry, lookup as _lookup
        subcmd = sys.argv[2] if len(sys.argv) > 2 else "list"
        if subcmd == "list":
            print(json.dumps(list_registry(), indent=2))
        elif subcmd == "refresh":
            refresh_registry()
            print(json.dumps(list_registry(), indent=2))
        elif subcmd == "check":
            app_name = sys.argv[3] if len(sys.argv) > 3 else ""
            entry = _lookup(app_name) if app_name else None
            if entry:
                print(json.dumps({"available": True, **entry}, indent=2))
            else:
                print(json.dumps({"available": False, "app": app_name}))
        else:
            print(json.dumps({"error": f"Unknown cli-registry subcommand: {subcmd}"}))

    elif cmd == "learn":
        # Manual learning entry: costa-nav learn <app> "fact to remember"
        if len(sys.argv) < 4:
            print(json.dumps({"error": "Usage: learn <app> 'fact'"}))
            sys.exit(1)
        app = sys.argv[2]
        fact = sys.argv[3]
        save_site_knowledge(app, "", [{"fact": fact, "context": "manual entry"}])
        print(json.dumps({"saved": True, "app": app, "fact": fact}))

    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
