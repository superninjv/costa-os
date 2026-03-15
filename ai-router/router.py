"""Costa AI Router — smart routing with context injection and auto-escalation.

The local model gets real system data injected into its prompt so it can actually
answer questions about the system. If it still can't answer (detects "I don't know"
type responses), it automatically escalates to Claude Haiku for a fast cloud answer.
"""

import subprocess
import json
import re
import os
import time
from pathlib import Path

from context import gather_context
from window_manager import is_window_command, execute_window_command
from project_switch import switch_project, fuzzy_match, list_projects
from file_search import search_files, format_results as format_file_results, record_file_open


# Read system prompt
SYSTEM_PROMPT_PATH = Path.home() / ".config" / "costa" / "system-ai.md"
KNOWLEDGE_DIR = Path.home() / ".config" / "costa" / "knowledge"
CONVERSATION_FILE = Path("/tmp/costa-conversation.json")
MAX_CONVERSATION_TURNS = 5
OLLAMA_URL = "http://localhost:11434/api/generate"

# Knowledge file selection by topic
KNOWLEDGE_TOPICS = {
    "arch-admin": r"(package|pacman|yay|install|update|upgrade|systemd|systemctl|service|journal|orphan|cache|downgrade)",
    "hyprland": r"(hyprland|hyprctl|window|workspace|monitor|keybind|bind|dispatch|float|tile|rule|config.*hypr)",
    "pipewire-audio": r"(audio|sound|volume|pipewire|wireplumber|speaker|mic|microphone|sink|source|alsa|pulse|crackling)",
    "costa-setup": r"(costa|theme|waybar|ghostty|rofi|dunst|wallpaper|config|dotfile|chezmoi|setup|customize)",
    "dev-tools": r"(python|pyenv|node|nvm|rust|cargo|java|sdk|docker|compose|git|lazygit|zellij|kubectl|k9s)",
}

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
    "project_switch": r"(switch|change|go|jump|move|open|load|start|launch)\s+(to\s+|into\s+|up\s+)?(the\s+)?\w[\w\s\-]*?\s*(project|workspace|env)|switch\s+to\s+\w+",
    "opus": r"architect|design.*system|research.*in.depth|deep dive|security.*audit|plan.*migration|compare.*approach|trade.?off|comprehensive.*review|evaluate.*strategy",
    "sonnet": r"write (a |the |some |me )?(code|script|function|class|test|program|module)|implement|debug|fix (the |this |a )?bug|refactor|make (a |the )?(component|api|endpoint|server|app)|build (a |the )?(project|app|service)|deploy|set up (a |the )?(pipeline|ci|cd|server)",
    "haiku+web": r"(latest |breaking |today.s )?(news|headline)|score.*(game|match)|who.*(won|play|lead)|trending|what happened.*(today|yesterday|world|country)|latest.*update.*(on|about)|search.*for.*(online|web|internet)|look up.*(online|web|person|company|stock|price)",
    "local+weather": r"weather|forecast|temperature|rain",
}

# Pattern to extract project name from switch queries
PROJECT_SWITCH_RE = re.compile(
    r"(?:switch|change|go|jump|move|open|load|start|launch)\s+"
    r"(?:to\s+|into\s+|up\s+)?(?:the\s+)?(?:project\s+)?"
    r"([\w][\w\s\-]*?)(?:\s+project|\s+workspace|\s+env)?$",
    re.IGNORECASE,
)


def get_system_prompt() -> str:
    """Load the system prompt from disk."""
    try:
        return SYSTEM_PROMPT_PATH.read_text()
    except Exception:
        return "You are the Costa OS local AI assistant. Be concise and direct."


def get_ollama_model() -> str:
    """Read the current best model from the VRAM manager."""
    try:
        return Path("/tmp/ollama-smart-model").read_text().strip()
    except Exception:
        return "qwen3:14b"  # default if VRAM manager hasn't written yet


def select_knowledge(query: str) -> str:
    """Select and load relevant knowledge files based on query topic."""
    q = query.lower()
    knowledge_parts = []
    for name, pattern in KNOWLEDGE_TOPICS.items():
        if re.search(pattern, q, re.IGNORECASE):
            kb_path = KNOWLEDGE_DIR / f"{name}.md"
            if kb_path.exists():
                knowledge_parts.append(kb_path.read_text())
    return "\n\n".join(knowledge_parts) if knowledge_parts else ""


def get_conversation_history() -> list[dict]:
    """Load rolling conversation history."""
    try:
        data = json.loads(CONVERSATION_FILE.read_text())
        return data[-MAX_CONVERSATION_TURNS:]
    except Exception:
        return []


def save_conversation_turn(query: str, response: str, model: str):
    """Append a turn to conversation history."""
    history = get_conversation_history()
    history.append({
        "q": query,
        "a": response[:300],  # truncate long responses
        "m": model,
        "t": int(time.time()),
    })
    # Keep only last N turns
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
    """Determine the best model tier for this query."""
    for model, pattern in ROUTE_PATTERNS.items():
        if re.search(pattern, query, re.IGNORECASE):
            return model
    return "local"


def query_ollama(prompt: str, system: str, model: str, timeout: int = 30) -> str:
    """Send a query to Ollama and return the response text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "keep_alive": "5m",
    })
    try:
        result = subprocess.run(
            ["curl", "-s", OLLAMA_URL, "-d", payload],
            capture_output=True, text=True, timeout=timeout,
        )
        data = json.loads(result.stdout)
        return data.get("response", "").strip()
    except Exception as e:
        return ""


def query_claude(query: str, model: str = "haiku", tools: list[str] | None = None,
                 system: str = "", timeout: int = 45) -> str:
    """Send a query to Claude via the claude CLI."""
    cmd = ["claude", "-p", "--model", model, "--dangerously-skip-permissions"]
    if tools:
        cmd.extend(["--tools", ",".join(tools)])
        cmd.extend(["--allowedTools", ",".join(tools)])
    if not system:
        system = "You are a helpful voice assistant. Answer in 1-3 sentences. No markdown. Be direct."
    cmd.extend(["--system-prompt", system])

    try:
        result = subprocess.run(
            cmd, input=query, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
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
                allow_escalation: bool = True, gather_context_flag: bool = True) -> dict:
    """Route a query through the AI stack.

    Returns a dict with:
        response: str — the answer
        model: str — which model answered (e.g. "qwen2.5:14b", "haiku", "sonnet")
        route: str — the routing decision (e.g. "local", "local+escalated", "haiku+web")
        context_gathered: bool — whether system context was injected
        escalated: bool — whether the query was escalated from local to cloud
    """
    start = time.time()
    route = force_model or select_route(query)
    system_prompt = get_system_prompt()
    escalated = False
    context_used = False
    model_used = route

    # Window management — intercept before other routes
    if not force_model and is_window_command(query):
        wm_result = execute_window_command(query)
        elapsed = time.time() - start
        return {
            "response": wm_result["result"],
            "model": "window_manager",
            "route": "window_manager",
            "context_gathered": False,
            "escalated": False,
            "command_executed": "; ".join(wm_result["commands_run"]) if wm_result["commands_run"] else None,
            "elapsed_ms": int(elapsed * 1000),
        }

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
            resp = f"No project matches '{project_name}'. Available: {available}" if available else f"No project configs found."
        return {
            "response": resp,
            "model": "project_switch",
            "route": "project_switch",
            "context_gathered": False,
            "escalated": False,
            "command_executed": None,
            "elapsed_ms": int(elapsed * 1000),
        }

    # File search — intercept before AI routes
    if route == "file_search" and not force_model:
        results = search_files(query)
        elapsed = time.time() - start
        if results:
            # Format top results as a natural response
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
        return {
            "response": resp,
            "model": "file_search",
            "route": "file_search",
            "context_gathered": False,
            "escalated": False,
            "command_executed": None,
            "elapsed_ms": int(elapsed * 1000),
        }

    # Cloud routes — pass directly
    if route in ("opus", "sonnet"):
        response = query_claude(query, model=route, timeout=120)
        model_used = route
    elif route == "haiku+web":
        response = query_claude(
            query, model="haiku",
            tools=["WebSearch", "WebFetch"],
            system="You are a helpful voice assistant with web search. Search the web to answer accurately. Answer in 1-3 sentences. No markdown. Be direct.",
        )
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
        response = query_ollama(prompt, system_prompt, ollama_model)
        model_used = ollama_model
    else:
        # Local route — context injection + knowledge + conversation + escalation
        ollama_model = get_ollama_model()
        model_used = ollama_model

        # Gather system context
        context = ""
        if gather_context_flag:
            context = gather_context(query)
            context_used = bool(context)

        # Select relevant knowledge base
        knowledge = select_knowledge(query)

        # Get conversation history
        conv_history = get_conversation_history()
        conv_context = format_conversation_context(conv_history)

        # Build prompt with all context layers
        prompt_parts = []
        if knowledge:
            prompt_parts.append(f"[REFERENCE — use this knowledge to answer accurately]\n{knowledge}")
        if context:
            prompt_parts.append(f"[SYSTEM CONTEXT — real data from this machine]\n{context}")
        if conv_context:
            prompt_parts.append(conv_context)
        prompt_parts.append(f"[USER QUERY]\n{query}")

        prompt = "\n\n".join(prompt_parts)

        response = query_ollama(prompt, system_prompt, ollama_model)

        # Check for "I don't know" responses and escalate
        if allow_escalation and is_idk_response(response):
            # Escalate to Haiku — fast, cheap, and actually has broad knowledge
            escalated = True
            haiku_prompt = query
            if context:
                # Give Haiku the system context too
                haiku_prompt = f"The user is on an Arch Linux system (Hyprland, AMD GPU). System data:\n{context}\n\nQuestion: {query}"

            haiku_response = query_claude(
                haiku_prompt, model="haiku",
                system="You are a helpful assistant for a Linux power user. Answer in 1-3 sentences. No markdown. Be direct and technical.",
            )
            if haiku_response:
                response = haiku_response
                model_used = "haiku"
                route = "local+escalated"

    # Action execution: if the user wanted something DONE, extract and run the command
    command_executed = None
    if response and is_action_query(query):
        cmd = extract_command(response)
        if cmd:
            safety = classify_command(cmd)
            if safety == "safe":
                cmd_output = execute_command(cmd)
                command_executed = cmd
                # Re-query model to give a natural response about what happened
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
                # "ask" — run it but notify what was done
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

    elapsed = time.time() - start

    # Save conversation turn for rolling context
    if response and route in ("local", "local+escalated", "local+weather"):
        save_conversation_turn(query, response, model_used)

    return {
        "response": response,
        "model": model_used,
        "route": route,
        "context_gathered": context_used,
        "escalated": escalated,
        "command_executed": command_executed,
        "elapsed_ms": int(elapsed * 1000),
    }
