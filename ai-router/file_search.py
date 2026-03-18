"""Costa OS Natural Language File Search.

"Find that rust file I was editing yesterday with the websocket code"

Combines content search, name search, time filtering, git history,
and frecency scoring to find files from natural language queries.
"""

import json
import math
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

FRECENCY_PATH = Path.home() / ".config" / "costa" / "file_frecency.json"
HOME = str(Path.home())

# File type keywords -> glob patterns
FILE_TYPE_MAP = {
    "rust": "*.rs",
    "python": "*.py",
    "javascript": "*.js",
    "typescript": "*.ts",
    "tsx": "*.tsx",
    "jsx": "*.jsx",
    "java": "*.java",
    "go": "*.go",
    "c file": "*.c",
    "c++ file": "*.cpp",
    "header": "*.h",
    "css": "*.css",
    "scss": "*.scss",
    "html": "*.html",
    "json": "*.json",
    "yaml": "*.yaml",
    "yml": "*.yml",
    "toml": "*.toml",
    "markdown": "*.md",
    "shell": "*.sh",
    "bash": "*.sh",
    "zsh": "*.zsh",
    "config": "*.conf",
    "dockerfile": "Dockerfile*",
    "docker": "Dockerfile*",
    "makefile": "Makefile*",
    "lua": "*.lua",
    "ruby": "*.rb",
    "kotlin": "*.kt",
    "swift": "*.swift",
    "sql": "*.sql",
    "xml": "*.xml",
    "svg": "*.svg",
    "php": "*.php",
}

# Words for "file type" that map to extensions directly
EXTENSION_WORDS = {
    "rust": ".rs", "rs": ".rs",
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "tsx": ".tsx", "jsx": ".jsx",
    "java": ".java",
    "go": ".go",
    "c": ".c", "cpp": ".cpp", "c++": ".cpp",
    "css": ".css", "scss": ".scss",
    "html": ".html",
    "json": ".json",
    "yaml": ".yaml", "yml": ".yml",
    "toml": ".toml",
    "md": ".md", "markdown": ".md",
    "sh": ".sh", "shell": ".sh", "bash": ".sh", "zsh": ".zsh",
    "lua": ".lua", "ruby": ".rb", "rb": ".rb",
    "kotlin": ".kt", "kt": ".kt",
    "sql": ".sql", "xml": ".xml", "php": ".php",
    "config": ".conf", "conf": ".conf",
}

# Time references -> timedelta
TIME_REFERENCES = {
    "today": timedelta(days=1),
    "yesterday": timedelta(days=2),
    "last hour": timedelta(hours=1),
    "this morning": timedelta(hours=12),
    "this afternoon": timedelta(hours=8),
    "last week": timedelta(weeks=1),
    "this week": timedelta(weeks=1),
    "last month": timedelta(days=30),
    "this month": timedelta(days=30),
    "recently": timedelta(days=3),
    "few days ago": timedelta(days=5),
    "couple days ago": timedelta(days=3),
}

# Stop words to filter out when extracting content keywords
STOP_WORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "is", "was", "are", "were", "be", "been", "being",
    "that", "this", "those", "these", "it", "its",
    "i", "me", "my", "we", "our", "you", "your",
    "find", "search", "look", "looking", "where", "which", "what",
    "file", "files", "code", "script", "module", "class", "function",
    "editing", "edited", "working", "wrote", "writing", "wrote",
    "about", "had", "has", "have", "just", "some", "there",
    "and", "or", "but", "not", "no", "so",
}

# Location hint patterns
LOCATION_PATTERNS = [
    (r"in\s+([\w/-]+)", None),
    (r"(?:inside|under|within)\s+([\w/-]+)", None),
    (r"(?:project|repo)\s+([\w-]+)", "~/projects/{match}"),
]


def _run(cmd: str | list[str], timeout: int = 10) -> str:
    """Run a command, return stdout.

    Accepts list (no shell) or string (shell=True for pipes). Prefer list form.
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
    except Exception:
        return ""


def load_frecency() -> dict:
    """Load the frecency database."""
    try:
        return json.loads(FRECENCY_PATH.read_text())
    except Exception:
        return {}


def save_frecency(data: dict):
    """Persist frecency data."""
    FRECENCY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        FRECENCY_PATH.write_text(json.dumps(data))
    except Exception:
        pass


def record_file_open(filepath: str):
    """Record that a file was opened (for frecency tracking)."""
    data = load_frecency()
    filepath = str(Path(filepath).resolve())
    entry = data.get(filepath, {"count": 0, "last": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["last"] = int(time.time())
    data[filepath] = entry
    # Prune old entries (> 90 days since last access)
    cutoff = int(time.time()) - 90 * 86400
    data = {k: v for k, v in data.items() if v.get("last", 0) > cutoff}
    save_frecency(data)


def parse_query(query: str) -> dict:
    """Parse a natural language file search query into structured components.

    Returns:
        dict with keys: file_type, time_delta, keywords, location, extensions
    """
    q = query.lower().strip()
    result = {
        "file_type": None,       # glob pattern like *.rs
        "extension": None,       # extension like .rs
        "time_delta": None,      # timedelta for mtime filtering
        "keywords": [],          # content search keywords
        "location": None,        # directory hint
    }

    # Extract file type
    for type_word, glob_pattern in FILE_TYPE_MAP.items():
        # Match "rust file", "python script", "typescript module", etc.
        if re.search(rf"\b{re.escape(type_word)}\b", q):
            result["file_type"] = glob_pattern
            result["extension"] = EXTENSION_WORDS.get(type_word)
            q = re.sub(rf"\b{re.escape(type_word)}\b\s*(file|script|module|code|source)?", "", q)
            break

    # Check for explicit extension mentions like ".rs file" or "*.py"
    ext_match = re.search(r"\.(\w+)\b", q)
    if ext_match and not result["file_type"]:
        ext = ext_match.group(1)
        if ext in EXTENSION_WORDS.values() or f".{ext}" in EXTENSION_WORDS.values():
            result["extension"] = f".{ext}" if not ext.startswith(".") else ext
            result["file_type"] = f"*{result['extension']}"

    # Extract time references
    for phrase, delta in TIME_REFERENCES.items():
        if phrase in q:
            result["time_delta"] = delta
            q = q.replace(phrase, "")
            break

    # Extract location hints
    for pattern, template in LOCATION_PATTERNS:
        m = re.search(pattern, q)
        if m:
            match = m.group(1)
            if template:
                loc = template.format(match=match)
            else:
                loc = match
            # Expand ~ and resolve common project paths
            if not loc.startswith("/") and not loc.startswith("~"):
                # Check if it's a known project
                proj_path = Path.home() / "projects" / loc
                if proj_path.exists():
                    loc = str(proj_path)
                elif (Path.home() / loc).exists():
                    loc = str(Path.home() / loc)
                elif (Path.home() / ".config" / loc).exists():
                    loc = str(Path.home() / ".config" / loc)
            else:
                loc = str(Path(loc).expanduser())
            result["location"] = loc
            q = q[:m.start()] + q[m.end():]
            break

    # Extract content keywords (remaining meaningful words)
    words = re.findall(r"\b[a-z_]\w{2,}\b", q)
    result["keywords"] = [w for w in words if w not in STOP_WORDS]

    return result


def search_by_content(keywords: list[str], location: str | None = None,
                      file_glob: str | None = None, max_results: int = 30) -> list[dict]:
    """Search file contents using ripgrep."""
    if not keywords:
        return []

    search_dir = location or HOME
    results = []

    for keyword in keywords:
        cmd_parts = ["rg", "-l", "--max-count=1", "--no-messages",
                     "--max-depth=8", "-i"]
        if file_glob:
            cmd_parts.extend(["-g", file_glob])
        # Exclude common noise directories
        cmd_parts.extend([
            "-g", "!node_modules", "-g", "!.git", "-g", "!__pycache__",
            "-g", "!target", "-g", "!dist", "-g", "!build",
            "-g", "!.cache", "-g", "!*.min.js", "-g", "!*.map",
        ])
        cmd_parts.append(keyword)
        cmd_parts.append(search_dir)

        # Use list form directly — no shell needed
        output = _run(cmd_parts)
        if output:
            for filepath in output.strip().split("\n")[:max_results]:
                filepath = filepath.strip()
                if filepath:
                    results.append({
                        "path": filepath,
                        "match_type": "content",
                        "keyword": keyword,
                    })

    return results


def search_by_name(keywords: list[str], location: str | None = None,
                   file_glob: str | None = None, max_results: int = 20) -> list[dict]:
    """Search file names using fd."""
    results = []
    search_dir = location or HOME

    # Search with file type glob
    if file_glob:
        cmd = ["fd", "-t", "f", "-g", file_glob, "--max-depth", "8", search_dir]
        output = _run(cmd)
        if output:
            for filepath in output.strip().split("\n")[:max_results]:
                filepath = filepath.strip()
                if filepath:
                    results.append({"path": filepath, "match_type": "name_glob"})

    # Search with keywords in filename
    for keyword in keywords:
        cmd = ["fd", "-t", "f", "-i", keyword, "--max-depth", "8", search_dir]
        output = _run(cmd)
        if output:
            for filepath in output.strip().split("\n")[:max_results]:
                filepath = filepath.strip()
                if filepath:
                    results.append({
                        "path": filepath,
                        "match_type": "name",
                        "keyword": keyword,
                    })

    return results


def search_by_time(time_delta: timedelta, location: str | None = None,
                   file_glob: str | None = None, max_results: int = 30) -> list[dict]:
    """Find files modified within the given time window."""
    search_dir = location or HOME
    minutes = int(time_delta.total_seconds() / 60)

    cmd_parts = ["find", search_dir, "-maxdepth", "8", "-type", "f",
                 "-mmin", f"-{minutes}"]
    if file_glob:
        cmd_parts.extend(["-name", file_glob])

    # Exclude noise
    cmd_parts.extend([
        "-not", "-path", "*/.git/*",
        "-not", "-path", "*/node_modules/*",
        "-not", "-path", "*/__pycache__/*",
        "-not", "-path", "*/target/*",
        "-not", "-path", "*/.cache/*",
    ])

    # Use list form (no shell) — handle max_results in Python
    output = _run(cmd_parts)
    results = []
    if output:
        for filepath in output.strip().split("\n")[:max_results]:
            filepath = filepath.strip()
            if filepath:
                results.append({"path": filepath, "match_type": "time"})

    return results


def search_by_git(time_delta: timedelta | None = None,
                  location: str | None = None,
                  max_results: int = 20) -> list[dict]:
    """Find recently modified files via git log."""
    search_dir = location or HOME

    # Find git repos to search in
    if location:
        repos = [location]
    else:
        # Search common project directories
        repos_output = _run(
            ["find", f"{HOME}/projects", "-maxdepth", "2", "-name", ".git", "-type", "d"]
        )
        repos = []
        if repos_output:
            repos = [str(Path(r).parent) for r in repos_output.strip().split("\n")[:20] if r.strip()]
        # Also check home dir
        if Path(HOME, ".git").exists():
            repos.append(HOME)

    results = []

    for repo in repos:
        cmd = ["git", "-C", repo, "log", "--diff-filter=M",
               "--name-only", "--pretty=format:", "-n", "50"]
        if time_delta:
            days = max(1, int(time_delta.total_seconds() / 86400))
            cmd.append(f"--since={days} days ago")
        output = _run(cmd)
        if output:
            seen = set()
            for relpath in output.strip().split("\n"):
                relpath = relpath.strip()
                if relpath and relpath not in seen:
                    seen.add(relpath)
                    fullpath = str(Path(repo) / relpath)
                    if Path(fullpath).exists():
                        results.append({
                            "path": fullpath,
                            "match_type": "git",
                        })
                    if len(results) >= max_results:
                        break

    return results


def score_results(raw_results: list[dict], parsed: dict) -> list[dict]:
    """Combine and score results from all search strategies.

    Scoring:
        Content match: +10 per matching keyword
        Name match: +15
        Time match: +8
        Git recent: +12
        Frecency bonus: +5 * log(open_count + 1)
    """
    frecency = load_frecency()
    keywords = set(parsed.get("keywords", []))
    extension = parsed.get("extension")

    # Aggregate scores by filepath
    file_scores: dict[str, dict] = {}

    for entry in raw_results:
        path = entry["path"]
        if path not in file_scores:
            file_scores[path] = {"path": path, "score": 0, "match_types": set()}

        match_type = entry.get("match_type", "")
        file_scores[path]["match_types"].add(match_type)

        if match_type == "content":
            file_scores[path]["score"] += 10
        elif match_type in ("name", "name_glob"):
            file_scores[path]["score"] += 15
        elif match_type == "config_dir":
            file_scores[path]["score"] += 25  # direct config directory hit
        elif match_type == "time":
            file_scores[path]["score"] += 8
        elif match_type == "git":
            file_scores[path]["score"] += 12

    # Apply frecency bonus and extension bonus
    for path, info in file_scores.items():
        # Frecency
        if path in frecency:
            count = frecency[path].get("count", 0)
            if count > 0:
                info["score"] += 5 * math.log(count + 1)

            # Recency bonus (opened in last 24h)
            last = frecency[path].get("last", 0)
            if time.time() - last < 86400:
                info["score"] += 5

        # Extension match bonus
        if extension and path.endswith(extension):
            info["score"] += 5

        # Keyword in filename bonus
        basename = Path(path).name.lower()
        for kw in keywords:
            if kw in basename:
                info["score"] += 8

        # Keyword in full path bonus (catches ~/.config/pipewire/ etc)
        path_lower = path.lower()
        for kw in keywords:
            if kw != "config" and kw != "file" and kw in path_lower:
                info["score"] += 12

        # Penalize deep paths slightly
        depth = path.count("/")
        if depth > 8:
            info["score"] -= (depth - 8) * 0.5

        # Penalize Downloads — rarely the right answer for config searches
        if "/Downloads/" in path:
            info["score"] -= 20

        # Bonus for config directories — usually what users are looking for
        if "/.config/" in path or "/etc/" in path:
            info["score"] += 10
        if "/projects/costa-os/" in path:
            info["score"] += 5

    # Convert match_types from set to list for JSON serialization
    scored = []
    for info in file_scores.values():
        info["match_types"] = list(info["match_types"])
        info["score"] = round(info["score"], 2)
        scored.append(info)

    # Sort by score descending
    scored.sort(key=lambda x: -x["score"])
    return scored[:10]


def search_files(query: str) -> list[dict]:
    """Search for files using natural language.

    Args:
        query: Natural language query like "rust file with websocket code from yesterday"

    Returns:
        List of dicts with keys: path, score, match_types
        Sorted by relevance score descending, top 10.
    """
    parsed = parse_query(query)
    all_results = []

    # 1. Content search
    if parsed["keywords"]:
        all_results.extend(
            search_by_content(parsed["keywords"], parsed["location"], parsed["file_type"])
        )

    # 2. Name search
    all_results.extend(
        search_by_name(parsed["keywords"], parsed["location"], parsed["file_type"])
    )

    # 3. Time search
    if parsed["time_delta"]:
        all_results.extend(
            search_by_time(parsed["time_delta"], parsed["location"], parsed["file_type"])
        )

    # 4. Git search
    all_results.extend(
        search_by_git(parsed["time_delta"], parsed["location"])
    )

    # 5. Config directory search — check ~/.config/<keyword>/ directly
    config_dir = Path.home() / ".config"
    for kw in parsed["keywords"]:
        if kw in ("config", "file", "the", "my", "where", "is", "find"):
            continue
        kw_dir = config_dir / kw
        if kw_dir.is_dir():
            # Found a matching config directory — add all files in it
            try:
                for f in kw_dir.rglob("*"):
                    if f.is_file():
                        all_results.append({
                            "path": str(f),
                            "match_type": "config_dir",
                        })
            except PermissionError:
                pass
        # Also check /etc/<keyword>/
        etc_dir = Path("/etc") / kw
        if etc_dir.is_dir():
            try:
                for f in etc_dir.rglob("*"):
                    if f.is_file() and f.stat().st_size < 1_000_000:
                        all_results.append({
                            "path": str(f),
                            "match_type": "config_dir",
                        })
            except PermissionError:
                pass

    # Score and rank
    return score_results(all_results, parsed)


def format_results(results: list[dict]) -> str:
    """Format results for display."""
    if not results:
        return "No matching files found."

    lines = []
    for i, r in enumerate(results, 1):
        path = r["path"]
        # Shorten home dir
        if path.startswith(HOME):
            path = "~" + path[len(HOME):]
        score = r["score"]
        types = ", ".join(r["match_types"])
        lines.append(f"{i:2d}. {path}  ({types}, score: {score})")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: file_search.py <natural language query>")
        print('Example: file_search.py "rust file with websocket code from yesterday"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    results = search_files(query)
    print(format_results(results))
