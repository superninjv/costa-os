#!/usr/bin/env python3
"""Generate real training data for the two-stage AST router.

Scans ~/projects/, generates natural queries referencing real code symbols,
classifies them with Mistral (free, volume) and Claude (quality subset),
captures AST features alongside each query.

Usage:
    python3 generate_training_data.py                    # Full pipeline
    python3 generate_training_data.py --inventory-only   # Just scan files
    python3 generate_training_data.py --classify-only    # Just classify (reuse inventory)
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECTS_DIR = Path.home() / "projects"
AI_ROUTER_DIR = Path(__file__).parent
TRAINING_DATA_DIR = AI_ROUTER_DIR / "training_data"
INVENTORY_FILE = TRAINING_DATA_DIR / "inventory.json"
QUERIES_FILE = TRAINING_DATA_DIR / "queries.json"
OUTPUT_FILE = TRAINING_DATA_DIR / "stage2_labeled.json"
PROVIDERS_YAML = Path.home() / "projects" / "costa-os" / "configs" / "costa" / "providers.yaml"
COSTA_ENV_FILE = Path.home() / ".config" / "costa" / "env"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILES = 1000
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".cache", "dist", "build",
    ".next", "target", "vendor", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", "coverage", ".nyc_output", "out", ".output",
    "eggs", ".eggs", "*.egg-info", ".DS_Store", ".idea", ".vscode",
}

SUPPORTED_EXTENSIONS = {
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".rs", ".go", ".sh", ".bash", ".zsh", ".rb", ".php", ".swift",
    ".kt", ".java", ".lua", ".c", ".h", ".cpp", ".cc", ".hpp",
    ".ex", ".exs", ".hs", ".ml",
}

ROUTE_CLASSES = [
    "local",
    "local_will_escalate",
    "haiku+web",
    "sonnet",
    "opus",
    "file_search",
    "window_manager",
]

# AST feature spec mirrors ml_router.py extract_ast_features
AST_LANGUAGES = [
    "python", "javascript", "typescript", "tsx", "rust", "go",
    "bash", "c", "cpp", "java", "lua", "other",
]
AST_SYMBOL_KINDS = [
    "function", "class", "struct", "enum", "interface", "type", "module", "variable",
]
N_AST_FEATURES = 65

# Mistral: free devstral model, classify all queries at weight 2.0
MISTRAL_MODEL = "devstral-small-2505"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_WEIGHT = 2.0
MISTRAL_RATE_LIMIT = 0.2  # seconds between batch requests

# Gemini: strong reasoning classifier, classify all queries at weight 4.0
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_WEIGHT = 4.0
GEMINI_RATE_LIMIT = 0.5  # 15 RPM free tier → be conservative

# Claude Haiku: highest quality classifier, stratified 1000-sample subset, weight 8.0
CLAUDE_HAIKU_MODEL = "claude-haiku-4-5"
CLAUDE_WEIGHT = 8.0
CLAUDE_RATE_LIMIT = 0.5  # seconds between requests
CLAUDE_SAMPLE_SIZE = 1000

# Non-code generic queries to mix in (window_manager, haiku+web, local)
GENERIC_QUERIES = [
    ("move this window to workspace 3", "window_manager"),
    ("move firefox to the right monitor", "window_manager"),
    ("tile windows side by side", "window_manager"),
    ("float the current window", "window_manager"),
    ("resize window to half screen", "window_manager"),
    ("close the active window", "window_manager"),
    ("move window to workspace 5", "window_manager"),
    ("snap window to top half", "window_manager"),
    ("focus the firefox window", "window_manager"),
    ("swap windows between workspaces", "window_manager"),
    ("latest security advisory for openssl", "haiku+web"),
    ("latest release notes for pytorch", "haiku+web"),
    ("what happened in tech news today", "haiku+web"),
    ("current CVE for log4j", "haiku+web"),
    ("what is the latest stable kernel version", "haiku+web"),
    ("nvidia driver release today", "haiku+web"),
    ("latest python release announcement", "haiku+web"),
    ("recent security vulnerability in openssh", "haiku+web"),
    ("what version of hyprland is current", "local"),
    ("is docker running", "local"),
    ("how much disk space do I have", "local"),
    ("what GPU do I have", "local"),
    ("list running processes", "local"),
    ("what monitors are connected", "local"),
    ("check my CPU usage", "local"),
    ("what kernel version am I on", "local"),
    ("is bluetooth enabled", "local"),
    ("check my RAM usage", "local"),
    ("what packages do I have installed", "local"),
    ("show network connections", "local"),
    ("how much swap is used", "local"),
    ("is ollama running", "local"),
    ("what is my IP address", "local"),
]


# ---------------------------------------------------------------------------
# Load provider config + API keys
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load API keys from ~/.config/costa/env (KEY=value per line)."""
    env: dict[str, str] = {}
    if COSTA_ENV_FILE.exists():
        for line in COSTA_ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    # Also check real environment
    for key in ("MISTRAL_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def load_providers() -> dict:
    """Load provider config from providers.yaml."""
    if PROVIDERS_YAML.exists():
        with open(PROVIDERS_YAML) as f:
            return yaml.safe_load(f) or {}
    return {}


# ---------------------------------------------------------------------------
# AST feature extraction (mirrors ml_router.py extract_ast_features)
# ---------------------------------------------------------------------------

def compute_ast_features(file_path: str) -> list[float]:
    """Compute 65-float AST feature vector for a file.

    Mirrors the spec in ml_router.py extract_ast_features so features are
    compatible with the Stage 2 model training.
    """
    try:
        import ast_parser
        summary = ast_parser.get_file_summary(file_path)
        complexity_data = ast_parser.get_complexity(file_path)
    except Exception:
        return [0.0] * N_AST_FEATURES

    feats: list[float] = []

    # [0] complexity_max (normalized /50)
    # [1] complexity_avg (normalized /20)
    complexities: list[float] = []
    if isinstance(complexity_data, dict):
        funcs = complexity_data.get("functions", [])
        if isinstance(funcs, list):
            complexities = [float(f.get("complexity", 1)) for f in funcs if isinstance(f, dict)]
        total_c = complexity_data.get("total_complexity")
        avg_c = complexity_data.get("avg_complexity")
        if not complexities and total_c is not None:
            complexities = [float(total_c)]

    complexity_max = max(complexities) if complexities else 0.0
    complexity_avg = (sum(complexities) / len(complexities)) if complexities else 0.0
    feats.append(min(complexity_max / 50.0, 1.0))   # [0]
    feats.append(min(complexity_avg / 20.0, 1.0))   # [1]

    # [2] scope_depth_max — not easily available, use 0
    feats.append(0.0)                                # [2]

    # [3] file_line_count (normalized /2000)
    line_count = 0.0
    if isinstance(summary, dict):
        line_count = float(summary.get("total_lines", 0))
    feats.append(min(line_count / 2000.0, 1.0))     # [3]

    # [4..15] language_one_hot (12 floats)
    lang = "other"
    if isinstance(summary, dict):
        lang = (summary.get("language") or "other").lower()
    if lang not in AST_LANGUAGES:
        lang = "other"
    for l in AST_LANGUAGES:
        feats.append(1.0 if l == lang else 0.0)     # [4..15]

    # [16..23] symbol_counts_by_kind (8 floats, each normalized /50)
    symbols: dict = {}
    if isinstance(summary, dict):
        symbols = summary.get("symbols", {}) or {}
    for kind in AST_SYMBOL_KINDS:
        count = float(symbols.get(kind, 0))
        feats.append(min(count / 50.0, 1.0))        # [16..23]

    # [24] total_symbol_count (normalized /100)
    total_symbols = sum(float(v) for v in symbols.values() if isinstance(v, (int, float)))
    feats.append(min(total_symbols / 100.0, 1.0))   # [24]

    # [25] query_symbol_match — unknown at feature-extraction time (set 0; caller can override)
    feats.append(0.0)                                # [25]

    # [26] dependency_count — use import count as proxy (normalized /30)
    import_count = 0.0
    if isinstance(summary, dict):
        imports = summary.get("imports", [])
        import_count = float(len(imports)) if isinstance(imports, list) else 0.0
    feats.append(min(import_count / 30.0, 1.0))     # [26]

    # [27] is_api_file: "api" or "route" or "handler" or "endpoint" in file path
    fp_lower = file_path.lower()
    is_api = any(kw in fp_lower for kw in ("api", "route", "handler", "endpoint"))
    feats.append(1.0 if is_api else 0.0)             # [27]

    # [28] import_count (real, normalized /30)
    feats.append(min(import_count / 30.0, 1.0))     # [28]

    # [29] has_high_complexity: any function with complexity > 10
    feats.append(1.0 if complexity_max > 10.0 else 0.0)  # [29]

    # [30] function_count (normalized /50)
    function_count = float(symbols.get("function", 0))
    feats.append(min(function_count / 50.0, 1.0))   # [30]

    # Pad to exactly N_AST_FEATURES=65
    while len(feats) < N_AST_FEATURES:
        feats.append(0.0)

    return feats[:N_AST_FEATURES]


def compute_query_symbol_match(query: str, summary: dict) -> float:
    """Check if any query word matches a top-level symbol name in the file."""
    if not isinstance(summary, dict):
        return 0.0
    top_level = summary.get("top_level", [])
    if not top_level:
        return 0.0
    query_words = set(query.lower().split())
    symbol_names = set()
    for s in top_level:
        if isinstance(s, dict):
            name = s.get("name", "")
        else:
            name = str(s)
        if name:
            symbol_names.add(name.lower())
    return 1.0 if (query_words & symbol_names) else 0.0


# ---------------------------------------------------------------------------
# 1. Inventory files
# ---------------------------------------------------------------------------

def inventory_files(projects_dir: Path, max_files: int = MAX_FILES) -> list[dict]:
    """Walk projects_dir, parse with ast_parser, return list of file summaries.

    Each entry: {path, basename, language, symbols, imports, top_level, total_lines}
    """
    try:
        import ast_parser
    except ImportError:
        print("ERROR: ast_parser not available. Run from the ai-router/ directory.", file=sys.stderr)
        sys.exit(1)

    results: list[dict] = []
    seen_paths: set[str] = set()

    for root, dirs, files in os.walk(projects_dir):
        # Prune skip directories in-place
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for fname in files:
            if len(results) >= max_files:
                break
            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = str(Path(root) / fname)
            real = os.path.realpath(filepath)
            if real in seen_paths:
                continue
            seen_paths.add(real)

            # Skip files > 500KB (too large for useful summaries)
            try:
                size = os.path.getsize(filepath)
                if size > 500 * 1024:
                    continue
            except OSError:
                continue

            summary = ast_parser.get_file_summary(filepath)
            if not isinstance(summary, dict) or not summary.get("parseable"):
                continue

            symbols_dict = summary.get("symbols", {}) or {}
            total_symbols = sum(symbols_dict.values()) if symbols_dict else 0
            if total_symbols == 0:
                continue  # empty file, no useful queries

            top_level = summary.get("top_level", [])
            imports = summary.get("imports", [])

            results.append({
                "path": filepath,
                "basename": Path(filepath).name,
                "language": summary.get("language", "unknown"),
                "symbols": symbols_dict,
                "imports": imports,
                "top_level": top_level,
                "total_lines": summary.get("total_lines", 0),
            })

        if len(results) >= max_files:
            break

    return results


# ---------------------------------------------------------------------------
# 2. Generate queries from inventory
# ---------------------------------------------------------------------------

def _extract_package_names(imports: list[str]) -> list[str]:
    """Heuristically extract top-level package names from import strings."""
    packages = []
    for imp in imports[:10]:
        imp = imp.strip()
        # "import foo" or "from foo import bar"
        if imp.startswith("from "):
            parts = imp.split()
            if len(parts) >= 2:
                pkg = parts[1].split(".")[0]
                if pkg and not pkg.startswith(".") and len(pkg) > 1:
                    packages.append(pkg)
        elif imp.startswith("import "):
            parts = imp.split()
            if len(parts) >= 2:
                pkg = parts[1].split(",")[0].split(".")[0].strip()
                if pkg and len(pkg) > 1:
                    packages.append(pkg)
        elif imp.startswith("require("):
            # JS: require('pkg')
            m = imp.strip("require()'\"")
            pkg = m.split("/")[0].lstrip("@")
            if pkg and len(pkg) > 1:
                packages.append(pkg)
    return list(dict.fromkeys(packages))  # deduplicate preserving order


def generate_queries(inventory: list[dict]) -> list[dict]:
    """For each file in inventory, generate 3-7 natural queries.

    Returns list of: {query, expected_route, file_path}
    """
    queries: list[dict] = []

    for entry in inventory:
        path = entry["path"]
        basename = entry["basename"]
        top_level = entry.get("top_level", [])
        imports = entry.get("imports", [])
        symbols_dict = entry.get("symbols", {})

        # Collect names by kind
        functions = []
        classes = []
        all_names = []
        for sym in top_level:
            if isinstance(sym, dict):
                name = sym.get("name", "")
                kind = sym.get("kind", "")
                if name:
                    all_names.append(name)
                    if kind == "function":
                        functions.append(name)
                    elif kind == "class":
                        classes.append(name)

        if not all_names:
            continue

        # Cap at 5 functions + 3 classes to avoid too many queries per large file
        functions = functions[:5]
        classes = classes[:3]

        # Generate function-level queries → code tasks
        for fn in functions:
            queries.append({
                "query": f"refactor {fn} in {basename}",
                "expected_route": "sonnet",
                "file_path": path,
            })
            if random.random() < 0.4:
                queries.append({
                    "query": f"write unit tests for {fn}",
                    "expected_route": "sonnet",
                    "file_path": path,
                })
            if random.random() < 0.3:
                queries.append({
                    "query": f"debug {fn} it's returning wrong results",
                    "expected_route": "sonnet",
                    "file_path": path,
                })
            if random.random() < 0.2:
                queries.append({
                    "query": f"optimize {fn} for performance",
                    "expected_route": "sonnet",
                    "file_path": path,
                })

        # Generate class-level queries → local or sonnet
        for cls in classes:
            queries.append({
                "query": f"what does {cls} do in {basename}",
                "expected_route": "local",
                "file_path": path,
            })
            if random.random() < 0.5:
                queries.append({
                    "query": f"add a method to {cls} for validation",
                    "expected_route": "sonnet",
                    "file_path": path,
                })

        # Symbol-finding query → file_search
        if all_names:
            sym = random.choice(all_names)
            queries.append({
                "query": f"find where {sym} is defined",
                "expected_route": "file_search",
                "file_path": path,
            })
            if random.random() < 0.5:
                queries.append({
                    "query": f"which file defines {sym}",
                    "expected_route": "file_search",
                    "file_path": path,
                })

        # Architecture/design query → opus
        if random.random() < 0.25:
            queries.append({
                "query": f"design a better architecture for {basename}",
                "expected_route": "opus",
                "file_path": path,
            })

        # Web query from imports → haiku+web
        packages = _extract_package_names(imports)
        if packages:
            pkg = random.choice(packages)
            queries.append({
                "query": f"latest security advisory for {pkg}",
                "expected_route": "haiku+web",
                "file_path": path,
            })
            if random.random() < 0.4:
                queries.append({
                    "query": f"latest release notes for {pkg}",
                    "expected_route": "haiku+web",
                    "file_path": path,
                })

        # Escalation candidate → local_will_escalate
        if random.random() < 0.2:
            name = random.choice(all_names)
            queries.append({
                "query": f"explain how {name} works in depth",
                "expected_route": "local_will_escalate",
                "file_path": path,
            })

    # Mix in generic non-code queries (window_manager, haiku+web, local)
    # Target: ~500 generic queries out of total
    n_generic = min(500, len(queries) // 8 + len(GENERIC_QUERIES))
    generic_pool = GENERIC_QUERIES * (n_generic // len(GENERIC_QUERIES) + 1)
    generic_sample = random.sample(generic_pool, min(n_generic, len(generic_pool)))
    for q_text, route in generic_sample:
        queries.append({
            "query": q_text,
            "expected_route": route,
            "file_path": None,
        })

    # Shuffle for even distribution
    random.shuffle(queries)

    print(f"Generated {len(queries)} queries from {len(inventory)} files")
    return queries


# ---------------------------------------------------------------------------
# 3. LLM classification
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT = (
    "You are a routing classifier for Costa OS, an AI-native Linux desktop. "
    "Classify each query into exactly one of these route classes:\n"
    "  local — answered by local Ollama (system info, config questions, simple facts)\n"
    "  local_will_escalate — starts local but likely escalates to cloud (complex explanations)\n"
    "  haiku+web — needs web search (news, latest releases, CVEs, current events)\n"
    "  sonnet — code task requiring a capable cloud model (refactor, write, debug, test)\n"
    "  opus — complex architecture/design/security requiring the best model\n"
    "  file_search — finding which file or where a symbol is defined\n"
    "  window_manager — desktop window management action (move, tile, resize, focus)\n\n"
    "Respond with ONLY the class name, nothing else."
)

# Batch classification prompt: classify multiple queries in one API call
CLASSIFY_BATCH_PROMPT = (
    "You are a routing classifier for Costa OS, an AI-native Linux desktop. "
    "Classify each numbered query into exactly one route class.\n\n"
    "Route classes:\n"
    "  local — answered by local Ollama (system info, config questions, simple facts)\n"
    "  local_will_escalate — starts local but likely escalates to cloud (complex explanations)\n"
    "  haiku+web — needs web search (news, latest releases, CVEs, current events)\n"
    "  sonnet — code task requiring a capable cloud model (refactor, write, debug, test)\n"
    "  opus — complex architecture/design/security requiring the best model\n"
    "  file_search — finding which file or where a symbol is defined\n"
    "  window_manager — desktop window management action (move, tile, resize, focus)\n\n"
    "Respond with ONLY numbered lines like:\n1. sonnet\n2. local\n3. file_search\n"
    "No explanations. One class per line."
)


def _parse_batch_response(raw: str, batch_size: int) -> list[str | None]:
    """Parse a numbered batch classification response.

    Expected format: '1. sonnet\n2. local\n3. file_search'
    Returns list of route strings (or None for unparseable lines).
    """
    import re
    results: list[str | None] = [None] * batch_size
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(\d+)\.\s*(\S+)", line)
        if m:
            idx = int(m.group(1)) - 1
            route = m.group(2).lower().rstrip(".,!").strip()
            if 0 <= idx < batch_size:
                if route in ROUTE_CLASSES:
                    results[idx] = route
                else:
                    for rc in ROUTE_CLASSES:
                        if rc in route or route in rc:
                            results[idx] = rc
                            break
    return results


def classify_with_api(
    queries: list[dict],
    base_url: str,
    api_key: str,
    model: str,
    rate_limit: float,
    weight: float,
    source_label: str,
    queries_per_call: int = 20,
) -> list[dict]:
    """Classify queries via OpenAI-compatible chat API using batch prompts.

    Sends multiple queries per API call to minimize total requests.
    8500 queries at 20/call = 427 API calls instead of 8500.
    """
    classified: list[dict] = []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    total = len(queries)

    for i in range(0, total, queries_per_call):
        batch = queries[i : i + queries_per_call]

        # Build numbered query list
        numbered = "\n".join(
            f"{j+1}. {entry['query']}" for j, entry in enumerate(batch)
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": CLASSIFY_BATCH_PROMPT},
                {"role": "user", "content": numbered},
            ],
            "max_tokens": len(batch) * 25,
            "temperature": 0.0,
        }

        routes: list[str | None] = [None] * len(batch)
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"]
                    routes = _parse_batch_response(raw, len(batch))
                    break
                elif resp.status_code == 429:
                    time.sleep(rate_limit * 5)
                else:
                    time.sleep(rate_limit * 2)
            except requests.RequestException:
                time.sleep(rate_limit * 3)

        # Assign results
        for j, entry in enumerate(batch):
            route = routes[j] if routes[j] else entry.get("expected_route", "local")
            classified.append({
                **entry,
                "route": route,
                "source": source_label,
                "weight": weight,
            })

        done = min(i + queries_per_call, total)
        print(f"  Classified {done}/{total} with {source_label}...", end="\r", flush=True)
        time.sleep(rate_limit)

    print()
    return classified


def classify_with_claude_cli(queries: list[dict], weight: float = CLAUDE_WEIGHT) -> list[dict]:
    """Classify queries using the costa-ai CLI (uses Claude plan auth, no API cost).

    Falls back gracefully if costa-ai is unavailable.
    """
    classified: list[dict] = []
    total = len(queries)

    for idx, entry in enumerate(queries):
        query = entry["query"]
        prompt = (
            f"{CLASSIFY_SYSTEM_PROMPT}\n\nQuery: {query}"
        )

        route = None
        try:
            result = subprocess.run(
                ["costa-ai", "--no-context", "--no-escalate", prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )
            raw = result.stdout.strip().lower().rstrip(".,!")
            if raw in ROUTE_CLASSES:
                route = raw
            else:
                for rc in ROUTE_CLASSES:
                    if rc in raw or raw in rc:
                        route = rc
                        break
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        if route is None:
            route = entry.get("expected_route", "local")

        classified.append({
            **entry,
            "route": route,
            "source": "claude",
            "weight": weight,
        })

        time.sleep(CLAUDE_RATE_LIMIT)
        if (idx + 1) % 10 == 0:
            print(f"  Classified {idx + 1}/{total} with claude...", end="\r", flush=True)

    print()
    return classified


def classify_batch_ollama(queries: list[dict]) -> list[dict]:
    """Classify ALL queries with local Ollama (fastest, weight=3.0)."""
    print(f"Classifying {len(queries)} queries with local Ollama...")
    return classify_with_api(
        queries=queries,
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # Ollama doesn't check keys but needs non-empty
        model="qwen3.5:9b",
        rate_limit=0.05,  # Local = no rate limit needed, tiny delay for batching
        weight=3.0,
        source_label="ollama",
        queries_per_call=20,
    )


def classify_batch_gemini(queries: list[dict], env: dict[str, str]) -> list[dict]:
    """Classify ALL queries with Gemini Flash (weight=4.0)."""
    api_key = env.get("GEMINI_API_KEY", "")
    if not api_key:
        print("WARNING: No GEMINI_API_KEY found — skipping Gemini classification.")
        return []

    print(f"Classifying {len(queries)} queries with Gemini ({GEMINI_MODEL})...")
    return classify_with_api(
        queries=queries,
        base_url=GEMINI_BASE_URL,
        api_key=api_key,
        model=GEMINI_MODEL,
        rate_limit=GEMINI_RATE_LIMIT,
        weight=GEMINI_WEIGHT,
        source_label="gemini",
    )


def classify_batch_mistral(queries: list[dict], env: dict[str, str]) -> list[dict]:
    """Classify ALL queries with Devstral (free tier, weight=2.0)."""
    api_key = env.get("MISTRAL_API_KEY", "")
    if not api_key:
        print("WARNING: No MISTRAL_API_KEY found — skipping Mistral classification.")
        return [
            {**q, "route": q.get("expected_route", "local"), "source": "heuristic", "weight": 1.0}
            for q in queries
        ]

    print(f"Classifying {len(queries)} queries with Mistral ({MISTRAL_MODEL})...")
    return classify_with_api(
        queries=queries,
        base_url=MISTRAL_BASE_URL,
        api_key=api_key,
        model=MISTRAL_MODEL,
        rate_limit=MISTRAL_RATE_LIMIT,
        weight=MISTRAL_WEIGHT,
        source_label="mistral",
    )


def classify_batch_claude(
    queries: list[dict],
    env: dict[str, str],
    sample_size: int = CLAUDE_SAMPLE_SIZE,
) -> list[dict]:
    """Classify a stratified subset with Claude Haiku (quality labels, weight=8.0).

    Returns classified records for just the sampled subset.
    """
    # Stratified sampling: pick uniformly from each expected_route bucket
    by_route: dict[str, list[dict]] = {}
    for q in queries:
        route = q.get("expected_route", "local")
        by_route.setdefault(route, []).append(q)

    per_class = sample_size // len(ROUTE_CLASSES)
    sample: list[dict] = []
    for route, bucket in by_route.items():
        n = min(per_class, len(bucket))
        sample.extend(random.sample(bucket, n))

    # Top up to sample_size if we fell short
    remaining = [q for q in queries if q not in sample]
    extra_needed = sample_size - len(sample)
    if extra_needed > 0 and remaining:
        sample.extend(random.sample(remaining, min(extra_needed, len(remaining))))

    print(f"Classifying {len(sample)} queries with Claude (stratified sample)...")

    # Try API key first, fall back to CLI
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return classify_with_api(
            queries=sample,
            base_url="https://api.anthropic.com/v1",
            api_key=api_key,
            model=CLAUDE_HAIKU_MODEL,
            rate_limit=CLAUDE_RATE_LIMIT,
            weight=CLAUDE_WEIGHT,
            source_label="claude",
        )
    else:
        print("  No ANTHROPIC_API_KEY — using costa-ai CLI (plan auth)...")
        return classify_with_claude_cli(sample, weight=CLAUDE_WEIGHT)


# ---------------------------------------------------------------------------
# 4. Extract AST features and save
# ---------------------------------------------------------------------------

def extract_and_save(classified: list[dict]) -> list[dict]:
    """For each query+file_path, compute AST features and save to output file.

    Returns the final list of labeled records.
    """
    try:
        import ast_parser
    except ImportError:
        ast_parser = None  # type: ignore

    records: list[dict] = []
    total = len(classified)

    for idx, entry in enumerate(classified):
        file_path = entry.get("file_path")
        query = entry["query"]

        if file_path and ast_parser is not None:
            ast_features = compute_ast_features(file_path)
            # Patch feature [25]: query_symbol_match
            try:
                summary = ast_parser.get_file_summary(file_path)
                ast_features[25] = compute_query_symbol_match(query, summary)
            except Exception:
                pass
        else:
            ast_features = [0.0] * N_AST_FEATURES

        records.append({
            "query": query,
            "route": entry["route"],
            "file_path": file_path,
            "ast_features": ast_features,
            "source": entry.get("source", "heuristic"),
            "weight": entry.get("weight", 1.0),
        })

        if (idx + 1) % 100 == 0:
            print(f"  Extracted features {idx + 1}/{total}...", end="\r", flush=True)

    print()

    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(records, f, indent=2)

    print(f"Saved {len(records)} labeled records to {OUTPUT_FILE}")
    return records


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def print_stats(records: list[dict]):
    """Print distribution of routes and sources."""
    route_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    for r in records:
        route = r.get("route", "unknown")
        source = r.get("source", "unknown")
        route_counts[route] = route_counts.get(route, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    print("\n--- Route Distribution ---")
    total = len(records)
    for route in ROUTE_CLASSES:
        count = route_counts.get(route, 0)
        pct = 100 * count / total if total else 0
        print(f"  {route:<25} {count:>5}  ({pct:.1f}%)")

    print("\n--- Source Distribution ---")
    for src, count in sorted(source_counts.items()):
        pct = 100 * count / total if total else 0
        print(f"  {src:<20} {count:>5}  ({pct:.1f}%)")

    print(f"\nTotal: {total} records")
    has_ast = sum(1 for r in records if any(v != 0.0 for v in r.get("ast_features", [])))
    print(f"With non-zero AST features: {has_ast} ({100*has_ast/total:.1f}%)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate training data for the two-stage AST router",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="Only scan files and save inventory (skip query generation and classification)",
    )
    parser.add_argument(
        "--classify-only",
        action="store_true",
        help="Skip inventory scan; reuse existing inventory.json and queries.json",
    )
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Skip Claude classification (Mistral only)",
    )
    parser.add_argument(
        "--no-mistral",
        action="store_true",
        help="Skip Mistral classification (Claude only)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=CLAUDE_SAMPLE_SIZE,
        help=f"Number of queries for Claude to classify (default: {CLAUDE_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=MAX_FILES,
        help=f"Maximum files to inventory (default: {MAX_FILES})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)

    env = load_env()

    # ── Step 1: Inventory ────────────────────────────────────────────────────
    if args.classify_only and INVENTORY_FILE.exists():
        print(f"Loading existing inventory from {INVENTORY_FILE}...")
        with open(INVENTORY_FILE) as f:
            inventory = json.load(f)
        print(f"Loaded {len(inventory)} files from inventory")
    elif not args.classify_only:
        print(f"Scanning {PROJECTS_DIR} for source files (max {args.max_files})...")
        inventory = inventory_files(PROJECTS_DIR, max_files=args.max_files)
        print(f"Inventoried {len(inventory)} files")
        with open(INVENTORY_FILE, "w") as f:
            json.dump(inventory, f, indent=2)
        print(f"Saved inventory to {INVENTORY_FILE}")
    else:
        print(f"ERROR: --classify-only requires existing {INVENTORY_FILE}")
        sys.exit(1)

    if args.inventory_only:
        print("Done (inventory only).")
        return

    # ── Step 2: Generate queries ─────────────────────────────────────────────
    if args.classify_only and QUERIES_FILE.exists():
        print(f"Loading existing queries from {QUERIES_FILE}...")
        with open(QUERIES_FILE) as f:
            queries = json.load(f)
        print(f"Loaded {len(queries)} queries")
    else:
        queries = generate_queries(inventory)
        with open(QUERIES_FILE, "w") as f:
            json.dump(queries, f, indent=2)
        print(f"Saved queries to {QUERIES_FILE}")

    # ── Step 3: Classify with ALL four models in parallel ───────────────────
    import concurrent.futures

    all_classified: list[dict] = []
    futures = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        # Ollama (local, fast, weight 3.0)
        futures["ollama"] = pool.submit(classify_batch_ollama, queries)

        # Gemini (strong reasoning, weight 4.0)
        futures["gemini"] = pool.submit(classify_batch_gemini, queries, env)

        # Mistral (free cloud, weight 2.0)
        if not args.no_mistral:
            futures["mistral"] = pool.submit(classify_batch_mistral, queries, env)

        # Claude (quality subset, weight 8.0)
        if not args.no_claude:
            futures["claude"] = pool.submit(classify_batch_claude, queries, env, args.sample_size)

        for name, fut in futures.items():
            try:
                result = fut.result(timeout=7200)  # 2 hour max per classifier
                all_classified.extend(result)
                print(f"  {name}: {len(result)} records")
            except Exception as e:
                print(f"  {name}: FAILED — {e}")

    print(f"\nTotal classified records: {len(all_classified)}")

    # ── Step 4: Extract AST features + save ──────────────────────────────────
    print("Extracting AST features...")
    records = extract_and_save(all_classified)

    # ── Stats ─────────────────────────────────────────────────────────────────
    print_stats(records)
    print(f"\nDone. Training data at: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
