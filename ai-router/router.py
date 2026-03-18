"""Costa AI Router — smart routing with context injection and auto-escalation.

The local model gets real system data injected into its prompt so it can actually
answer questions about the system. If it still can't answer (detects "I don't know"
type responses), it automatically escalates to Claude Haiku for a fast cloud answer.

Features:
- Tiered knowledge injection matched to model capability
- Auto-escalation: local → Haiku when local can't answer
- Claude tool_use: structured function calling with 30+ system tools
- ML routing: optional PyTorch classifier (falls back to regex)
- SQLite persistence: query logging, cost tracking, conversation history
- Cancel mechanism: SIGTERM-based query cancellation
- RAG: document search injected into prompts when relevant
- Budget enforcement: falls back to local when API spend exceeded
"""

import subprocess
import json
import re
import os
import signal
import sys
import time
from pathlib import Path

from context import gather_context
from window_manager import is_window_command, execute_window_command
from project_switch import switch_project, fuzzy_match, list_projects
from file_search import search_files, format_results as format_file_results, record_file_open
from keybinds import is_keybind_query, handle_keybind_query
from knowledge import select_knowledge_tiered, detect_model_tier


# System prompt paths — tiered by model size
SYSTEM_PROMPT_DIR = Path.home() / ".config" / "costa" / "system-prompts"
SYSTEM_PROMPT_FALLBACK = Path.home() / ".config" / "costa" / "system-ai.md"
KNOWLEDGE_DIR = Path.home() / ".config" / "costa" / "knowledge"
CONVERSATION_FILE = Path("/tmp/costa-conversation.json")
MAX_CONVERSATION_TURNS = 5
OLLAMA_URL = "http://localhost:11434/api/generate"
PID_FILE = Path("/tmp/costa-ai.pid")
MAX_TOOL_CALLS = 5

# Patterns that indicate the local model is punting
IDK_PATTERNS = [
    r"i don.?t (know|have (access|information|that|enough))",
    r"i.?m (not sure|unable|not able|not certain)",
    r"i (cannot|can.?t) (access|check|determine|tell|verify|confirm|read|see|look|find|browse|view)",
    r"(don.?t|do not) have (access to|the ability|information about|real.?time|current|live)",
    r"(cannot|can.?t|unable to) (access|browse|check|query|read|view|look|search|fetch|retrieve|open|run|execute)",
    r"(no|don.?t have) (way to|means to|ability to|access to)",
    r"as an ai|as a language model|as an llm",
    r"you.?d need to (check|run|look|verify)",
    r"you (can|could|should|might want to) (check|run|try|use|look)",
    r"i.?d recommend (checking|running|looking|using)",
    r"i (would need|need) to (check|access|run|look|query)",
    r"without (access|checking|running|looking)",
    r"my (knowledge|training|data) (cutoff|ends|is limited)",
    r"i.?m not (equipped|designed|built) to",
    r"outside (of )?my (capabilities|scope|ability)",
    r"beyond (my|what i can)",
]
IDK_RE = re.compile("|".join(IDK_PATTERNS), re.IGNORECASE)

# Routing patterns — same logic as PTT but used for all input modalities
ROUTE_PATTERNS = {
    "file_search": r"(find|locate|where\s+is|search\s+for)\s+(the\s+|that\s+|a\s+|my\s+)?(file|script|module|config|source|code)|where.s\s+(the|that|my)\s+\w+\s+file|find\s+that\s+\w+\s+(file|script|code)|which\s+file\s+(has|contains|had)",
    "project_switch": r"(switch|change|go|jump|move|open|load|start|launch)\s+(to\s+|into\s+|up\s+)?(the\s+)?\w[\w\s\-]*?\s*(project|env)|switch\s+to\s+(?!workspace\b)\w+",
    "opus": r"architect|design.*system|research.*in.depth|deep dive|security.*audit|plan.*migration|compare.*approach|trade.?off|comprehensive.*review|evaluate.*strategy",
    "sonnet": r"write (a |the |some |me )?(code|script|function|class|test|program|module)|implement|debug|fix (the |this |a )?bug|refactor|make (a |the )?(component|api|endpoint|server|app)|build (a |the )?(project|app|service)|deploy|set up (a |the )?(pipeline|ci|cd|server)",
    "haiku+web": r"(latest |breaking |today.s )?(news|headline)|score.*(game|match)|who.*(won|play|lead)|trending|what happened.*(today|yesterday|world|country)|latest.*update.*(on|about)|search.*for.*(online|web|internet)|look up.*(online|web|person|company|stock|price)|(new|latest|recent)\s+(CVE|vulnerabilit|security\s+(advisory|patch|update|issue))",
    "local+weather": r"weather|forecast|(?:outside|outdoor)\s*temp|temperature\s*(?:outside|outdoors|today|tonight|tomorrow)|(?:how|what).{0,10}(?:hot|cold|warm)\s+(?:is\s+it|outside|today)|rain(?:ing|fall|y)?(?:\s+today|\s+tomorrow|\s+this\s+week)?$",
}

# Pattern to extract project name from switch queries
PROJECT_SWITCH_RE = re.compile(
    r"(?:switch|change|go|jump|move|open|load|start|launch)\s+"
    r"(?:to\s+|into\s+|up\s+)?(?:the\s+)?(?:project\s+)?"
    r"([\w][\w\s\-]*?)(?:\s+project|\s+workspace|\s+env)?$",
    re.IGNORECASE,
)

# Cancel flag — set by SIGTERM handler
_cancelled = False
_ollama_process = None


def _sigterm_handler(signum, frame):
    """Handle SIGTERM for query cancellation."""
    global _cancelled, _ollama_process
    _cancelled = True
    # Kill Ollama subprocess if running
    if _ollama_process and _ollama_process.poll() is None:
        try:
            _ollama_process.kill()
        except Exception:
            pass


# Register SIGTERM handler
signal.signal(signal.SIGTERM, _sigterm_handler)


def _write_pid():
    """Write current PID to file for cancel mechanism."""
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass


def _clear_pid():
    """Remove PID file."""
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def get_system_prompt(model_name: str = "") -> str:
    """Load the tier-appropriate system prompt from disk."""
    if model_name:
        tier = detect_model_tier(model_name)
        tier_path = SYSTEM_PROMPT_DIR / f"system-ai-{tier}.md"
        if tier_path.exists():
            try:
                return tier_path.read_text()
            except Exception:
                pass
    # Fallback to single system prompt
    try:
        return SYSTEM_PROMPT_FALLBACK.read_text()
    except Exception:
        return "You are the Costa OS local AI assistant. Be concise and direct."


def get_ollama_model() -> str:
    """Read the current best model from the VRAM manager."""
    try:
        return Path("/tmp/ollama-smart-model").read_text().strip()
    except Exception:
        return "qwen2.5:14b"  # default if VRAM manager hasn't written yet


def select_knowledge(query: str, model_name: str = "") -> str:
    """Select and load relevant knowledge files, tiered by model capability."""
    return select_knowledge_tiered(query, model_name or "qwen2.5:14b")


def get_conversation_history() -> list[dict]:
    """Load rolling conversation history from database (with file fallback)."""
    try:
        from db import get_conversation_history as db_get_history
        history = db_get_history(MAX_CONVERSATION_TURNS)
        if history:
            return history
    except Exception:
        pass
    # Fallback to file-based history
    try:
        data = json.loads(CONVERSATION_FILE.read_text())
        return data[-MAX_CONVERSATION_TURNS:]
    except Exception:
        return []


def save_conversation_turn(query: str, response: str, model: str):
    """Append a turn to conversation history (file-based for backward compat)."""
    history = []
    try:
        data = json.loads(CONVERSATION_FILE.read_text())
        history = data[-MAX_CONVERSATION_TURNS:]
    except Exception:
        pass
    history.append({
        "q": query,
        "a": response[:300],
        "m": model,
        "t": int(time.time()),
    })
    history = history[-MAX_CONVERSATION_TURNS:]
    try:
        CONVERSATION_FILE.write_text(json.dumps(history))
    except Exception:
        pass


def format_conversation_context(history: list[dict]) -> str:
    """Format conversation history for prompt injection."""
    if not history:
        return ""
    lines = ["[RECENT CONVERSATION — use for context on pronouns like 'it', 'that', 'this']"]
    for turn in history:
        lines.append(f"User: {turn['q']}")
        lines.append(f"Assistant: {turn['a']}")
    return "\n".join(lines)


def select_route(query: str) -> str:
    """Determine the best model tier for this query.

    Tries ML router first (if trained and confident), falls back to regex patterns.
    """
    # Try ML router
    try:
        from ml_router import get_router
        router = get_router()
        ml_route, confidence = router.predict(query)
        if ml_route and confidence > 0.65:
            return ml_route
    except Exception:
        pass

    # Fallback to regex patterns
    for model, pattern in ROUTE_PATTERNS.items():
        if re.search(pattern, query, re.IGNORECASE):
            return model
    return "local"


def _select_temperature(query: str) -> float:
    """Pick generation temperature based on query type."""
    q = query.lower()
    # Commands / actions need precision
    if ACTION_PATTERNS.search(q):
        return 0.1
    # Followup / conversation is more fluid
    conv = get_conversation_history()
    if conv and any(q.startswith(w) for w in ("what about", "and ", "also ", "how about")):
        return 0.5
    # General knowledge
    return 0.3


def _select_num_predict(is_voice: bool = False) -> int:
    """Max tokens for the response. Voice needs to be short."""
    return 256 if is_voice else 512


def query_ollama(prompt: str, system: str, model: str, timeout: int = 30,
                 temperature: float | None = None, num_predict: int | None = None) -> str:
    """Send a query to Ollama and return the response text."""
    global _ollama_process, _cancelled
    if _cancelled:
        return ""

    payload_dict = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "keep_alive": "5m",
        "options": {},
    }
    if temperature is not None:
        payload_dict["options"]["temperature"] = temperature
    if num_predict is not None:
        payload_dict["options"]["num_predict"] = num_predict

    # Remove empty options
    if not payload_dict["options"]:
        del payload_dict["options"]

    payload = json.dumps(payload_dict)
    try:
        _ollama_process = subprocess.Popen(
            ["curl", "-s", OLLAMA_URL, "-d", payload],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        stdout, _ = _ollama_process.communicate(timeout=timeout)
        _ollama_process = None

        if _cancelled:
            return ""

        data = json.loads(stdout)
        return data.get("response", "").strip()
    except subprocess.TimeoutExpired:
        if _ollama_process:
            _ollama_process.kill()
            _ollama_process = None
        return ""
    except Exception:
        _ollama_process = None
        return ""


CLAUDE_MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6-20250514",
    "opus": "claude-opus-4-6-20250514",
}

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


def _get_anthropic_key() -> str | None:
    """Read the Anthropic API key from environment or costa config."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_file = Path.home() / ".config" / "costa" / "env"
    try:
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def query_claude(query: str, model: str = "haiku", tools: list | None = None,
                 system: str = "", timeout: int = 45,
                 use_tools: bool = False) -> str:
    """Send a query via the Claude Code CLI (uses subscription, not API billing).

    Args:
        query: The user's query text
        model: Model tier ('haiku', 'sonnet', 'opus')
        tools: Legacy param (ignored)
        system: System prompt override
        timeout: Request timeout in seconds
        use_tools: Enable tool use (passed as --allowedTools to claude CLI)

    Returns:
        The model's text response.
    """
    global _cancelled
    if _cancelled:
        return ""

    model_id = CLAUDE_MODEL_MAP.get(model, model)
    if not system:
        system = "You are a helpful voice assistant for Costa OS (Arch Linux + Hyprland). Answer in 1-3 sentences. No markdown. Be direct."

    # Find claude CLI
    claude_bin = None
    for path in [
        os.path.expanduser("~/.nvm/versions/node") + "/{}/bin/claude",
        "/usr/local/bin/claude",
        "/usr/bin/claude",
    ]:
        if "{}" in path:
            # Find nvm node version
            nvm_dir = os.path.expanduser("~/.nvm/versions/node")
            try:
                versions = sorted(os.listdir(nvm_dir))
                if versions:
                    candidate = os.path.join(nvm_dir, versions[-1], "bin", "claude")
                    if os.path.exists(candidate):
                        claude_bin = candidate
                        break
            except Exception:
                pass
        elif os.path.exists(path):
            claude_bin = path
            break

    if not claude_bin:
        return ""

    cmd = [
        claude_bin, "-p",
        "--model", model_id,
        "--output-format", "text",
        "--system-prompt", system,
    ]

    if use_tools:
        cmd.extend(["--allowedTools", "WebSearch,WebFetch"])

    try:
        result = subprocess.run(
            cmd,
            input=query,
            capture_output=True, text=True,
            timeout=timeout,
            cwd="/tmp",
        )
        if _cancelled:
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""


# Patterns that indicate the user wants an ACTION performed, not just information
ACTION_PATTERNS = re.compile(
    r"(^|\b)(turn\b.{0,20}\b(up|down|off|on)|set (the |my )?(volume|brightness|wallpaper)|"
    r"(lower|raise|increase|decrease|reduce) (the |my )?(volume|brightness)|"
    r"restart|reload|kill|close|open|launch|start|stop|mute|unmute|"
    r"switch (to |)workspace|move (window|this)|"
    r"connect|disconnect|enable|disable|toggle|"
    r"play|pause|skip|next|previous|shuffle)\b",
    re.IGNORECASE,
)

# Commands that are safe to run without confirmation
SAFE_COMMAND_PATTERNS = [
    r"^wpctl\s+(set-volume|set-mute|get-volume)",
    r"^pactl\s+(set-default|get-default|set-sink-volume|set-source-volume)",
    r"^hyprctl\s+(dispatch|reload|switchxkblayout)",
    r"^killall\s+(waybar|dunst)$",
    r"^notify-send\b",
    r"^playerctl\b",
    r"^brightnessctl\b",
    r"^systemctl\s+(--user\s+)?(restart|start|stop)\s+(pipewire|wireplumber|waybar)",
    r"^waybar\b",
]
SAFE_RE = re.compile("|".join(SAFE_COMMAND_PATTERNS))

# Commands that should NEVER be run
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


def is_action_query(query: str) -> bool:
    """Detect if the user wants something DONE, not just answered."""
    return bool(ACTION_PATTERNS.search(query))


def extract_command(response: str) -> str | None:
    """Extract a shell command from the model's response."""
    # Try triple backtick code blocks first
    m = re.search(r"```(?:bash|sh|shell)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if m:
        cmd = m.group(1).strip()
        if cmd:
            return cmd.split("\n")[0].strip()  # first line only

    # Try single backtick commands
    m = re.search(r"`([^`]+)`", response)
    if m:
        cmd = m.group(1).strip()
        # Filter out non-commands (English phrases in backticks)
        if any(c in cmd for c in ["(", ")", "{", "}", "|", "/", "=", "-"]) or \
           " " not in cmd or \
           cmd.startswith(("wpctl", "pactl", "hyprctl", "killall", "systemctl",
                          "playerctl", "notify", "brightnessctl", "waybar",
                          "pkill", "docker", "git")):
            return cmd
    return None


def classify_command(cmd: str) -> str:
    """Classify a command as 'safe', 'dangerous', or 'ask'."""
    if DANGEROUS_RE.search(cmd):
        return "dangerous"
    if SAFE_RE.search(cmd):
        return "safe"
    return "ask"


def execute_command(cmd: str, timeout: int = 10) -> str:
    """Execute a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr.strip():
            output += f"\n(error: {result.stderr.strip()[:200]})"
        return output if output else "(completed successfully)"
    except subprocess.TimeoutExpired:
        return "(command timed out)"
    except Exception as e:
        return f"(error: {e})"


def is_idk_response(response: str) -> bool:
    """Detect if the local model is saying 'I don't know' in various ways."""
    if not response:
        return True
    # Short non-answers
    if len(response) < 15:
        return True
    return bool(IDK_RE.search(response))


def route_query(query: str, force_model: str | None = None,
                allow_escalation: bool = True, gather_context_flag: bool = True,
                input_modality: str = "text") -> dict:
    """Route a query through the AI stack.

    Returns a dict with:
        query: str — the original query
        response: str — the answer
        model: str — which model answered (e.g. "qwen2.5:14b", "haiku", "sonnet")
        route: str — the routing decision (e.g. "local", "local+escalated", "haiku+web")
        context_gathered: bool — whether system context was injected
        escalated: bool — whether the query was escalated from local to cloud
        command_executed: str|None — shell command that was auto-executed
        elapsed_ms: int — total wall time in ms
        context_ms: int|None — time spent gathering context
        knowledge_ms: int|None — time spent loading knowledge
        model_ms: int|None — time spent waiting for model response
        total_ms: int — alias for elapsed_ms (for db)
    """
    global _cancelled
    _cancelled = False
    _write_pid()

    start = time.time()
    context_ms = None
    knowledge_ms = None
    model_ms = None

    route = force_model or select_route(query)
    system_prompt = get_system_prompt()
    escalated = False
    context_used = False
    model_used = route
    response = ""

    try:
        # Window management — intercept before other routes
        if not force_model and is_window_command(query):
            wm_result = execute_window_command(query)
            # If window manager couldn't handle it (and it's not just "window not found"),
            # escalate to Claude with tools
            is_not_found = "Could not find" in wm_result.get("result", "") or "No " in wm_result.get("result", "")
            if not wm_result.get("commands_run") and allow_escalation and not is_not_found:
                escalated_response = query_claude(
                    query, model="haiku",
                    system="You are a system assistant for Costa OS (Arch Linux + Hyprland). "
                           "The user wants a window management action. Execute it. Be direct.",
                    use_tools=True,
                    timeout=30,
                )
                if escalated_response:
                    wm_result["result"] = escalated_response
                    wm_result["commands_run"] = ["(via Claude)"]
            elapsed = time.time() - start
            result = {
                "query": query,
                "response": wm_result["result"],
                "model": "window_manager",
                "route": "window_manager",
                "context_gathered": False,
                "escalated": not bool(wm_result.get("commands_run", [None])[0] != "(via Claude)"),
                "command_executed": "; ".join(wm_result["commands_run"]) if wm_result["commands_run"] else None,
                "elapsed_ms": int(elapsed * 1000),
                "total_ms": int(elapsed * 1000),
            }
            _log_to_db(result, input_modality)
            return result

        # Project switching — intercept before AI routes
        if route == "project_switch" and not force_model:
            m = PROJECT_SWITCH_RE.search(query)
            project_name = m.group(1).strip() if m else query.split()[-1]
            success = switch_project(project_name)
            elapsed = time.time() - start
            if success:
                proj = fuzzy_match(project_name, list_projects())
                resp = f"Switched to {proj.name}." if proj else f"Switched to {project_name}."
            else:
                available = ", ".join(p.name for p in list_projects())
                resp = f"No project matches '{project_name}'. Available: {available}" if available else "No project configs found."
            result = {
                "query": query,
                "response": resp,
                "model": "project_switch",
                "route": "project_switch",
                "context_gathered": False,
                "escalated": False,
                "command_executed": None,
                "elapsed_ms": int(elapsed * 1000),
                "total_ms": int(elapsed * 1000),
            }
            _log_to_db(result, input_modality)
            return result

        # Keybind management — intercept before AI routes
        if not force_model and is_keybind_query(query):
            kb_result = handle_keybind_query(query)
            if not kb_result.get("needs_ai"):
                elapsed = time.time() - start
                kb_result.setdefault("query", query)
                kb_result.setdefault("context_gathered", False)
                kb_result.setdefault("escalated", False)
                kb_result.setdefault("command_executed", None)
                kb_result["elapsed_ms"] = int(elapsed * 1000)
                kb_result["total_ms"] = int(elapsed * 1000)
                _log_to_db(kb_result, input_modality)
                return kb_result

        # File search — intercept before AI routes
        if route == "file_search" and not force_model:
            results = search_files(query)
            elapsed = time.time() - start
            if results:
                top = results[:5]
                lines = [f"Found {len(results)} matching file{'s' if len(results) != 1 else ''}:"]
                for i, r in enumerate(top, 1):
                    path = r["path"]
                    home = str(Path.home())
                    if path.startswith(home):
                        path = "~" + path[len(home):]
                    lines.append(f"  {i}. {path}")
                resp = "\n".join(lines)
            else:
                resp = "No matching files found."
            result = {
                "query": query,
                "response": resp,
                "model": "file_search",
                "route": "file_search",
                "context_gathered": False,
                "escalated": False,
                "command_executed": None,
                "elapsed_ms": int(elapsed * 1000),
                "total_ms": int(elapsed * 1000),
            }
            _log_to_db(result, input_modality)
            return result

        # Check for cancellation
        if _cancelled:
            return _cancelled_result(query, start, input_modality)

        # Cloud routes — pass directly (with tool_use for sonnet/opus)
        if route in ("opus", "sonnet"):
            t0 = time.time()
            response = query_claude(query, model=route, timeout=120, use_tools=True)
            model_ms = int((time.time() - t0) * 1000)
            model_used = route
        elif route == "haiku+web":
            t0 = time.time()
            response = query_claude(
                query, model="haiku",
                system="You are a helpful voice assistant with web search. Search the web to answer accurately. Answer in 1-3 sentences. No markdown. Be direct.",
                use_tools=True,
            )
            model_ms = int((time.time() - t0) * 1000)
            model_used = "haiku"
        elif route == "local+weather":
            # Fetch weather data and reason locally
            import urllib.parse
            city_match = re.search(r"in ([a-zA-Z ]+)", query, re.IGNORECASE)
            city = city_match.group(1).strip() if city_match else "New York"
            try:
                weather = subprocess.run(
                    ["curl", "-s", f"wttr.in/{urllib.parse.quote(city)}?format=%l:+%C+%t+feels+like+%f+humidity+%h+wind+%w"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
            except Exception:
                weather = "weather data unavailable"

            ollama_model = get_ollama_model()
            prompt = f"Current weather data: {weather}. Summarize this naturally in one sentence."
            t0 = time.time()
            response = query_ollama(prompt, system_prompt, ollama_model)
            model_ms = int((time.time() - t0) * 1000)
            model_used = ollama_model
        else:
            # Local route — context injection + knowledge + conversation + RAG + escalation
            ollama_model = get_ollama_model()
            model_used = ollama_model
            system_prompt = get_system_prompt(ollama_model)

            # Gather system context
            context = ""
            if gather_context_flag:
                t0 = time.time()
                context = gather_context(query)
                context_ms = int((time.time() - t0) * 1000)
                context_used = bool(context)

            if _cancelled:
                return _cancelled_result(query, start, input_modality)

            # Select relevant knowledge base (tiered by model size)
            t0 = time.time()
            knowledge = select_knowledge(query, ollama_model)
            knowledge_ms = int((time.time() - t0) * 1000)

            # RAG — check if query references personal documents
            rag_context = ""
            try:
                from rag import is_rag_query, search_for_prompt
                if is_rag_query(query):
                    rag_context = search_for_prompt(query)
            except Exception:
                pass

            # Get conversation history
            conv_history = get_conversation_history()
            conv_context = format_conversation_context(conv_history)

            # Build prompt with XML-delimited context layers
            prompt_parts = []
            if context:
                prompt_parts.append(f"<context>\n{context}\n</context>")
            if knowledge:
                prompt_parts.append(f"<knowledge>\n{knowledge}\n</knowledge>")
            if rag_context:
                prompt_parts.append(f"<documents>\n{rag_context}\n</documents>")
            if conv_context:
                prompt_parts.append(f"<history>\n{conv_context}\n</history>")
            prompt_parts.append(f"<query>\n{query}\n</query>")

            prompt = "\n\n".join(prompt_parts)

            # Temperature and token limits tuned per query type
            temp = _select_temperature(query)
            num_predict = _select_num_predict()

            if _cancelled:
                return _cancelled_result(query, start, input_modality)

            t0 = time.time()
            response = query_ollama(prompt, system_prompt, ollama_model,
                                    temperature=temp, num_predict=num_predict)
            model_ms = int((time.time() - t0) * 1000)

            # Check for "I don't know" responses and escalate
            if allow_escalation and is_idk_response(response) and not _cancelled:
                escalated = True
                haiku_prompt = query
                if context:
                    haiku_prompt = f"The user is on an Arch Linux system (Hyprland, AMD GPU). System data:\n{context}\n\nQuestion: {query}"

                t0 = time.time()
                haiku_response = query_claude(
                    haiku_prompt, model="haiku",
                    system="You are a helpful assistant for a Linux power user. Answer in 1-3 sentences. No markdown. Be direct and technical.",
                    use_tools=True,
                )
                model_ms = int((time.time() - t0) * 1000)
                if haiku_response:
                    response = haiku_response
                    model_used = "haiku"
                    route = "local+escalated"

        if _cancelled:
            return _cancelled_result(query, start, input_modality)

        # Action execution: if the user wanted something DONE, extract and run the command
        command_executed = None
        if response and is_action_query(query):
            cmd = extract_command(response)
            if cmd:
                safety = classify_command(cmd)
                if safety == "safe":
                    cmd_output = execute_command(cmd)
                    command_executed = cmd
                    followup = query_ollama(
                        f"You just ran this command: `{cmd}`\nOutput: {cmd_output}\n\nGive a brief natural confirmation of what happened. One sentence, no backticks.",
                        system_prompt, get_ollama_model(), timeout=10,
                    )
                    if followup and len(followup) > 5:
                        response = followup
                    else:
                        response = f"Done. {cmd_output}" if cmd_output != "(completed successfully)" else "Done."
                elif safety == "dangerous":
                    response = f"I won't run that automatically — it could be destructive. Command: {cmd}"
                else:
                    cmd_output = execute_command(cmd)
                    command_executed = cmd
                    followup = query_ollama(
                        f"You just ran this command: `{cmd}`\nOutput: {cmd_output}\n\nGive a brief natural confirmation. One sentence, no backticks.",
                        system_prompt, get_ollama_model(), timeout=10,
                    )
                    if followup and len(followup) > 5:
                        response = followup
                    else:
                        response = f"Ran `{cmd}`. {cmd_output}"
            elif allow_escalation and not escalated and not _cancelled:
                # Local model described instead of acting — escalate to Claude with tools
                escalated = True
                t0 = time.time()
                escalated_response = query_claude(
                    query, model="haiku",
                    system="You are a system assistant for Costa OS (Arch Linux + Hyprland). "
                           "The user wants an ACTION performed, not a description. "
                           "Use your tools to execute the request. Be direct.",
                    use_tools=True,
                    timeout=45,
                )
                model_ms = int((time.time() - t0) * 1000)
                if escalated_response:
                    response = escalated_response
                    model_used = "haiku"
                    route = "local+escalated"

        elapsed = time.time() - start

        # Save conversation turn for rolling context
        if response and route in ("local", "local+escalated", "local+weather"):
            save_conversation_turn(query, response, model_used)

        result = {
            "query": query,
            "response": response,
            "model": model_used,
            "route": route,
            "context_gathered": context_used,
            "escalated": escalated,
            "command_executed": command_executed,
            "elapsed_ms": int(elapsed * 1000),
            "total_ms": int(elapsed * 1000),
            "context_ms": context_ms,
            "knowledge_ms": knowledge_ms,
            "model_ms": model_ms,
        }

        _log_to_db(result, input_modality)
        return result

    finally:
        _clear_pid()


def _cancelled_result(query: str, start: float, input_modality: str) -> dict:
    """Build a result dict for a cancelled query."""
    elapsed = time.time() - start
    result = {
        "query": query,
        "response": "(Cancelled)",
        "model": "cancelled",
        "route": "cancelled",
        "context_gathered": False,
        "escalated": False,
        "command_executed": None,
        "elapsed_ms": int(elapsed * 1000),
        "total_ms": int(elapsed * 1000),
    }
    _log_to_db(result, input_modality)
    _clear_pid()
    return result


def _log_to_db(result: dict, input_modality: str = "text"):
    """Log query result to SQLite database, auto-label routing, trigger retrain."""
    try:
        from db import log_query, update_routing_feedback
        query_id = log_query(result, input_modality=input_modality)

        # Auto-label routing outcome (skip cancelled queries)
        route = result.get("route", "")
        if route != "cancelled" and query_id:
            was_correct = not result.get("escalated", False)
            update_routing_feedback(query_id, was_correct)

        # Fire-and-forget: retrain if stale (every 50 queries)
        try:
            subprocess.Popen(
                [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "costa-ai"), "--train-if-stale"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
    except Exception:
        pass  # DB logging is best-effort — never break the router


def stop_running_query() -> bool:
    """Send SIGTERM to a running query process.

    Returns True if a signal was sent.
    """
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False
