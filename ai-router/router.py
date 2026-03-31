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
import yaml
from pathlib import Path

from context import gather_context
from window_manager import is_window_command, execute_window_command

# Meta queries — questions about Costa OS itself, handled before routing
META_PATTERN = re.compile(
    r"\b(what can you do|what are you|how do I use (costa|this|the ai)|how does .{0,10}(ai|costa|routing|router) work|"
    r"(show me |what.s |my )(usage|stats|history)|costa.?ai (usage|stats|help)|"
    r"what models are (available|loaded|running)|how do I (use|train) (the |this )?(router|costa|ai)|"
    r"list (available )?models|costa help|what commands (do you|can you)|"
    r"what time is it|what.s the (time|date)|any updates (available|pending)|"
    r"check for updates|what.s the weather)\b",
    re.IGNORECASE,
)

# Multi-intent split patterns
_SPLIT_RE = re.compile(
    r"\s+(?:and\s+(?:then\s+)?(?:also\s+)?|then\s+|also\s+|,\s*(?:and\s+)?(?:then\s+)?)"
    r"(?=\b(?:open|close|move|put|tile|switch|find|show|check|start|stop|run|set|change|"
    r"install|write|create|make|play|search|locate|list|what|how|is|where|kill|restart|float|resize|reboot|shutdown|update|mute|unmute|lower|raise|clean)\b)",
    re.IGNORECASE,
)


def _split_multi_intent(query: str) -> list[str]:
    """Split a multi-intent query into individual queries.

    'install neovim and set it as my default editor' → ['install neovim', 'set it as my default editor']
    'check if postgres is running and show me the logs' → ['check if postgres is running', 'show me the logs']

    Returns a list with 1 element if the query is single-intent.
    """
    parts = _SPLIT_RE.split(query)
    # Filter empty parts and very short fragments
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
    return parts if len(parts) > 1 else [query]


def _handle_meta(query: str) -> dict | None:
    """Handle meta-queries about Costa OS itself."""
    if not META_PATTERN.search(query):
        return None

    q = query.lower()

    if re.search(r"what can you do|what are you|costa help|how do i use (costa|this|the ai)|what are you capable", q):
        return {
            "response": "I can manage your system, search files, control windows, write code, "
                        "research topics, and answer questions. Ask naturally — voice, text, or keybinds. "
                        "Try: 'what GPU do I have', 'move firefox to workspace 3', or 'write a python script'.",
            "model": "meta", "route": "meta",
        }

    if re.search(r"usage|stats", q):
        try:
            from db import get_usage_stats
            stats = get_usage_stats("today")
            return {
                "response": f"Today: {stats['total_queries']} queries, ${stats['total_cost']:.4f} cost, "
                            f"{stats['avg_latency_ms']}ms avg, {stats['escalation_rate']:.0%} escalation rate.",
                "model": "meta", "route": "meta",
            }
        except Exception:
            pass

    if re.search(r"models? (are |)(available|loaded|running)", q):
        try:
            model = _smart_model_file().read_text().strip()
            return {
                "response": f"Local: {model} (via Ollama). Cloud: Claude Haiku (web), Sonnet (code), Opus (architecture). "
                            f"Routing is automatic — local for fast queries, cloud when needed.",
                "model": "meta", "route": "meta",
            }
        except Exception:
            pass

    if re.search(r"(how does|how do).*(rout|ai|costa).*work", q):
        return {
            "response": "Queries go through an MLP classifier (instant) with LLM fallback for ambiguous cases (~300ms). "
                        "Routes: local (Ollama), haiku+web (live data), sonnet (code), opus (architecture), "
                        "file_search, window_manager. Every query trains the model via auto-labeling.",
            "model": "meta", "route": "meta",
        }

    if re.search(r"train.*(router|model)", q):
        return {
            "response": "Run 'costa-ai --train-router' to retrain the MLP on logged queries. "
                        "It retrains automatically every 50 queries. "
                        "Use 'costa-ai --train-router --eval' for accuracy report.",
            "model": "meta", "route": "meta",
        }

    # Time/date
    if re.search(r"what time|what.s the time|what.s the date", q):
        from datetime import datetime
        now = datetime.now()
        return {
            "response": now.strftime("It's %I:%M %p on %A, %B %d."),
            "model": "meta", "route": "meta",
        }

    # Weather — delegate to the existing weather script
    if re.search(r"weather", q):
        try:
            weather_out = subprocess.run(
                [str(Path.home() / ".config/costa/scripts/weather.sh")],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            import json as _json
            data = _json.loads(weather_out)
            tooltip = data.get("tooltip", "Weather unavailable")
            return {
                "response": tooltip.replace("\\n", "\n"),
                "model": "meta", "route": "meta",
            }
        except Exception:
            pass

    # Updates
    if re.search(r"updates? (available|pending)|check for updates", q):
        try:
            official = subprocess.run(
                ["checkupdates"], capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            aur = subprocess.run(
                ["yay", "-Qua"], capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            official_count = len(official.splitlines()) if official else 0
            aur_count = len(aur.splitlines()) if aur else 0
            total = official_count + aur_count
            if total == 0:
                resp = "System is up to date."
            else:
                resp = f"{total} updates available ({official_count} official, {aur_count} AUR)."
                if official_count <= 10 and official:
                    resp += "\n" + official
            return {
                "response": resp,
                "model": "meta", "route": "meta",
            }
        except Exception:
            pass

    return None
from project_switch import switch_project, fuzzy_match, list_projects
from file_search import search_files, format_results as format_file_results, record_file_open
from keybinds import is_keybind_query, handle_keybind_query
from knowledge import select_knowledge_tiered, detect_model_tier
from ml_router import select_local_model, CATEGORY_MODEL_PREFS

def _smart_model_file():
    """Smart model path: XDG_RUNTIME_DIR first, /tmp fallback."""
    xdg = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "costa/ollama-smart-model"
    return xdg if xdg.exists() else Path("/tmp/ollama-smart-model")



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
    "opus": r"architect|design.*system|research.*in.depth|deep dive|security.*audit|plan.*migration|compare.*approach|trade.?off|comprehensive.*review|evaluate.*strategy|threat\s*model|incident\s*response|capacity\s*plan",
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


def get_ollama_model() -> str | None:
    """Read the current best model from the VRAM manager.
    Returns None if no local model is available (gaming mode / no GPU).
    """
    try:
        model = _smart_model_file().read_text().strip()
        if not model or model == "none":
            return None
        return model
    except Exception:
        return None


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


def select_route(query: str, file_path: str | None = None) -> str:
    """Determine the best model tier for this query.

    Tries ML router first (if trained and confident), falls back to regex patterns.
    """
    # Try ML router
    try:
        from ml_router import get_router
        router = get_router()
        ml_route, confidence = router.predict(query, file_path=file_path)
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

    # Quick check: is Ollama even reachable? (avoids 30s timeout)
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
    except Exception:
        return ""  # Ollama not running, caller will escalate

    payload_dict = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "keep_alive": "5m",
        "options": {},
    }
    # Qwen3.5 models default to "thinking mode" which consumes the entire
    # num_predict budget on chain-of-thought before generating visible output.
    # Disable thinking to get direct responses within the token budget.
    if "qwen3.5" in model or "qwen3" in model:
        payload_dict["think"] = False
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
        resp = data.get("response", "").strip()
        # Truncate if model switches to Chinese/other scripts (qwen2.5 quirk)
        # CJK Unified Ideographs range: U+4E00–U+9FFF
        for i, ch in enumerate(resp):
            if '\u4e00' <= ch <= '\u9fff':
                resp = resp[:i].rstrip('，。、：；')
                break
        return resp
    except subprocess.TimeoutExpired:
        if _ollama_process:
            _ollama_process.kill()
            _ollama_process = None
        return ""
    except Exception:
        _ollama_process = None
        return ""


CLAUDE_MODEL_MAP = {
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
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
        return "Claude Code is not installed or not on PATH. Open a terminal and run 'claude' to set it up."

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


# ---------------------------------------------------------------------------
# Multi-provider support
# ---------------------------------------------------------------------------

_PROVIDERS_CONFIG: dict | None = None
_ROUTING_CONFIG: dict | None = None


def _load_providers() -> dict:
    """Load provider configuration from YAML."""
    global _PROVIDERS_CONFIG
    if _PROVIDERS_CONFIG is not None:
        return _PROVIDERS_CONFIG

    config_paths = [
        Path.home() / ".config" / "costa" / "providers.yaml",
        Path(__file__).parent.parent / "configs" / "costa" / "providers.yaml",
    ]
    for p in config_paths:
        if p.exists():
            try:
                _PROVIDERS_CONFIG = yaml.safe_load(p.read_text()).get("providers", {})
                return _PROVIDERS_CONFIG
            except Exception:
                pass
    _PROVIDERS_CONFIG = {}
    return _PROVIDERS_CONFIG


def _load_routing() -> dict:
    """Load routing rules from YAML."""
    global _ROUTING_CONFIG
    if _ROUTING_CONFIG is not None:
        return _ROUTING_CONFIG

    config_paths = [
        Path.home() / ".config" / "costa" / "routing.yaml",
        Path(__file__).parent.parent / "configs" / "costa" / "routing.yaml",
    ]
    for p in config_paths:
        if p.exists():
            try:
                _ROUTING_CONFIG = yaml.safe_load(p.read_text()).get("routing_rules", {})
                return _ROUTING_CONFIG
            except Exception:
                pass
    _ROUTING_CONFIG = {}
    return _ROUTING_CONFIG


def _get_provider_key(provider_name: str) -> str | None:
    """Get API key for a provider from environment or costa config."""
    providers = _load_providers()
    config = providers.get(provider_name, {})
    env_var = config.get("api_key_env", "")
    if not env_var:
        return None

    # Check environment
    key = os.environ.get(env_var)
    if key:
        return key

    # Check ~/.config/costa/env
    env_file = Path.home() / ".config" / "costa" / "env"
    try:
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{env_var}="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _is_provider_available(provider_name: str) -> bool:
    """Check if a provider is enabled and has credentials (or is free tier)."""
    providers = _load_providers()
    config = providers.get(provider_name, {})
    if not config.get("enabled", False):
        return False
    if config.get("free_tier", False):
        return True  # Free tier doesn't need a key
    return _get_provider_key(provider_name) is not None


def _is_reasoning_boost_enabled() -> bool:
    """Check if reasoning boost is enabled in user config."""
    config_path = Path.home() / ".config" / "costa" / "config.json"
    try:
        config = json.loads(config_path.read_text())
        return config.get("reasoning_boost", False)
    except Exception:
        return False


def reasoning_boost(
    task_description: str,
    context: str = "",
    max_tokens: int = 2048,
    timeout: int = 90,
) -> str | None:
    """Delegate a hard reasoning subtask to Gemini's thinking mode.

    Called by the router when:
    1. reasoning_boost is enabled in config (~/.config/costa/config.json)
    2. Query category is math/reasoning/science/architecture
    3. Gemini provider is available

    Returns the Gemini response, or None if unavailable/failed.

    # MCP Integration (future): Expose reasoning_boost as a tool:
    # costa_reasoning_boost(task: str, context: str) -> str
    # This lets Claude Code explicitly delegate thinking to Gemini
    # when it determines a subtask would benefit from Gemini's reasoning.
    """
    if not _is_reasoning_boost_enabled():
        return None

    if not _is_provider_available("gemini"):
        return None

    system_prompt = (
        "You are a reasoning specialist. Think step by step. "
        "Provide a clear, structured answer."
    )

    if context:
        prompt = f"Context:\n{context}\n\nTask:\n{task_description}"
    else:
        prompt = task_description

    # Use the free flash model; upgrade to flash-thinking if available
    providers = _load_providers()
    gemini_config = providers.get("gemini", {})
    free_models = gemini_config.get("free_models", ["gemini-2.0-flash-lite"])
    gemini_key = _get_provider_key("gemini")
    if gemini_key:
        model = "gemini-2.0-flash"  # better reasoning with key
    else:
        model = free_models[0] if free_models else "gemini-2.0-flash-lite"

    response_text, meta = query_openai_compat(
        prompt=prompt,
        model=model,
        provider="gemini",
        system=system_prompt,
        temperature=0.2,
        max_tokens=max_tokens,
        timeout=timeout,
    )

    if meta.get("error") or not response_text:
        return None

    return response_text


def query_openai_compat(
    prompt: str,
    model: str,
    provider: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 512,
    timeout: int = 45,
) -> tuple[str, dict]:
    """Query any OpenAI-compatible API (Groq, Gemini, OpenAI, Mistral, remote Ollama).

    Returns (response_text, metadata_dict).
    """
    import requests as req

    providers = _load_providers()
    config = providers.get(provider, {})
    base_url = config.get("base_url", "")
    api_key = _get_provider_key(provider) or ""

    if not base_url:
        return "", {"error": f"No base_url for provider '{provider}'"}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = req.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        meta = {
            "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
            "model": model,
            "provider": provider,
        }
        return text.strip(), meta
    except Exception as exc:
        return "", {"error": str(exc), "provider": provider, "model": model}


def select_cloud_model(route: str, query_category: str | None = None) -> dict | None:
    """Pick best available non-Claude model for a task category.

    Returns a dict with {provider, model} if an alternative is better,
    or None if Claude should handle it.

    Decision logic is based on verified benchmarks, not auto-generated scores.
    """
    routing = _load_routing()

    # Map the query category to a routing rule
    rule_name = None
    if query_category in ("math", "reasoning", "science", "physics", "chemistry"):
        rule_name = "math_reasoning"
    elif query_category in ("devops", "terminal", "cicd", "infrastructure"):
        rule_name = "devops_terminal"
    # fast_web_query is detected by the existing haiku+web route, not category

    if not rule_name:
        return None

    rule = routing.get(rule_name, {})
    preferred = rule.get("prefer", [])

    for option in preferred:
        provider = option.get("provider", "")
        model = option.get("model", "")
        tier = option.get("tier", "paid")

        if not _is_provider_available(provider):
            continue

        # If tier is "free", only use if provider has free tier
        if tier == "free":
            config = _load_providers().get(provider, {})
            if not config.get("free_tier", False):
                continue
            # Use free model if no API key
            if not _get_provider_key(provider):
                free_models = config.get("free_models", [])
                if free_models:
                    model = free_models[0]

        return {"provider": provider, "model": model}

    return None  # Stay on Claude


# Patterns that indicate the user wants an ACTION performed, not just information
ACTION_PATTERNS = re.compile(
    r"(^|\b)(turn\b.{0,20}\b(up|down|off|on)|set (the |my )?(volume|brightness|wallpaper)|"
    r"(lower|raise|increase|decrease|reduce) (the |my )?(volume|brightness)|"
    r"restart|reload|kill|close|open|launch|start|stop|mute|unmute|"
    r"switch (to |)workspace|move (window|this)|minimize|maximize|"
    r"connect|disconnect|enable|disable|toggle|"
    r"play|pause|skip|next|previous|shuffle|"
    r"show (me |my |the )?(git |docker |running |systemd |system )?(status|log|containers|services|processes|branch)|"
    r"(run|execute) (the |my )?(test|build|script|command)|"
    r"(list|check) (my |all |running )?(docker|containers|services|packages|updates|processes))\b",
    re.IGNORECASE,
)

# Commands that are safe to run without confirmation
SAFE_COMMAND_PATTERNS = [
    r"^wpctl\s+(set-volume|set-mute|get-volume)",
    r"^pactl\s+(set-default|get-default|set-sink-volume|set-source-volume)",
    r"^hyprctl\s+(dispatch|reload|switchxkblayout|monitors|clients|activewindow)",
    r"^killall\s+(ags|dunst)$",
    r"^notify-send\b",
    r"^playerctl\b",
    r"^brightnessctl\b",
    r"^systemctl\s+(--user\s+)?(restart|start|stop)\s+(pipewire|wireplumber)",
    r"^systemctl\s+(--failed|list-timers|status)\b",
    r"^ags\b",
    # Read-only system queries — safe to auto-run
    r"^git\s+(status|branch|log|diff|remote)\b",
    r"^docker\s+(ps|images|stats|logs)\b",
    r"^sensors\b",
    r"^free\b",
    r"^df\b",
    r"^lsblk\b",
    r"^ip\s+(addr|route|link)\b",
    r"^ss\s+",
    r"^uname\b",
    r"^cat\s+/proc/(cpuinfo|meminfo|version)\b",
    r"^lspci\b",
    r"^bluetoothctl\s+(show|devices)\b",
    r"^checkupdates\b",
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
                          "playerctl", "notify", "brightnessctl", "ags",
                          "pkill", "docker", "git")):
            return cmd
    return None


_SHELL_METACHAR_RE = re.compile(r'[;|&$`(){}]')

def classify_command(cmd: str) -> str:
    """Classify a command as 'safe', 'dangerous', or 'ask'."""
    if DANGEROUS_RE.search(cmd):
        return "dangerous"
    if SAFE_RE.search(cmd):
        # Even safe-prefix commands are dangerous if they contain shell metacharacters
        # that could chain additional commands (e.g. "git status; rm -rf /")
        if _SHELL_METACHAR_RE.search(cmd):
            return "ask"
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


def _is_api_error(response: str) -> bool:
    """Detect if a response is an API error, not a real answer."""
    if not response:
        return True
    error_patterns = [
        "out of extra usage",
        "resets 2pm",
        "issue with the selected model",
        "may not exist or you may not have access",
        "rate limit",
        "overloaded",
    ]
    resp_lower = response.lower()
    return any(p in resp_lower for p in error_patterns)


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

    # Detect active editor file for AST-enriched routing
    _active_file_path = None
    try:
        import json as _json
        _aw = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True, text=True, timeout=2,
        )
        if _aw.returncode == 0:
            _win = _json.loads(_aw.stdout)
            _win_class = _win.get("class", "").lower()
            _title = _win.get("title", "")
            if any(ed in _win_class for ed in ("code", "codium", "zed")):
                _parts = _title.split(" — ")
                if _parts:
                    _candidate = _parts[0].strip()
                    if os.path.isfile(_candidate):
                        _active_file_path = _candidate
    except Exception:
        pass

    route = force_model or select_route(query, file_path=_active_file_path)
    system_prompt = get_system_prompt()
    escalated = False
    context_used = False
    model_used = route
    response = ""
    query_category = None

    try:
        # Meta queries — questions about Costa OS itself
        if not force_model:
            meta = _handle_meta(query)
            if meta:
                elapsed = time.time() - start
                result = {
                    "query": query,
                    "response": meta["response"],
                    "model": "meta",
                    "route": "meta",
                    "context_gathered": False,
                    "escalated": False,
                    "command_executed": None,
                    "elapsed_ms": int(elapsed * 1000),
                    "total_ms": int(elapsed * 1000),
                }
                _log_to_db(result, input_modality)
                return result

        # Multi-intent splitting — "do X and then do Y"
        if not force_model:
            parts = _split_multi_intent(query)
            if len(parts) > 1:
                responses = []
                for part in parts:
                    sub = route_query(part, force_model=force_model,
                                      allow_escalation=allow_escalation,
                                      gather_context_flag=gather_context_flag,
                                      input_modality=input_modality)
                    responses.append(sub.get("response", ""))
                elapsed = time.time() - start
                result = {
                    "query": query,
                    "response": " | ".join(r for r in responses if r),
                    "model": "multi",
                    "route": "multi",
                    "context_gathered": False,
                    "escalated": False,
                    "command_executed": None,
                    "elapsed_ms": int(elapsed * 1000),
                    "total_ms": int(elapsed * 1000),
                }
                _log_to_db(result, input_modality)
                return result

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
                "escalated": bool(wm_result.get("commands_run") and wm_result["commands_run"][0] == "(via Claude)"),
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

        # Window manager route from ML (not caught by is_window_command regex)
        # Skip WM handler for config/settings queries that were misrouted
        _is_config_query = bool(re.search(
            r"\b(wallpaper|theme|font|config|setting|keybind|notification|display|resolution)\b",
            query, re.IGNORECASE
        ))
        if route == "window_manager" and not force_model and not _is_config_query:
            wm_result = execute_window_command(query)
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
                "escalated": bool(wm_result.get("commands_run") and wm_result["commands_run"][0] == "(via Claude)"),
                "command_executed": "; ".join(wm_result["commands_run"]) if wm_result["commands_run"] else None,
                "elapsed_ms": int(elapsed * 1000),
                "total_ms": int(elapsed * 1000),
            }
            _log_to_db(result, input_modality)
            return result

        # Budget check before cloud calls
        if route in ("opus", "sonnet", "haiku+web"):
            try:
                from db import check_budget
                if not check_budget():
                    if query_category and query_category in ("code_write", "code_debug", "code_test", "code_refactor"):
                        # Budget exhausted — try free Devstral for code tasks
                        if _is_provider_available("mistral"):
                            t0 = time.time()
                            alt_response, _ = query_openai_compat(
                                query, model="devstral-small-2505", provider="mistral",
                                system=system_prompt, max_tokens=1024, timeout=60,
                            )
                            model_ms = int((time.time() - t0) * 1000)
                            if alt_response:
                                response = alt_response
                                model_used = "mistral:devstral-small-2505"
                                route = "budget_fallback"
                    if not response:
                        route = "local"  # Fall back to local when budget exhausted
            except Exception:
                pass  # If budget check fails, proceed normally

        # Cloud routes — pass directly (with tool_use for sonnet/opus)
        if route in ("opus", "sonnet"):
            t0 = time.time()
            response = query_claude(query, model=route, timeout=120, use_tools=True)
            model_ms = int((time.time() - t0) * 1000)
            model_used = route
            # If API is down, try alternative provider for this category
            if _is_api_error(response):
                alt = select_cloud_model(route, query_category)
                if alt:
                    t0 = time.time()
                    alt_response, alt_meta = query_openai_compat(
                        query, model=alt["model"], provider=alt["provider"],
                        system=system_prompt, timeout=60,
                    )
                    model_ms = int((time.time() - t0) * 1000)
                    if alt_response:
                        response = alt_response
                        model_used = f"{alt['provider']}:{alt['model']}"
                        route = f"{route}+fallback"
                if not response:
                    response = ""
                    route = "local"
        elif route == "haiku+web":
            t0 = time.time()
            response = query_claude(
                query, model="haiku",
                system="You are a helpful voice assistant with web search. Search the web to answer accurately. Answer in 1-3 sentences. No markdown. Be direct.",
                use_tools=True,
            )
            model_ms = int((time.time() - t0) * 1000)
            model_used = "haiku"
            if _is_api_error(response):
                response = "Cloud API is currently unavailable. Try again in a few minutes."
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
            if ollama_model:
                response = query_ollama(prompt, system_prompt, ollama_model)
                model_used = ollama_model
            else:
                response = query_claude(prompt, model="haiku")
                model_used = "haiku"
            model_ms = int((time.time() - t0) * 1000)
        else:
            # Local route — context injection + knowledge + conversation + RAG + escalation
            ollama_model = get_ollama_model()

            # No local model available (no GPU / gaming mode): route everything to cloud
            if ollama_model is None:
                t0 = time.time()
                response = query_claude(
                    query, model="haiku",
                    system="You are a helpful assistant for a Linux power user running Costa OS (Arch Linux + Hyprland). Be direct and technical.",
                    use_tools=True,
                )
                model_ms = int((time.time() - t0) * 1000)
                model_used = "haiku"
                route = "cloud_only"
                if not response:
                    response = "No local model is available and cloud is not reachable. Check your internet connection, or run 'claude' in a terminal to set up Claude Code."
                elapsed = time.time() - start
                result = {
                    "query": query, "response": response, "model": model_used,
                    "route": route, "context_gathered": False, "escalated": False,
                    "command_executed": None, "elapsed_ms": int(elapsed * 1000),
                    "total_ms": int(elapsed * 1000),
                }
                _log_to_db(result, input_modality)
                return result

            # Category-aware model selection: if the ML classifier or regex
            # detected a category where a different model excels, swap to it.
            # Ollama auto-loads the requested model (2-3s swap).
            query_category = None
            try:
                from ml_router import get_router
                router_inst = get_router()
                _route, _conf = router_inst.predict(query)
                # The classifier returns a route, but we need the category.
                # Use the knowledge topic scoring as a proxy for category.
                from knowledge import TOPIC_PATTERNS
                best_cat, best_score = None, 0
                for cat, pat in TOPIC_PATTERNS.items():
                    if re.search(pat, query, re.IGNORECASE):
                        best_cat = cat
                        break
                # Map knowledge topics to benchmark categories
                _TOPIC_TO_CATEGORY = {
                    "arch-admin": "package_query",
                    "dev-tools": "code_write",
                    "ai-router": "architecture",
                    "costa-os": "deep_knowledge",
                    "costa-nav": "architecture",
                    "pipewire-audio": "simple_action",
                    "music-control": "simple_action",
                    "process-management": "system_info",
                    "bluetooth": "system_info",
                    "display": "system_info",
                    "network": "system_info",
                    "hyprland": "system_info",
                    "keybinds": "system_info",
                    "customization": "deep_knowledge",
                    "security": "architecture",
                    "screenshots": "simple_action",
                    "notifications": "simple_action",
                }
                if best_cat:
                    query_category = _TOPIC_TO_CATEGORY.get(best_cat, best_cat)
            except Exception:
                pass

            # Also detect category from code/refactor/test/debug keywords
            if not query_category:
                q_lower = query.lower()
                # Simple actions — fast model handles these instantly
                if re.search(r"\b(unmute|mute|volume|brightness|play|pause|skip|next|prev|previous|louder|quieter|turn (up|down|on|off))\b", q_lower) and len(query.split()) <= 10:
                    query_category = "simple_action"
                elif re.search(r"\b(refactor|clean up|simplify|rename)\b", q_lower):
                    query_category = "code_refactor"
                elif re.search(r"\b(test|spec|coverage|assert)\b", q_lower):
                    query_category = "code_test"
                elif re.search(r"\b(debug|trace|error|crash|fix|bug)\b", q_lower):
                    query_category = "code_debug"
                elif re.search(r"\b(deploy|release|ship|ci|cd|pipeline)\b", q_lower):
                    query_category = "code_deploy"
                elif re.search(r"\b(architect|design|structure|pattern|system)\b", q_lower):
                    query_category = "architecture"
                elif re.search(r"\b(solve|calculate|compute|derive|prove|equation|integral|derivative|math|algebra|calculus|geometry|statistics|probability)\b", q_lower):
                    query_category = "math"
                elif re.search(r"\b(physics|chemistry|biology)\s+(problem|question|equation)\b", q_lower):
                    query_category = "science"

            # AST-enriched category detection: if the query references code and
            # we have an active editor, use structural analysis to improve routing.
            # A 5-line helper refactor → fast model; a 200-line class with 40
            # dependents → route to Claude.
            if query_category in ("code_refactor", "code_debug", "code_test", None) and _active_file_path:
                try:
                    import ast_parser
                    summary = ast_parser.get_file_summary(_active_file_path)
                    if summary.get("parseable"):
                        total_lines = summary.get("total_lines", 0)
                        sym_count = summary.get("symbol_count", 0)

                        # If the active file is complex, consider
                        # escalating category to architecture
                        if total_lines > 500 or sym_count > 30:
                            if query_category == "code_refactor":
                                query_category = "architecture"
                            elif not query_category and re.search(
                                r"\b(this|here|current|open)\b", q_lower
                            ):
                                # Query references current context + large file
                                query_category = "code_debug"
                except Exception:
                    pass

            # Route math/reasoning to Gemini if available (verified GPQA advantage)
            if query_category in ("math", "reasoning", "science") and not force_model:
                alt = select_cloud_model(route, query_category)
                if alt:
                    t0 = time.time()
                    alt_response, alt_meta = query_openai_compat(
                        query, model=alt["model"], provider=alt["provider"],
                        system=system_prompt, temperature=0.2, max_tokens=1024, timeout=60,
                    )
                    model_ms = int((time.time() - t0) * 1000)
                    if alt_response and not is_idk_response(alt_response):
                        response = alt_response
                        model_used = f"{alt['provider']}:{alt['model']}"
                        route = f"local+{alt['provider']}"
                        # Skip the normal local model path
                        elapsed = time.time() - start
                        result = {
                            "query": query, "response": response, "model": model_used,
                            "route": route, "context_gathered": context_used,
                            "escalated": False, "command_executed": None,
                            "elapsed_ms": int(elapsed * 1000), "total_ms": int(elapsed * 1000),
                            "context_ms": context_ms, "knowledge_ms": knowledge_ms,
                            "model_ms": model_ms,
                        }
                        _log_to_db(result, input_modality)
                        return result

            # Pick the best model for this category (if we identified one)
            if query_category and query_category in CATEGORY_MODEL_PREFS:
                preferred = select_local_model(query_category, ollama_model)
                if preferred != ollama_model:
                    ollama_model = preferred

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

            # Reasoning Boost: for architecture queries (or math/reasoning/science when
            # reasoning_boost is enabled but Gemini wasn't available earlier), delegate
            # the thinking step to Gemini before running Ollama.
            # math/reasoning/science typically return early above via select_cloud_model;
            # this covers architecture and acts as a fallback for the others.
            if query_category in ("math", "reasoning", "science", "architecture") and not force_model:
                t0 = time.time()
                boost_response = reasoning_boost(
                    task_description=query,
                    context=context,
                    max_tokens=2048,
                    timeout=90,
                )
                if boost_response and not is_idk_response(boost_response):
                    model_ms = int((time.time() - t0) * 1000)
                    response = boost_response
                    model_used = "gemini:reasoning-boost"
                    route = "local+reasoning-boost"
                    elapsed = time.time() - start
                    result = {
                        "query": query, "response": response, "model": model_used,
                        "route": route, "context_gathered": context_used,
                        "escalated": False, "command_executed": None,
                        "elapsed_ms": int(elapsed * 1000), "total_ms": int(elapsed * 1000),
                        "context_ms": context_ms, "knowledge_ms": knowledge_ms,
                        "model_ms": model_ms,
                    }
                    _log_to_db(result, input_modality)
                    return result

            t0 = time.time()
            response = query_ollama(prompt, system_prompt, ollama_model,
                                    temperature=temp, num_predict=num_predict)
            model_ms = int((time.time() - t0) * 1000)

            # Check for "I don't know" responses and escalate.
            # But if the response contains a valid command, it's NOT an IDK —
            # the model gave the answer even if it hedged with "you can run...".
            has_command = bool(response and extract_command(response))
            if allow_escalation and not has_command and is_idk_response(response) and not _cancelled:
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
                if haiku_response and not _is_api_error(haiku_response):
                    response = haiku_response
                    model_used = "haiku"
                    route = "local+escalated"
                elif not response or is_idk_response(response):
                    # Both local and cloud failed
                    response = "Could not get an answer. The local model was unsure and cloud is not reachable. Check your internet connection or try again."

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
                    # "ask" category: show command but don't auto-execute
                    response = f"{response}\n\nSuggested command: `{cmd}` (run manually to confirm)"
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

        # Log AST features for future training
        if _active_file_path:
            try:
                from ml_router import extract_ast_features
                _ast_feats = extract_ast_features(query, _active_file_path)
                if _ast_feats is not None:
                    from db import log_ast_features
                    log_ast_features(result.get("query_id"), _active_file_path, _ast_feats.tolist())
            except Exception:
                pass

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
