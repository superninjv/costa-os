"""ML-based query router — PyTorch MLP classifier that learns which model
handles which queries best.

Replaces static regex routing with a lightweight neural network trained on
labeled query→route pairs. Falls back gracefully if no trained model exists.

Usage:
    python3 ml_router.py train              # generate synthetic data + train
    python3 ml_router.py eval               # train + evaluate + print report
    python3 ml_router.py predict "query"    # predict route for a query
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from knowledge import TOPIC_PATTERNS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROUTE_CLASSES = [
    "local",
    "local_will_escalate",
    "haiku+web",
    "sonnet",
    "opus",
    "file_search",
    "window_manager",
]

MODEL_PATH = Path.home() / ".config" / "costa" / "ml_router.pt"
# Pre-trained model shipped with Costa OS (fallback if user hasn't trained yet)
SHIPPED_MODEL_PATH = Path(__file__).parent / "models" / "ml_router.pt"
LLM_CLASSIFY_THRESHOLD = 0.85  # Below this, ask the local LLM to classify
LLM_CLASSIFY_CACHE: dict[str, tuple[str, float]] = {}  # query → (route, confidence)

ACTION_KEYWORDS = re.compile(
    r"\b(turn|set|restart|kill|open|play|close|stop|start|run|launch|switch|move|resize|toggle|enable|disable|mute|unmute)\b",
    re.IGNORECASE,
)

CODE_KEYWORDS = re.compile(
    r"\b(write|implement|debug|function|class|code|refactor|compile|build|deploy|test|lint|error|exception|traceback|syntax|api|endpoint|database|query|sql|schema|migrate)\b",
    re.IGNORECASE,
)

WEB_KEYWORDS = re.compile(
    r"\b(news|trending|score|latest|current|today|live|update|weather|forecast|stock|price|release|announced|happened|election)\b",
    re.IGNORECASE,
)

FILE_SEARCH_KEYWORDS = re.compile(
    r"\b(find\s+(the\s+|that\s+|my\s+|a\s+|all\s+)?(file|script|config|module)|where\s+is\s+(the|my|that)|locate\s+(the|my)|which\s+file)\b",
    re.IGNORECASE,
)

SYSTEM_INFO_KEYWORDS = re.compile(
    r"\b(how\s+much\s+(disk|ram|memory|swap|space|storage)|check\s+(my\s+)?(cpu|gpu|ram|memory|disk|swap|temp|usage)|what\s+(gpu|cpu|kernel|ip|dns|uptime|monitors?|displays?)\s+(do|are|is|am)|is\s+\w+\s+running|list\s+(running|installed|all)\s+\w+|show\s+(disk|memory|cpu|network|routing|all\s+connected)|what\s+(monitors?|displays?)\s+are\s+(connected|attached|available))\b",
    re.IGNORECASE,
)

DEEP_QUESTION_KEYWORDS = re.compile(
    r"\b(explain\s+(how|the|in\s+depth)|deep\s+dive|in\s+detail|internals|comprehensive|thorough|compare\s+.{5,}\s+vs|trade.?offs?\s+(between|of))\b",
    re.IGNORECASE,
)

# Distinguish "hyprland config question" from "hyprland window action"
WM_ACTION_KEYWORDS = re.compile(
    r"\b(move|put|tile|snap|float|resize|swap|focus|arrange|group|pin|center|bring|send)\s.{0,20}\b(window|terminal|browser|firefox|code|spotify|editor|monitor|workspace|left|right|half|screen)\b",
    re.IGNORECASE,
)

OPUS_KEYWORDS = re.compile(
    r"\b(architect|design\s+a\s+(system|pipeline|layer|framework|plugin|module|architecture|strategy|infra)|threat\s*model|security\s*(audit|posture|review)|incident\s*response|evaluate\s+(trade|whether)|comprehensive\s+(review|analysis))\b",
    re.IGNORECASE,
)

HYPRLAND_CONFIG_KEYWORDS = re.compile(
    r"\b(what\s+(is|are)\s+(my\s+)?(current\s+)?(hyprland|hyprctl)|hyprland\s+(version|config|setting|animation|border|gap|keybind|rule|option|variable)|how\s+do\s+I\s+(set|change|configure|edit)\s+.{0,15}hyprland|what\s+version\s+of\s+hyprland|(my|current)\s+(hyprland\s+)?(animation|border|gap|keybind|rule)s?)\b",
    re.IGNORECASE,
)

VRAM_MODEL_MAP = {
    # Quality scores from benchmark_qwen35.py (2026-03-23, 80 prompts, Vulkan/RADV)
    "qwen3.5:9b": 0.87,    # Best quality (0.871), 24 t/s, ~8GB VRAM
    "qwen3:14b": 0.85,     # Similar quality (0.854), 25 t/s, ~11GB VRAM
    "qwen3.5:4b": 0.86,    # Near-best quality (0.858), 28 t/s, ~5GB VRAM
    "qwen3.5:2b": 0.85,    # Best value (0.852), 55 t/s, ~3GB VRAM
    "qwen3.5:0.8b": 0.84,  # Still viable (0.846), 16 t/s, ~1.5GB VRAM
    "qwen2.5:14b": 1.0,    # Legacy baseline
    "qwen2.5:7b": 0.66,
    "qwen2.5:3b": 0.33,
}

# Category-aware model preferences — best model per category from benchmark data.
# Used by select_local_model() to override the default VRAM-tier model when a
# category-specialist would do better. Only triggers if the preferred model fits
# in VRAM (checked against /tmp/ollama-smart-model tier).
#
# Format: category → [(model, quality, vram_gb), ...] sorted best-first
# The router picks the first model that fits in current VRAM budget.
CATEGORY_MODEL_PREFS = {
    # qwen3:14b dominates architecture and test generation
    "architecture":    [("qwen3:14b", 0.955, 11), ("qwen3.5:9b", 0.905, 8), ("qwen3.5:4b", 0.900, 5)],
    "code_test":       [("qwen3:14b", 1.000, 11), ("qwen3.5:4b", 1.000, 5), ("qwen3.5:9b", 0.667, 8)],
    # qwen3.5:9b dominates these categories
    "package_query":   [("qwen3.5:9b", 0.903, 8), ("qwen3:14b", 0.819, 11), ("qwen3.5:2b", 0.778, 3)],
    "code_deploy":     [("qwen3.5:9b", 1.000, 8), ("qwen3.5:4b", 0.833, 5), ("qwen3:14b", 0.833, 11)],
    # qwen3.5:2b and 4b are surprisingly strong here — use for speed
    "code_debug":      [("qwen3.5:2b", 1.000, 3), ("qwen3.5:4b", 1.000, 5), ("qwen3.5:9b", 0.875, 8)],
    "code_refactor":   [("qwen3.5:2b", 1.000, 3), ("qwen3.5:4b", 1.000, 5), ("qwen3.5:9b", 1.000, 8)],
    # deep_knowledge — 2b is perfect, save VRAM
    "deep_knowledge":  [("qwen3.5:2b", 1.000, 3), ("qwen3.5:4b", 0.988, 5), ("qwen3.5:9b", 0.975, 8)],
}

# VRAM size (GB) for each model — used to check if a preferred model fits
MODEL_VRAM_GB = {
    "qwen3.5:0.8b": 1.5,
    "qwen3.5:2b": 3,
    "qwen3.5:4b": 5,
    "qwen3.5:9b": 8,
    "qwen3:14b": 11,
    "qwen3.5:27b": 17,
    "qwen2.5:3b": 3,
    "qwen2.5:7b": 6,
    "qwen2.5:14b": 11,
}


def select_local_model(category: str, default_model: str, vram_budget_gb: float = 0) -> str:
    """Pick the best local model for a query category.

    If the category has a specialist model that fits in VRAM, use it.
    Otherwise fall back to the default model from the VRAM manager.

    Only swaps if the quality gain is >= 5% over the default model's quality
    in that category, to avoid unnecessary 2-3s model load penalties.

    Args:
        category: Query category from ML classifier (e.g. "architecture")
        default_model: Current model from /tmp/ollama-smart-model
        vram_budget_gb: Available VRAM in GB (0 = use default model's tier)

    Returns:
        Model name to use for this query.
    """
    prefs = CATEGORY_MODEL_PREFS.get(category)
    if not prefs:
        return default_model

    # If no VRAM budget provided, estimate from the default model
    if vram_budget_gb <= 0:
        vram_budget_gb = MODEL_VRAM_GB.get(default_model, 8) + 2  # headroom

    # Find the default model's quality in this category (if listed)
    default_quality = 0.0
    for model, quality, _vram in prefs:
        if model == default_model:
            default_quality = quality
            break
    # If default isn't in prefs, use its overall score
    if default_quality == 0.0:
        default_quality = VRAM_MODEL_MAP.get(default_model, 0.5)

    for model, quality, vram_needed in prefs:
        if model == default_model:
            return default_model  # Already the best — no swap needed
        if vram_needed <= vram_budget_gb and (quality - default_quality) >= 0.049:
            return model

    return default_model

# ---------------------------------------------------------------------------
# Intent structure features — verb+noun patterns that disambiguate routes
# ---------------------------------------------------------------------------

VERSION_CHECK_RE = re.compile(
    r"\b(what\s+(version|release)|which\s+version|version\s+of|version\s+(is|do)|is\s+installed|do\s+I\s+have)\b",
    re.IGNORECASE,
)

FILE_INTENT_RE = re.compile(
    r"\b(what\s+(file|config|script|module)\s+(defines?|controls?|sets?|handles?|does|is\s+responsible)|which\s+(file|config|script|module)|the\s+file\s+(that|responsible|for))\b",
    re.IGNORECASE,
)

DESIGN_INTENT_RE = re.compile(
    r"\b(design\s+a|architect\s+a|plan\s+a|evaluate\s+(whether|the)|create\s+a\s+(comprehensive|threat|incident|migration|capacity|security|backup|testing|monitoring|data\s+retention|rollback|permissions))\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Entity vocabulary — known nouns that disambiguate routes
# ---------------------------------------------------------------------------

EXTERNAL_ENTITIES = {
    "cloudflare", "github", "gitlab", "bitbucket", "steam", "nvidia", "amd",
    "intel", "google", "aws", "azure", "digitalocean", "reddit", "twitter",
    "youtube", "twitch", "spotify", "discord", "slack", "telegram", "whatsapp",
    "openai", "anthropic", "microsoft", "apple", "meta", "amazon", "netflix",
    "hacker news", "hackernews", "hn", "stackoverflow", "wikipedia", "arxiv",
    "pypi", "npm", "crates.io", "dockerhub", "ubuntu", "fedora", "debian",
    "nba", "nfl", "mlb", "ufc", "f1", "fifa", "champions league", "super bowl",
    "bitcoin", "ethereum", "crypto", "nasdaq", "s&p", "dow jones",
    "cve", "exploit", "zero-day", "zeroday", "vulnerability", "advisory",
    "spacex", "tesla", "boeing", "starlink",
    "pytorch", "tensorflow", "huggingface", "langchain", "llamacpp",
}

LOCAL_ENTITIES = {
    "docker", "podman", "pipewire", "wireplumber", "pulseaudio", "ollama",
    "waybar", "hyprland", "hyprctl", "dunst", "rofi", "ghostty", "kitty",
    "alacritty", "systemd", "systemctl", "journalctl", "pacman", "yay",
    "bluetooth", "bluetoothctl", "wifi", "networkmanager", "nmcli",
    "zellij", "tmux", "zsh", "bash", "fish", "neovim", "nvim", "vim",
    "firefox", "chromium", "brave", "code", "vscode",
    "greetd", "tuigreet", "sddm", "gdm",
    "pipewire", "easyeffects", "qpwgraph", "pavucontrol",
    "gpu", "cpu", "ram", "swap", "nvme", "ssd", "partition",
    "ssh", "sshd", "gpg", "keyring",
    "nginx", "apache", "postgresql", "postgres", "redis", "mongodb",
    "xdg", "gtk", "qt", "wayland", "xwayland",
}

CODE_ENTITIES = {
    "python", "rust", "typescript", "javascript", "java", "kotlin", "go",
    "golang", "ruby", "php", "swift", "c++", "cpp", "haskell", "elixir",
    "fastapi", "flask", "django", "express", "react", "vue", "svelte",
    "nextjs", "nest", "spring", "actix", "axum", "tokio", "async",
    "postgres", "redis", "mongodb", "sqlite", "mysql", "graphql", "grpc",
    "rest", "websocket", "oauth", "jwt", "webhook", "middleware",
    "dockerfile", "docker-compose", "kubernetes", "k8s", "terraform",
    "ansible", "github actions", "ci/cd", "pytest", "jest", "cargo",
}

N_NGRAM_BINS = 16  # Character trigram hash bins (kept small to prevent overfitting)


_NEW_RELEASE_RE = re.compile(
    r"\b(new(er)?\s+version|released|been\s+released|come\s+out|came\s+out|update[ds]?\s+(for|to)|upgrade|changelog)\b",
    re.IGNORECASE,
)
_STATUS_CHECK_RE = re.compile(
    r"\b(having\s+(issues|problems|outage)|is\s+\w+\s+down|down\s+right\s+now|loading\s+slow|not\s+working)\b",
    re.IGNORECASE,
)


def _entity_scores(query: str) -> tuple[float, float, float]:
    """Check if query contains known external, local, or code entities.

    Context-aware: "new version of docker" → external (needs web),
    while "is docker running" → local. The entity type alone isn't
    enough — the intent determines the route.

    Returns (external_intent, local_intent, code_intent) as floats 0.0-1.0.
    """
    q_lower = query.lower()
    words = set(q_lower.split())

    has_external = any(e in q_lower for e in EXTERNAL_ENTITIES)
    has_local = any(e in words or e in q_lower for e in LOCAL_ENTITIES)
    has_code = any(e in words or e in q_lower for e in CODE_ENTITIES)

    # Intent modifiers: "new version of X" or "X having issues" → needs web
    # regardless of whether X is a local or external entity
    needs_web = bool(_NEW_RELEASE_RE.search(q_lower) or _STATUS_CHECK_RE.search(q_lower))

    # External entity OR local entity with web intent → external signal
    external = has_external or (has_local and needs_web)

    # Local entity WITHOUT web intent → local signal
    local = has_local and not needs_web

    # Code entity only when query has code ACTION intent (write/implement/fix/debug)
    has_code_intent = bool(CODE_KEYWORDS.search(q_lower))
    code = has_code and has_code_intent

    return (1.0 if external else 0.0,
            1.0 if local else 0.0,
            1.0 if code else 0.0)


def _char_ngram_hash(query: str, n_bins: int = N_NGRAM_BINS) -> np.ndarray:
    """Hash character trigrams into a fixed-size feature vector.

    Each word's trigrams are hashed to bins, giving the model a
    word-level fingerprint without needing an explicit vocabulary.
    Unseen words still produce distinct hash patterns.
    """
    bins = np.zeros(n_bins, dtype=np.float32)
    q = query.lower().strip()

    for word in q.split():
        # Pad word for edge trigrams
        padded = f"^{word}$"
        for i in range(len(padded) - 2):
            trigram = padded[i:i + 3]
            # Simple hash to bin index
            h = hash(trigram) % n_bins
            bins[h] += 1.0

    # Normalize to 0-1 range
    max_val = bins.max()
    if max_val > 0:
        bins /= max_val

    return bins

# Ordered list matching TOPIC_PATTERNS keys for consistent feature indexing
TOPIC_KEYS = [
    "arch-admin",
    "hyprland",
    "pipewire-audio",
    "costa-setup",
    "dev-tools",
    "voice-assistant",
    "ai-router",
    "keybinds",
    "customization",
    "costa-os",
    "costa-nav",
    "security",
    "file-operations",
    "bluetooth",
    "screenshots",
    "display",
    "network",
    "usb-drives",
    "process-management",
    "media-control",
    "notifications",
]

N_BASE_FEATURES = 21  # 15 keyword + 3 entity vocab + 3 intent structure
N_TOPIC_FEATURES = len(TOPIC_KEYS)  # 21
N_NGRAM_FEATURES = N_NGRAM_BINS  # 16
N_FEATURES = N_BASE_FEATURES + N_TOPIC_FEATURES + N_NGRAM_FEATURES  # 55


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _read_vram_tier() -> float:
    """Read current VRAM tier from /tmp/ollama-smart-model."""
    try:
        model = Path("/tmp/ollama-smart-model").read_text().strip()
        return VRAM_MODEL_MAP.get(model, 0.0)
    except (FileNotFoundError, PermissionError):
        return 0.0


def extract_features(query: str, context: dict | None = None) -> np.ndarray:
    """Convert a query string into a fixed-size feature vector.

    Args:
        query: The user's natural language query.
        context: Optional dict with extra context (unused currently, reserved).

    Returns:
        numpy array of shape (N_FEATURES,) with float32 values.
    """
    q = query.strip()
    q_lower = q.lower()

    features = []

    # --- Base features (8) ---
    # 1. Query length (normalized — divide by 200 to keep roughly 0-1)
    features.append(min(len(q) / 200.0, 1.0))

    # 2. Word count (normalized — divide by 40)
    features.append(min(len(q.split()) / 40.0, 1.0))

    # 3. Has question mark
    features.append(1.0 if "?" in q else 0.0)

    # 4. Has action keywords
    features.append(1.0 if ACTION_KEYWORDS.search(q) else 0.0)

    # 5. Has code keywords
    features.append(1.0 if CODE_KEYWORDS.search(q) else 0.0)

    # 6. Has web/news keywords
    features.append(1.0 if WEB_KEYWORDS.search(q) else 0.0)

    # 7. Hour of day (normalized 0-1)
    features.append(datetime.now().hour / 23.0)

    # 8. VRAM available tier
    features.append(_read_vram_tier())

    # 9. Has file-search intent keywords (finding actual files)
    features.append(1.0 if FILE_SEARCH_KEYWORDS.search(q) else 0.0)

    # 10. Has system-info keywords (disk usage, RAM, CPU — NOT file search)
    features.append(1.0 if SYSTEM_INFO_KEYWORDS.search(q) else 0.0)

    # 11. Has deep-question keywords (should escalate or go to opus)
    features.append(1.0 if DEEP_QUESTION_KEYWORDS.search(q) else 0.0)

    # 12. High word count (long queries tend to be complex → escalate/opus)
    features.append(1.0 if len(q.split()) > 12 else 0.0)

    # 13. Window manager action intent (move/tile/snap/float + target)
    features.append(1.0 if WM_ACTION_KEYWORDS.search(q) else 0.0)

    # 14. Hyprland config question (NOT window action)
    features.append(1.0 if HYPRLAND_CONFIG_KEYWORDS.search(q) else 0.0)

    # 15. Opus-level architecture/design keywords
    features.append(1.0 if OPUS_KEYWORDS.search(q) else 0.0)

    # 16-18. Entity vocabulary (external service, local process, code tool)
    ext, loc, cod = _entity_scores(q)
    features.append(ext)
    features.append(loc)
    features.append(cod)

    # 19. Version/status check intent ("what version of X" → local)
    features.append(1.0 if VERSION_CHECK_RE.search(q) else 0.0)

    # 20. File-finding intent ("what file defines X" → file_search)
    features.append(1.0 if FILE_INTENT_RE.search(q) else 0.0)

    # 21. Architecture/design intent ("design a X" → opus)
    features.append(1.0 if DESIGN_INTENT_RE.search(q) else 0.0)

    # --- Topic pattern features (21) ---
    for key in TOPIC_KEYS:
        pattern = TOPIC_PATTERNS.get(key, "")
        if pattern and re.search(pattern, q_lower, re.IGNORECASE):
            features.append(1.0)
        else:
            features.append(0.0)

    # --- Character trigram hash (64 bins) ---
    ngram_features = _char_ngram_hash(q)
    features.extend(ngram_features.tolist())

    return np.array(features, dtype=np.float32)


# ---------------------------------------------------------------------------
# Model architecture
# ---------------------------------------------------------------------------

def _build_model(n_features: int, n_classes: int) -> nn.Sequential:
    """Create the MLP classifier.

    Architecture:
        Input(n_features) → Linear(96) → ReLU → Dropout(0.3)
                          → Linear(48) → ReLU → Dropout(0.2)
                          → Linear(n_classes)
    """
    return nn.Sequential(
        nn.Linear(n_features, 96),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(96, 48),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(48, n_classes),
    )


# ---------------------------------------------------------------------------
# LLM-based classification for ambiguous queries
# ---------------------------------------------------------------------------

_LLM_CLASSIFY_PROMPT = """Classify this query into one category. Reply with ONLY the category name.

Categories:
- local — system info, status, config, packages, hardware (answerable by checking the system)
- haiku+web — needs current/live data from the internet (news, outages, new releases, scores, CVEs)
- sonnet — asks to WRITE/CREATE/FIX code, scripts, configs
- opus — asks to DESIGN/EVALUATE/PLAN architecture, strategy, trade-offs
- file_search — asks WHICH FILE or WHERE a config/script/setting is
- window_manager — asks to MOVE/RESIZE/ARRANGE/MINIMIZE windows or change layout

Examples:
"what GPU do I have" → local
"is ollama running" → local
"what's my IP address" → local
"is docker running" → local
"fix my audio" → local
"is github down right now" → haiku+web
"did they release a new version of docker" → haiku+web
"is spotify having login issues" → haiku+web
"write a python retry decorator" → sonnet
"give me a bash script that monitors disk" → sonnet
"should I use REST or GraphQL" → opus
"what's the best database for time series" → opus
"what file controls my screen brightness" → file_search
"where do keybinds get defined" → file_search
"make this window bigger" → window_manager
"swap these two windows" → window_manager

Query: "{query}"
Category:"""


def _llm_classify(query: str) -> tuple[str | None, float]:
    """Ask the local LLM to classify a query into a route.

    Uses the smallest available model for speed (~200-500ms).
    Returns (route, confidence) where confidence is 0.9 if the
    LLM returns a valid class, 0.0 otherwise.
    """
    # Check cache first
    cache_key = query.strip().lower()
    if cache_key in LLM_CLASSIFY_CACHE:
        return LLM_CLASSIFY_CACHE[cache_key]

    import subprocess
    import json as _json

    # Use the best available model — classification needs reasoning
    try:
        classify_model = Path("/tmp/ollama-smart-model").read_text().strip()
    except Exception:
        classify_model = "qwen2.5:7b"

    prompt = _LLM_CLASSIFY_PROMPT.format(query=query)

    payload = _json.dumps({
        "model": classify_model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": 0.0, "num_predict": 10},
    })

    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/generate", "-d", payload],
            capture_output=True, text=True, timeout=10,
        )
        data = _json.loads(result.stdout)
        raw = data.get("response", "").strip().lower()
    except Exception:
        return (None, 0.0)

    # Parse the response — find a valid route class
    matched_route = None
    matched_conf = 0.0

    for cls in ROUTE_CLASSES:
        if cls.lower().replace("+", "") in raw.replace("+", "").replace(" ", ""):
            matched_route = cls
            matched_conf = 0.9
            break

    # Try partial match if exact match failed
    if not matched_route:
        route_map = {
            "local": "local",
            "escalate": "local_will_escalate",
            "web": "haiku+web",
            "haiku": "haiku+web",
            "sonnet": "sonnet",
            "code": "sonnet",
            "opus": "opus",
            "architect": "opus",
            "design": "opus",
            "file": "file_search",
            "search": "file_search",
            "window": "window_manager",
        }
        for keyword, route in route_map.items():
            if keyword in raw:
                matched_route = route
                matched_conf = 0.85
                break

    if matched_route:
        LLM_CLASSIFY_CACHE[cache_key] = (matched_route, matched_conf)
        # Save to DB for MLP distillation — the MLP will learn from LLM decisions
        _save_llm_routing(query, matched_route)
        return (matched_route, matched_conf)

    return (None, 0.0)


def _save_llm_routing(query: str, route: str):
    """Save LLM routing decision to DB so the MLP can learn from it on next retrain."""
    try:
        from db import get_db
        db = get_db()
        # Store in a separate table to avoid polluting query logs
        db.execute("""CREATE TABLE IF NOT EXISTS llm_routing_cache (
            id INTEGER PRIMARY KEY,
            query TEXT NOT NULL,
            route TEXT NOT NULL,
            ts TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        )""")
        db.execute("INSERT INTO llm_routing_cache (query, route) VALUES (?, ?)",
                   (query, route))
        db.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# MLRouter
# ---------------------------------------------------------------------------

_instance: "MLRouter | None" = None


class MLRouter:
    """PyTorch MLP routing classifier.

    Loads a saved model from disk if available; otherwise predict()
    returns (None, 0.0) until train() is called.
    """

    def __init__(self):
        self.model: nn.Sequential | None = None
        self.n_features = N_FEATURES
        self.n_classes = len(ROUTE_CLASSES)
        self._load()

    # ----- public API -----

    def predict(self, query: str) -> tuple[str | None, float]:
        """Predict the best route for a query.

        Uses MLP as fast path. If confidence is below LLM_THRESHOLD,
        escalates to local LLM for classification (~300ms but much
        more accurate on conversational/ambiguous queries).

        Returns:
            (route_name, confidence) or (None, 0.0) if no model loaded.
        """
        if self.model is None:
            return _llm_classify(query)

        self.model.eval()
        features = extract_features(query)
        x = torch.tensor(features, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            logits = self.model(x)
            probs = torch.softmax(logits, dim=1)
            confidence, idx = torch.max(probs, dim=1)

        route = ROUTE_CLASSES[idx.item()]
        conf = confidence.item()

        # High confidence → trust the MLP
        if conf >= LLM_CLASSIFY_THRESHOLD:
            return (route, conf)

        # Low confidence → ask the local LLM to classify
        llm_route, llm_conf = _llm_classify(query)
        if llm_route and llm_conf > conf:
            return (llm_route, llm_conf)

        return (route, conf)

    def train(self, data: list[tuple[str, str]],
              weights: list[float] | None = None) -> dict:
        """Train on labeled (query, route_label) pairs.

        Args:
            data: List of (query_text, route_label) tuples.
            weights: Optional per-sample weights (e.g. 3.0 for real data,
                     1.0 for synthetic). Must match len(data) if provided.

        Returns:
            Dict with training stats (final_loss, epochs, duration_s, etc).
        """
        # Encode
        X_list, y_list, w_list = [], [], []
        for i, (query, label) in enumerate(data):
            if label not in ROUTE_CLASSES:
                continue
            X_list.append(extract_features(query))
            y_list.append(ROUTE_CLASSES.index(label))
            w_list.append(weights[i] if weights else 1.0)

        X = torch.tensor(np.array(X_list), dtype=torch.float32)
        y = torch.tensor(y_list, dtype=torch.long)
        sample_weights = torch.tensor(w_list, dtype=torch.float32)

        # Class-balanced loss weights
        class_counts = torch.zeros(self.n_classes)
        for yi in y_list:
            class_counts[yi] += 1
        # Avoid div-by-zero for classes with no samples
        class_weights = torch.where(
            class_counts > 0,
            class_counts.sum() / (self.n_classes * class_counts),
            torch.ones(1),
        )

        # Build fresh model
        self.model = _build_model(self.n_features, self.n_classes)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3, weight_decay=1e-4)
        criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.1)

        dataset = TensorDataset(X, y)

        # Use WeightedRandomSampler when per-sample weights are provided
        if weights:
            sampler = WeightedRandomSampler(sample_weights, num_samples=len(dataset), replacement=True)
            loader = DataLoader(dataset, batch_size=32, sampler=sampler)
        else:
            loader = DataLoader(dataset, batch_size=32, shuffle=True)

        self.model.train()
        t0 = time.time()
        final_loss = 0.0

        for epoch in range(100):
            epoch_loss = 0.0
            for xb, yb in loader:
                optimizer.zero_grad()
                logits = self.model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            final_loss = epoch_loss / len(loader)

        duration = time.time() - t0

        # Count synthetic vs real for metadata
        synthetic_count = sum(1 for w in w_list if w <= 1.0)
        real_count = len(w_list) - synthetic_count

        self._save(synthetic_count=synthetic_count, real_count=real_count,
                   final_loss=final_loss)

        return {
            "final_loss": final_loss,
            "epochs": 100,
            "duration_s": round(duration, 2),
            "samples": len(X_list),
            "synthetic_count": synthetic_count,
            "real_count": real_count,
        }

    def evaluate(self, data: list[tuple[str, str]]) -> dict:
        """Train/test split evaluation.

        Args:
            data: Full labeled dataset.

        Returns:
            Dict with accuracy, per_class_accuracy, confusion_matrix.
        """
        # 80/20 split
        np.random.seed(42)
        indices = np.random.permutation(len(data))
        split = int(len(data) * 0.8)
        train_data = [data[i] for i in indices[:split]]
        test_data = [data[i] for i in indices[split:]]

        # Train
        self.train(train_data)

        # Evaluate on test set
        self.model.eval()
        confusion = np.zeros((self.n_classes, self.n_classes), dtype=int)
        correct = 0
        total = 0

        for query, label in test_data:
            if label not in ROUTE_CLASSES:
                continue
            true_idx = ROUTE_CLASSES.index(label)
            pred_route, conf = self.predict(query)
            pred_idx = ROUTE_CLASSES.index(pred_route) if pred_route else 0
            confusion[true_idx, pred_idx] += 1
            if pred_idx == true_idx:
                correct += 1
            total += 1

        accuracy = correct / total if total > 0 else 0.0

        # Per-class accuracy
        per_class = {}
        for i, cls in enumerate(ROUTE_CLASSES):
            cls_total = confusion[i].sum()
            cls_correct = confusion[i, i]
            per_class[cls] = (cls_correct / cls_total) if cls_total > 0 else 0.0

        return {
            "accuracy": round(accuracy, 4),
            "per_class_accuracy": {k: round(v, 4) for k, v in per_class.items()},
            "confusion_matrix": confusion.tolist(),
            "test_size": total,
            "train_size": len(train_data),
        }

    # ----- internal -----

    def _load(self):
        """Load saved model from disk. Tries user-trained model first, then shipped model."""
        for path in [MODEL_PATH, SHIPPED_MODEL_PATH]:
            if path.exists():
                try:
                    checkpoint = torch.load(path, weights_only=True)
                    self.model = _build_model(self.n_features, self.n_classes)
                    self.model.load_state_dict(checkpoint["model_state_dict"])
                    self.model.eval()
                    return  # loaded successfully
                except Exception:
                    continue
        self.model = None

    def _save(self, synthetic_count: int = 0, real_count: int = 0,
              final_loss: float = 0.0):
        """Save model to disk with training metadata."""
        if self.model is None:
            return
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "route_classes": ROUTE_CLASSES,
                "n_features": self.n_features,
                "timestamp": datetime.now().isoformat(),
                "synthetic_count": synthetic_count,
                "real_count": real_count,
                "final_loss": final_loss,
            },
            MODEL_PATH,
        )


def get_router() -> MLRouter:
    """Return the singleton MLRouter instance."""
    global _instance
    if _instance is None:
        _instance = MLRouter()
    return _instance


# ---------------------------------------------------------------------------
# Synthetic training data
# ---------------------------------------------------------------------------

def generate_synthetic_data() -> list[tuple[str, str]]:
    """Generate ~300+ labeled (query, route) training pairs from known patterns."""
    data: list[tuple[str, str]] = []

    # --- local (~50) ---
    local_queries = [
        "install firefox",
        "what packages do I have for python",
        "update all packages",
        "what's the weather",
        "what is my IP address",
        "how much disk space do I have",
        "what GPU do I have",
        "list installed packages",
        "how do I add a pacman repo",
        "what kernel am I running",
        "set my volume to 50%",
        "restart pipewire",
        "what time is it",
        "turn on bluetooth",
        "mute my mic",
        "what CPU do I have",
        "how much RAM is free",
        "what's my hostname",
        "list running services",
        "check systemd journal for errors",
        "how do I connect to wifi",
        "what is my screen resolution",
        "change my wallpaper",
        "what theme am I using",
        "how do I configure waybar",
        "add a workspace keybind",
        "what font is configured",
        "how do I change my terminal theme",
        "open ghostty settings",
        "customize rofi",
        "how to use dunst notifications",
        "what monitors are connected",
        "rotate my left monitor",
        "adjust monitor brightness",
        "is docker running",
        "check if postgresql is active",
        "what python version do I have",
        "list docker containers",
        "what node version is installed",
        "how do I use zellij",
        "where is my hyprland config",
        "reload hyprland",
        "show me my keybinds",
        "what's using port 8080",
        "how do I pair bluetooth headphones",
        "mount my USB drive",
        "what's my uptime",
        "check temperature sensors",
        # --- Counter-examples: disk/space/partition queries are LOCAL not file_search ---
        "show disk usage by partition",
        "how much disk space is left",
        "check my disk usage",
        "what's the disk space on root",
        "show filesystem usage",
        "how full is my hard drive",
        "check storage space remaining",
        "list partition sizes",
        "show me disk usage stats",
        "how much space is used on the NVMe",
        "df output for all drives",
        "is my drive getting full",
        # --- Counter-examples: system info with words that overlap file_search/WM ---
        "what monitors are connected",
        "show monitor layout",
        "check display configuration",
        "what's my screen arrangement",
        "how many monitors do I have",
        "what displays are connected",
        "show all connected monitors and their resolution",
        "list my displays",
        "how do I set environment variables in hyprland",
        "configure hyprland animations",
        "set hyprland window gaps",
        "change hyprland keybindings",
        "what hyprland version am I on",
        "what are my current hyprland animations",
        "how do I change hyprland border colors",
        "what are my hyprland keybindings",
        # --- Counter-examples: system check queries ---
        "what process is using port 3000",
        "check if ollama is running",
        "is bluetooth on",
        "toggle bluetooth on",
        "turn bluetooth off",
        "check swap usage",
        "what's my CPU temperature",
        "show memory usage by process",
        # --- Counter-examples: queries about WM that are info not actions ---
        "what window manager am I using",
        "what compositor is running",
        "show me the hyprland log",
        "what's taking up space in home",
        "check if my SSH key is loaded",
        "show journal errors from today",
    ]
    data.extend((q, "local") for q in local_queries)

    # --- local_will_escalate (~40) ---
    escalate_queries = [
        "explain the difference between Wayland and X11 protocol internals",
        "how does the Linux kernel scheduler work in detail",
        "write a comprehensive comparison of btrfs vs ext4 vs zfs",
        "what are the security implications of running containers as root",
        "explain how PipeWire's session management differs from PulseAudio",
        "give me a deep dive into how Hyprland's rendering pipeline works",
        "what's the best approach to implementing a custom Wayland compositor",
        "explain how systemd-resolved interacts with NetworkManager in detail",
        "how does the AMD RDNA 4 architecture differ from RDNA 3",
        "explain the mathematical foundations of audio signal processing",
        "what are the trade-offs between different IPC mechanisms on Linux",
        "give me a detailed comparison of container runtimes",
        "how does the Linux memory management subsystem handle NUMA",
        "explain the internals of the ext4 journal",
        "what are the security best practices for a multi-tenant Kubernetes cluster",
        "describe the full boot process from UEFI to userspace",
        "how does eBPF work at the kernel level",
        "explain how Vulkan memory allocation strategies affect GPU performance",
        "compare the architectures of different Linux audio subsystems",
        "what's the full lifecycle of a network packet in the Linux kernel",
        "explain how copy-on-write works in modern filesystems",
        "give me a thorough analysis of Linux cgroup v2 resource management",
        "how do interrupt handlers work in the Linux kernel",
        "explain the differences between io_uring and traditional async I/O",
        "what is the complete architecture of the Wayland security model",
        "describe how DRM/KMS works for display management in Linux",
        "how does GCC optimize code compared to LLVM",
        "explain the internals of the Rust borrow checker",
        "what are all the ways Linux handles shared memory between processes",
        "compare the merits of microkernel vs monolithic kernel design",
        "how does the OOM killer decide which process to terminate",
        "explain how transparent huge pages work and their performance impact",
        "give a deep technical explanation of how WireGuard works vs OpenVPN",
        "what are all the kernel parameters that affect network performance",
        "how does the Linux page cache interact with direct I/O",
        "explain the complete lifecycle of a system call",
        "what are the implications of speculative execution vulnerabilities on AMD",
        "how does PCI passthrough work for GPU virtualization",
        "describe the architecture of the Linux device model",
        "compare BPF vs kprobes vs tracepoints for kernel tracing",
    ]
    data.extend((q, "local_will_escalate") for q in escalate_queries)

    # --- haiku+web (~45) ---
    web_queries = [
        "latest news",
        "what's trending on Twitter",
        "who won the game last night",
        "current stock price of NVIDIA",
        "what happened in the news today",
        "score of the Lakers game",
        "latest Linux kernel release",
        "what's the current Bitcoin price",
        "who won the election",
        "trending topics right now",
        "latest Arch Linux news",
        "what's new in the tech world",
        "current weather forecast for New York",
        "who won the Super Bowl",
        "latest Python release version",
        "what are the top headlines today",
        "score of the World Cup match",
        "latest cybersecurity news",
        "what's new in AI today",
        "current price of gold",
        "who won the Grammy awards",
        "latest updates on Ukraine",
        "trending GitHub repositories",
        "what movies are in theaters now",
        "latest Steam sale",
        "current gas prices",
        "who won the UFC fight",
        "latest AMD GPU driver release",
        "what's the latest Hyprland version",
        "trending on Hacker News",
        "current weather in Tokyo",
        "who won the Oscar for best picture",
        "latest Rust release notes",
        "what concerts are happening near me",
        "latest security vulnerabilities announced",
        "score of the NFL game today",
        "what's new in open source this week",
        "current exchange rate USD to EUR",
        "latest SpaceX launch update",
        "who won the Nobel Prize this year",
        "current COVID statistics",
        "latest Docker release",
        "what happened at CES this year",
        "trending anime this season",
        "latest Wayland protocol updates",
        # --- Counter-examples: security/CVE/vulnerability queries need web data ---
        "any new CVEs this week",
        "latest security vulnerabilities for linux",
        "new CVEs for kernel this month",
        "are there any zero-day exploits announced recently",
        "latest security advisory for openssh",
        # --- Counter-examples: indirect web queries without "latest/trending" ---
        "has the new mesa driver been released yet",
        "is there a new version of hyprland out",
        "did they release a new kernel this week",
        "is cloudflare having issues right now",
        "is github down",
        "any service outages today",
        "what games came out this week on steam",
        "what games released this month",
        "what did Linus say about rust in the kernel recently",
        "any new exploits for AMD GPUs",
        "did the mesa update fix the RDNA issue",
        "is there a new docker release",
        "are there any new arch linux announcements",
        "what's new in the wayland world",
        # --- Conversational: "did they fix", "is X up to date", "when does" ---
        "did they fix the mesa RDNA4 bug",
        "did they patch that kernel vulnerability",
        "is the arch linux keyring up to date",
        "is my mesa version current",
        "when does the next kernel release come out",
        "when is the next ubuntu LTS",
        "is there a new version of ollama available",
        "did mass layoffs hit any more tech companies",
    ]
    data.extend((q, "haiku+web") for q in web_queries)

    # --- sonnet (~45) ---
    sonnet_queries = [
        "write a REST API in Python with FastAPI",
        "debug this function that's throwing an index error",
        "implement a binary search tree in Rust",
        "write a React component for a todo list",
        "refactor this class to use the strategy pattern",
        "create a Docker compose file for a Node app with PostgreSQL",
        "write a bash script to backup my databases",
        "implement authentication middleware in Express",
        "debug why my async function isn't awaiting properly",
        "write a Python decorator for caching",
        "create a systemd service file for my app",
        "implement a WebSocket server in Python",
        "write unit tests for this function",
        "create a GitHub Actions workflow for CI/CD",
        "implement pagination for a REST API",
        "write a SQL migration to add user roles",
        "debug this segfault in my C code",
        "create a Makefile for this project",
        "implement a rate limiter middleware",
        "write a parser for a custom config format",
        "refactor this spaghetti code into clean modules",
        "implement OAuth2 login flow",
        "write a CLI tool in Rust that processes CSV files",
        "create a Python script to scrape a website",
        "implement a connection pool for PostgreSQL",
        "write a Kubernetes deployment manifest",
        "debug why my React state isn't updating",
        "create a monitoring dashboard with Grafana queries",
        "implement error handling for this API",
        "write a data pipeline with Apache Kafka consumer",
        "fix the race condition in this multithreaded code",
        "implement a LRU cache from scratch",
        "write a Discord bot command handler",
        "create an Ansible playbook for server provisioning",
        "implement a JWT refresh token rotation system",
        "write a regex to parse log files",
        "debug this memory leak in my Node application",
        "create a Python async web scraper",
        "implement a message queue with Redis",
        "write integration tests for the payment module",
        "code a function to merge two sorted linked lists",
        "implement a trie data structure in Python",
        "write a GraphQL schema for a blog",
        "create a Terraform module for AWS ECS",
        "implement server-sent events in FastAPI",
        # --- Negative samples: local entities with code intent ---
        "write a systemd service manager in python",
        "implement a PipeWire audio routing tool",
        "create a GPU monitoring dashboard in rust",
        "write a docker container health checker",
        "implement a waybar module in python",
        # --- Conversational forms: "give me", "can you", "I need" ---
        "give me a systemd timer that runs every 5 minutes",
        "give me a bash script that monitors disk usage",
        "can you write a regex for email validation",
        "can you make a script that backs up my configs",
        "I need a python script that watches for file changes",
        "I need a function that retries on failure",
        "how would you implement a rate limiter",
        "how would you build a CLI that parses JSON",
    ]
    data.extend((q, "sonnet") for q in sonnet_queries)

    # --- opus (~40) ---
    opus_queries = [
        "architect a microservice system for an e-commerce platform",
        "design a distributed event sourcing system",
        "review the security of my authentication system",
        "design a system that handles 10 million concurrent users",
        "architect a real-time data pipeline for IoT devices",
        "create a comprehensive technical specification for a SaaS platform",
        "design a multi-region database replication strategy",
        "perform a security audit of this codebase",
        "architect a zero-trust network for my infrastructure",
        "design a machine learning pipeline for production",
        "create a disaster recovery plan for our infrastructure",
        "architect a plugin system for extensibility",
        "design a consensus algorithm for distributed systems",
        "review and redesign our API versioning strategy",
        "architect a multi-tenant SaaS data isolation model",
        "design a CQRS and event sourcing architecture",
        "create a comprehensive migration plan from monolith to microservices",
        "architect a real-time collaboration system like Google Docs",
        "design a secure secrets management infrastructure",
        "perform a deep code review focusing on performance bottlenecks",
        "architect a content delivery network from scratch",
        "design a recommendation engine architecture",
        "create a technical architecture document for a fintech platform",
        "architect a fault-tolerant message processing system",
        "design a data lake architecture with proper governance",
        "review the cryptographic implementation in our auth module",
        "architect a serverless event-driven processing pipeline",
        "design a comprehensive observability stack",
        "create a threat model for our application",
        "architect a search engine with relevance ranking",
        "design a distributed task scheduling system",
        "perform a comprehensive performance review of this system",
        "architect a secure API gateway with rate limiting and auth",
        "design a database sharding strategy for horizontal scaling",
        "create a technical roadmap for platform modernization",
        "architect a real-time analytics dashboard backend",
        "design a CI/CD pipeline architecture for a large monorepo",
        "review the overall architecture for scalability concerns",
        "architect a feature flag system with gradual rollouts",
        "design an end-to-end encryption system for messaging",
        # --- Counter-examples: "create/design/strategy" queries that are opus not local ---
        "create a threat model for the AI router",
        "create a threat model for this service",
        "design an end-to-end testing strategy for a voice assistant",
        "design a comprehensive testing strategy for this app",
        "create a capacity planning model for our infrastructure",
        "design a rollback strategy for database migrations",
        # --- Counter-examples: "design/plugin/costa" queries are opus not file_search ---
        "design a plugin architecture for costa OS",
        "design a plugin system for costa extensions",
        "architect a module system for costa",
        "design a caching layer for the costa AI router",
        "create an extension framework for costa OS",
        # --- Negative samples: local entities with architecture intent ---
        "design a GPU scheduling system for shared workstations",
        "design a VRAM management strategy for multi-model inference",
        "architect a system where ollama serves multiple users",
        "plan a migration from PulseAudio to PipeWire for a fleet",
        "design a docker orchestration strategy for development",
        "evaluate security implications of running AI models with root",
        "design a graceful degradation strategy when GPU memory is full",
        "create a data retention policy for the AI query database",
        "design a monitoring strategy for a linux desktop OS",
        # --- Conversational forms: "should I", "what's the best", "how should I" ---
        "should I use REST or GraphQL for this project",
        "should I use SQLite or Postgres for this",
        "what's the best way to structure a monorepo",
        "what's the best approach for handling auth",
        "how should I handle secrets in my deployment",
        "what database would you recommend for time series data",
        "how do I make my voice assistant work offline",
        "what's the right architecture for a real-time dashboard",
        "how should I approach this migration",
        "what would you recommend for caching in this system",
    ]
    data.extend((q, "opus") for q in opus_queries)

    # --- file_search (~40) ---
    file_search_queries = [
        "find that rust file I was working on",
        "where is my hyprland config",
        "find all Python files in this project",
        "locate the Docker compose file",
        "where did I put the database migration",
        "find files containing TODO comments",
        "search for the config file with API keys",
        "where is the waybar style file",
        "find all test files",
        "locate the systemd service file for costa",
        "where is the package.json for the frontend",
        "find the largest files in my home directory",
        "search for files modified today",
        "where did I save that script",
        "find all markdown files in docs",
        "locate the Cargo.toml",
        "where is the .env file",
        "find files with the word 'deprecated'",
        "search for configuration yaml files",
        "where is the main entry point of this app",
        "find all shell scripts",
        "locate the requirements.txt",
        "where are the log files",
        "find the CSS file for the theme",
        "search for files larger than 100MB",
        "where is the Makefile",
        "find all JSON config files",
        "locate the SSH config",
        "where did I put my notes",
        "find the source file for the router",
        "search for the font configuration",
        "where is the wallpaper directory",
        "find all YAML files in configs",
        "locate my zshrc",
        "where is the PipeWire config",
        "find recently modified Python files",
        "search for the backup script",
        "where is the Dockerfile",
        "find all files matching *.service",
        "locate the knowledge base files",
        # --- Counter-examples: indirect file search without "find/where/locate" ---
        "which script runs when I press the keybind",
        "what config controls the waybar clock",
        "what config file sets the cursor theme",
        "which file defines the color palette",
        "what script handles the wallpaper",
        "which module handles model selection",
        "what file runs at startup",
        "which config sets the default font",
        "where are the voice recordings stored",
        "what file defines the power menu",
        # --- Conversational: "what controls", "I need to edit" ---
        "what controls my screen brightness",
        "where do keybinds get defined",
        "what sets up my PATH variable",
        "I need to edit the volume keybind",
        "I need to change the notification timeout",
        "what determines my default browser",
        "how do I change what happens at startup",
    ]
    data.extend((q, "file_search") for q in file_search_queries)

    # --- window_manager (~40) ---
    wm_queries = [
        "move firefox to workspace 3",
        "tile the current window to the left",
        "make this window fullscreen",
        "float the current window",
        "move this window to the right monitor",
        "resize the window to half the screen",
        "close this window",
        "switch to workspace 2",
        "snap this window to the top right corner",
        "minimize all windows",
        "focus the terminal window",
        "move all windows to workspace 1",
        "split the screen with firefox and terminal",
        "toggle floating for this window",
        "move the window 100 pixels to the right",
        "put this on the left monitor",
        "arrange windows in a grid",
        "focus the window on the right",
        "swap this window with the one on the left",
        "bring the Spotify window here",
        "send this to the top monitor",
        "maximize the current window",
        "cycle through windows",
        "pin this window to all workspaces",
        "move this to workspace 5",
        "switch focus to the next window",
        "put firefox on the left and terminal on the right",
        "resize window width to 800 pixels",
        "center this window on screen",
        "move the window to the other monitor",
        "group these windows together",
        "ungroup the current window",
        "set opacity of this window to 80%",
        "move the focused window down",
        "switch to the next workspace",
        "move all floating windows to tiled",
        "bring all windows to current workspace",
        "focus the VS Code window",
        "move window to the secondary monitor",
        "tile firefox next to my editor",
        # --- Counter-examples: conversational WM without explicit keywords ---
        "make the terminal bigger",
        "make this window smaller",
        "I need these two windows side by side",
        "I need firefox and the editor next to each other",
        "can you put that on my other screen",
        "minimize everything",
        "minimize all windows",
        "hide all windows",
        "show the desktop",
        "I want this bigger",
        "switch me to the gaming workspace",
        # --- More conversational WM ---
        "I can barely see this window make it bigger",
        "this is taking up the whole screen get it out",
        "put everything back to normal",
        "arrange my windows so I can see everything",
        "swap these two around",
        "get this off my screen",
        "can I have browser on one side and code on the other",
        "just give me a clean desktop",
        "get rid of everything on screen",
        "I want to see all my windows at once",
    ]
    data.extend((q, "window_manager") for q in wm_queries)

    return data


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _print_report(results: dict):
    """Pretty-print evaluation results."""
    print(f"\n{'=' * 60}")
    print(f"  ML Router Evaluation Report")
    print(f"{'=' * 60}")
    print(f"  Train size:  {results['train_size']}")
    print(f"  Test size:   {results['test_size']}")
    print(f"  Accuracy:    {results['accuracy']:.1%}")
    print(f"\n  Per-class accuracy:")
    for cls, acc in results["per_class_accuracy"].items():
        bar = "#" * int(acc * 30)
        print(f"    {cls:<22s} {acc:.1%}  {bar}")

    print(f"\n  Confusion matrix (rows=true, cols=predicted):")
    header = "  " + " " * 22 + "".join(f"{c[:6]:>7s}" for c in ROUTE_CLASSES)
    print(header)
    for i, row in enumerate(results["confusion_matrix"]):
        label = ROUTE_CLASSES[i]
        vals = "".join(f"{v:7d}" for v in row)
        print(f"    {label:<20s}{vals}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ml_router.py [train|eval|predict \"query\"]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "train":
        print("Generating synthetic training data...")
        data = generate_synthetic_data()
        print(f"Generated {len(data)} labeled samples")
        print("Training ML router...")
        router = MLRouter()
        stats = router.train(data)
        print(f"Training complete in {stats['duration_s']}s")
        print(f"  Final loss: {stats['final_loss']:.4f}")
        print(f"  Samples:    {stats['samples']}")
        print(f"  Model saved to {MODEL_PATH}")

    elif cmd == "eval":
        print("Generating synthetic training data...")
        data = generate_synthetic_data()
        print(f"Generated {len(data)} labeled samples")
        print("Running train/test evaluation...")
        router = MLRouter()
        results = router.evaluate(data)
        _print_report(results)

    elif cmd == "predict":
        if len(sys.argv) < 3:
            print("Usage: python3 ml_router.py predict \"query text\"")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        router = get_router()
        route, confidence = router.predict(query)
        if route is None:
            print("No trained model found. Run 'python3 ml_router.py train' first.")
            sys.exit(1)
        print(f"Query:      {query}")
        print(f"Route:      {route}")
        print(f"Confidence: {confidence:.1%}")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 ml_router.py [train|eval|predict \"query\"]")
        sys.exit(1)
