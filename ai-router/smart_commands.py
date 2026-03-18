"""Costa OS Smart Command Suggestions.

Watches zsh history and suggests next commands based on learned patterns.
Analyzes command bigrams, per-directory frequencies, and common workflows
to predict what the user likely wants to run next.
"""

import json
import os
import re
import subprocess
import math
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PATTERN_DB_PATH = Path.home() / ".config" / "costa" / "command_patterns.json"
MAX_HISTORY_LINES = 5000
BUILTIN_SEQUENCES = {
    # command A -> likely command B (with base confidence)
    "git add": [("git commit -m \"\"", 0.85)],
    "git add .": [("git commit -m \"\"", 0.90)],
    "git add -A": [("git commit -m \"\"", 0.90)],
    "git commit": [("git push", 0.70)],
    "git pull": [("git status", 0.50)],
    "git clone": [("cd", 0.60)],
    "git stash": [("git pull", 0.55), ("git checkout", 0.45)],
    "cargo build": [("cargo run", 0.60), ("cargo test", 0.50)],
    "cargo test": [("cargo build", 0.40), ("cargo run", 0.35)],
    "npm install": [("npm run dev", 0.55), ("npm start", 0.50)],
    "npm run build": [("npm start", 0.50), ("npm run dev", 0.45)],
    "npm test": [("npm run build", 0.45)],
    "pip install": [("python", 0.40)],
    "make": [("make install", 0.45), ("./", 0.35)],
    "mkdir": [("cd", 0.70)],
    "cd": [("ls", 0.60)],
    "docker build": [("docker run", 0.70)],
    "docker compose up": [("docker compose logs", 0.50), ("docker compose down", 0.40)],
    "docker compose down": [("docker compose up", 0.55)],
    "pytest": [("git add", 0.40)],
    "python -m pytest": [("git add", 0.40)],
    "pacman -Syu": [("yay -Syu", 0.35)],
    "systemctl restart": [("systemctl status", 0.60)],
    "systemctl start": [("systemctl status", 0.60)],
    "systemctl stop": [("systemctl status", 0.50)],
}

# File extension -> likely build/run commands
EXTENSION_COMMANDS = {
    ".rs": ["cargo build", "cargo run", "cargo test", "cargo check"],
    ".py": ["python {file}", "pytest", "python -m pytest"],
    ".ts": ["npm run build", "npm run dev", "npx tsc"],
    ".tsx": ["npm run build", "npm run dev", "npm start"],
    ".js": ["node {file}", "npm run build", "npm start"],
    ".jsx": ["npm run build", "npm run dev", "npm start"],
    ".java": ["mvn compile", "gradle build", "./gradlew build"],
    ".go": ["go build", "go run .", "go test ./..."],
    ".c": ["make", "gcc {file} -o {stem}"],
    ".cpp": ["make", "g++ {file} -o {stem}"],
    ".toml": ["cargo build"],
    ".lock": [],
}

# Common corrections for failed commands
FAIL_CORRECTIONS = [
    # (pattern in failed cmd, suggestion)
    (r"^cd\s+(\S+)", "mkdir -p {match} && cd {match}"),
    (r"^git push$", "git push --set-upstream origin $(git branch --show-current)"),
    (r"^python\s+", "python3 {rest}"),
    (r"^pip\s+", "pip3 {rest}"),
    (r"command not found.*?(\S+)", "yay -S {match}"),
    (r"permission denied", "sudo !!"),
    (r"^npm\s+", "npm install && {cmd}"),
]


def load_pattern_db() -> dict:
    """Load the learned pattern database."""
    try:
        return json.loads(PATTERN_DB_PATH.read_text())
    except Exception:
        return {"bigrams": {}, "dir_commands": {}, "version": 1}


def save_pattern_db(db: dict):
    """Persist the pattern database."""
    PATTERN_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        PATTERN_DB_PATH.write_text(json.dumps(db, indent=2))
    except Exception:
        pass


def parse_zsh_history(max_lines: int = MAX_HISTORY_LINES) -> list[dict]:
    """Parse zsh extended history format.

    Lines look like: : 1710000000:0;command here
    or plain: command here
    """
    histfile = os.environ.get("HISTFILE", str(Path.home() / ".zsh_history"))
    entries = []
    try:
        with open(histfile, "r", errors="replace") as f:
            lines = f.readlines()
        for line in lines[-max_lines:]:
            line = line.strip()
            if not line:
                continue
            # Extended history format
            m = re.match(r"^:\s*(\d+):\d+;(.+)$", line)
            if m:
                entries.append({
                    "timestamp": int(m.group(1)),
                    "command": m.group(2).strip(),
                })
            else:
                # Plain format
                entries.append({
                    "timestamp": 0,
                    "command": line,
                })
    except Exception:
        pass
    return entries


def build_bigrams(history: list[dict]) -> dict[str, dict[str, int]]:
    """Build a frequency table of command bigrams from history.

    Keys are normalized command prefixes, values are dicts of
    {next_command_prefix: count}.
    """
    bigrams: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in range(len(history) - 1):
        cmd_a = _normalize_command(history[i]["command"])
        cmd_b = _normalize_command(history[i + 1]["command"])
        if cmd_a and cmd_b and cmd_a != cmd_b:
            bigrams[cmd_a][cmd_b] += 1
    return {k: dict(v) for k, v in bigrams.items()}


def _normalize_command(cmd: str) -> str:
    """Normalize a command to its prefix for pattern matching.

    'git commit -m "fix: foo"' -> 'git commit'
    'cd ~/projects/my-app' -> 'cd'
    'vim src/main.rs' -> 'vim'
    """
    cmd = cmd.strip()
    if not cmd or cmd.startswith("#"):
        return ""

    parts = cmd.split()
    if not parts:
        return ""

    base = parts[0]

    # For git/docker/systemctl, include the subcommand
    if base in ("git", "docker", "systemctl", "cargo", "npm", "npx",
                "kubectl", "pip", "pip3", "python", "python3", "go",
                "make", "gradle", "mvn", "pacman", "yay", "sudo"):
        if len(parts) > 1:
            return f"{base} {parts[1]}"
    return base


def _full_normalize(cmd: str) -> str:
    """Return the full command for exact matching in suggestions."""
    return cmd.strip().split("|")[0].strip()


def update_pattern_db(db: dict, history: list[dict], cwd: str):
    """Update the pattern database with new observations."""
    # Update bigrams
    new_bigrams = build_bigrams(history[-100:])  # last 100 commands
    stored = db.get("bigrams", {})
    for cmd_a, nexts in new_bigrams.items():
        if cmd_a not in stored:
            stored[cmd_a] = {}
        for cmd_b, count in nexts.items():
            stored[cmd_a][cmd_b] = stored[cmd_a].get(cmd_b, 0) + count
    db["bigrams"] = stored

    # Update per-directory command frequencies
    dir_cmds = db.get("dir_commands", {})
    if cwd not in dir_cmds:
        dir_cmds[cwd] = {}
    if history:
        last_cmd = _normalize_command(history[-1]["command"])
        if last_cmd:
            dir_cmds[cwd][last_cmd] = dir_cmds[cwd].get(last_cmd, 0) + 1
    db["dir_commands"] = dir_cmds
    db["version"] = 1


def detect_edited_file(last_commands: list[str]) -> str | None:
    """Check if the user just edited a file, return extension if so."""
    editors = ("vim", "nvim", "nano", "vi", "code", "hx", "helix", "emacs", "kate")
    for cmd in reversed(last_commands):
        parts = cmd.strip().split()
        if len(parts) >= 2 and parts[0] in editors:
            filepath = parts[-1]
            ext = Path(filepath).suffix
            if ext:
                return ext
    return None


def get_fail_suggestions(last_command: str, exit_code: int) -> list[tuple[str, float]]:
    """Suggest corrections for a failed command."""
    if exit_code == 0:
        return []

    suggestions = []
    for pattern, template in FAIL_CORRECTIONS:
        m = re.search(pattern, last_command, re.IGNORECASE)
        if m:
            try:
                suggestion = template.format(
                    match=m.group(1) if m.lastindex else "",
                    rest=" ".join(last_command.split()[1:]),
                    cmd=last_command,
                )
                suggestions.append((suggestion, 0.75))
            except (IndexError, KeyError):
                pass

    # Generic: suggest running with sudo if permission error likely
    if exit_code == 1 and not last_command.startswith("sudo"):
        suggestions.append((f"sudo {last_command}", 0.30))

    return suggestions[:3]


def get_suggestions(
    cwd: str,
    last_commands: list[str],
    last_exit_code: int = 0,
) -> list[tuple[str, float]]:
    """Get command suggestions based on context.

    Args:
        cwd: Current working directory.
        last_commands: Recent commands (most recent last), typically 1-5.
        last_exit_code: Exit code of the most recent command.

    Returns:
        List of (suggestion, confidence) tuples, sorted by confidence descending.
        Confidence is a float 0.0-1.0. Returns top 3.
    """
    if not last_commands:
        return []

    candidates: dict[str, float] = {}  # suggestion -> confidence

    last_cmd = last_commands[-1].strip()
    last_norm = _normalize_command(last_cmd)
    db = load_pattern_db()

    # 1. Check for failed command corrections
    if last_exit_code != 0:
        for suggestion, conf in get_fail_suggestions(last_cmd, last_exit_code):
            candidates[suggestion] = max(candidates.get(suggestion, 0), conf)

    # 2. Built-in sequences
    for prefix, suggestions in BUILTIN_SEQUENCES.items():
        if last_cmd.startswith(prefix) or last_norm == _normalize_command(prefix):
            for suggestion, conf in suggestions:
                candidates[suggestion] = max(candidates.get(suggestion, 0), conf)

    # 3. Learned bigrams from history
    bigrams = db.get("bigrams", {})
    if last_norm in bigrams:
        nexts = bigrams[last_norm]
        total = sum(nexts.values())
        for next_cmd, count in sorted(nexts.items(), key=lambda x: -x[1])[:5]:
            freq = count / total
            conf = min(0.95, 0.3 + freq * 0.6)
            candidates[next_cmd] = max(candidates.get(next_cmd, 0), conf)

    # 4. File-type-based suggestions (user just edited a file)
    ext = detect_edited_file(last_commands)
    if ext and ext in EXTENSION_COMMANDS:
        for cmd_template in EXTENSION_COMMANDS[ext]:
            cmd = cmd_template.split("{")[0].strip()  # drop {file} placeholders
            if cmd:
                candidates[cmd] = max(candidates.get(cmd, 0), 0.45)

    # 5. Per-directory command frequency bonus
    dir_cmds = db.get("dir_commands", {})
    if cwd in dir_cmds:
        dir_total = sum(dir_cmds[cwd].values())
        for cmd, count in sorted(dir_cmds[cwd].items(), key=lambda x: -x[1])[:5]:
            freq = count / dir_total
            bonus = freq * 0.25
            if cmd in candidates:
                candidates[cmd] = min(0.95, candidates[cmd] + bonus)
            elif freq > 0.15:  # only add dir-frequent cmds if they're actually common
                candidates[cmd] = 0.20 + bonus

    # 6. Update the pattern DB with this observation
    history = parse_zsh_history(200)
    update_pattern_db(db, history, cwd)
    save_pattern_db(db)

    # Remove the command we just ran from suggestions
    candidates.pop(last_norm, None)
    candidates.pop(last_cmd, None)

    # Sort by confidence and return top 3
    sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])
    return sorted_candidates[:3]


def format_suggestion(suggestions: list[tuple[str, float]]) -> str:
    """Format suggestions for display."""
    if not suggestions:
        return ""
    # Return just the top suggestion for RPROMPT
    return suggestions[0][0]


if __name__ == "__main__":
    import sys

    cwd = os.getcwd()
    last_cmds = sys.argv[1:] if len(sys.argv) > 1 else []
    exit_code = int(os.environ.get("COSTA_LAST_EXIT", "0"))

    if not last_cmds:
        # Read from history
        history = parse_zsh_history(10)
        last_cmds = [e["command"] for e in history[-3:]]

    suggestions = get_suggestions(cwd, last_cmds, exit_code)
    if suggestions:
        # Output format: suggestion\tconfidence
        for suggestion, conf in suggestions:
            print(f"{suggestion}\t{conf:.2f}")
    else:
        print("")
