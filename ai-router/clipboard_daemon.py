#!/usr/bin/env python3
"""Costa OS Clipboard Intelligence Daemon.

Watches the Wayland clipboard via `wl-paste --watch` and offers smart actions
through dunst notifications based on content type detection.

Launch: python3 clipboard_daemon.py
Kill:   pkill -f clipboard_daemon.py
"""

import subprocess
import sys
import os
import re
import json
import time
import signal
import threading
from pathlib import Path

# Path to the click handler script
SCRIPT_DIR = Path(__file__).parent.resolve()
ACTION_SCRIPT = SCRIPT_DIR / "clipboard_action.sh"

# Debounce: ignore clipboard changes within this window (seconds)
DEBOUNCE_SECONDS = 0.5

# Minimum content length to analyze
MIN_LENGTH = 3

# Track state
_last_content = ""
_last_time = 0.0
_lock = threading.Lock()


def notify(title: str, body: str, action_type: str, content: str,
           urgency: str = "normal", timeout: int = 8000):
    """Send a dunst notification with a click action."""
    # Truncate body for display
    display_body = body[:200] + "..." if len(body) > 200 else body

    # Write content to a temp file for the action script (avoids shell escaping issues)
    content_file = f"/tmp/costa-clipboard-content-{os.getpid()}"
    try:
        Path(content_file).write_text(content)
    except Exception:
        return

    # Build notify-send with action
    cmd = [
        "notify-send",
        "--app-name=Costa Clipboard",
        f"--urgency={urgency}",
        f"--expire-time={timeout}",
        "--action=default=Open",
        title,
        display_body,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=12,
        )
        # If the user clicked the action (notify-send returns "default" on stdout)
        if result.stdout.strip() == "default":
            subprocess.Popen(
                ["bash", str(ACTION_SCRIPT), action_type, content_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


def classify_content(content: str) -> tuple[str, str, str] | None:
    """Classify clipboard content and return (action_type, title, body) or None.

    Returns None if content doesn't match any known pattern.
    """
    stripped = content.strip()

    # --- Error / stack trace ---
    error_patterns = [
        r"(?:Error|Exception|Traceback|FAILED|FATAL|panic)[\s:]",
        r"at line \d+",
        r"File \".*\", line \d+",
        r"^\s+at \S+\(.+:\d+:\d+\)",  # JS stack trace
        r"Caused by:",
        r"(?:java|python|node|rust).*(?:Error|Exception|Panic)",
    ]
    if any(re.search(p, stripped, re.MULTILINE | re.IGNORECASE) for p in error_patterns):
        first_line = stripped.split("\n")[0][:80]
        return ("error", "Error detected — click to explain", first_line)

    # --- URL ---
    if re.match(r"https?://\S+$", stripped):
        # Single URL on clipboard
        domain = re.sub(r"https?://([^/]+).*", r"\1", stripped)
        return ("url", "URL copied — click to open", domain)

    # --- JSON ---
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            size = len(stripped)
            return ("json", "JSON copied — click to format", f"{size} characters")
        except (json.JSONDecodeError, ValueError):
            pass

    # --- File path ---
    if re.match(r"^(~|/)[^\s]*$", stripped):
        expanded = os.path.expanduser(stripped)
        if os.path.exists(expanded):
            return ("path", "Path copied — click to open", stripped)

    # --- Shell command ---
    shell_prefixes = (
        "sudo ", "git ", "docker ", "docker-compose ", "npm ", "pip ", "pip3 ",
        "cargo ", "systemctl ", "journalctl ", "pacman ", "yay ", "curl ",
        "wget ", "ssh ", "scp ", "rsync ", "make ", "cmake ", "go ",
        "python ", "python3 ", "node ", "deno ", "bun ", "pnpm ",
        "kubectl ", "helm ", "terraform ", "ansible ",
    )
    first_line = stripped.split("\n")[0].strip()
    if first_line.startswith(shell_prefixes):
        return ("command", "Command copied — click to run in terminal", first_line[:80])

    # --- Code snippet ---
    code_indicators = [
        r"^\s*(def |class |function |const |let |var |import |from |export |pub fn |fn |impl |struct |enum |interface |type )",
        r"^\s*(if\s*\(|for\s*\(|while\s*\(|switch\s*\(|try\s*\{)",
        r"[{;]\s*$",
        r"^\s*(return |yield |async |await )",
        r"=>",
        r"^\s*#include\b",
        r"^\s*package\s+\w+",
        r"^\s*@\w+",  # decorators/annotations
    ]
    lines = stripped.split("\n")
    code_score = 0
    for line in lines[:20]:
        for pattern in code_indicators:
            if re.search(pattern, line, re.MULTILINE):
                code_score += 1
                break
    # Also check for consistent indentation (tabs or spaces)
    indented_lines = sum(1 for l in lines if l.startswith(("  ", "\t")) and l.strip())
    if indented_lines > len(lines) * 0.3:
        code_score += 2

    if code_score >= 2:
        lang_hint = _detect_language(stripped)
        label = f"Code copied ({lang_hint})" if lang_hint else "Code copied"
        return ("code", f"{label} — click to analyze", f"{len(lines)} lines")

    return None


def _detect_language(code: str) -> str:
    """Simple language detection heuristic."""
    if re.search(r"\bdef\s+\w+.*:", code):
        return "Python"
    if re.search(r"\b(const|let|var)\s+\w+\s*=", code):
        return "JavaScript"
    if re.search(r"\bfn\s+\w+\s*\(", code):
        return "Rust"
    if re.search(r"\b(public|private|protected)\s+(static\s+)?(void|int|String|class)\b", code):
        return "Java"
    if re.search(r"^\s*package\s+main\b", code, re.MULTILINE):
        return "Go"
    if re.search(r"#include\s*<", code):
        return "C/C++"
    return ""


def handle_clipboard_change(content: str):
    """Process a clipboard change event."""
    global _last_content, _last_time

    now = time.time()

    with _lock:
        # Debounce
        if now - _last_time < DEBOUNCE_SECONDS:
            return

        # Skip empty / too short
        if not content or len(content.strip()) < MIN_LENGTH:
            return

        # Skip duplicate
        if content == _last_content:
            return

        _last_content = content
        _last_time = now

    # Classify and notify
    result = classify_content(content)
    if result is None:
        return

    action_type, title, body = result

    # Run notification in a thread so we don't block the watcher
    t = threading.Thread(
        target=notify,
        args=(title, body, action_type, content),
        daemon=True,
    )
    t.start()


def run_watcher():
    """Main loop: watch clipboard via wl-paste --watch."""
    print("Costa Clipboard Intelligence daemon starting...", flush=True)

    while True:
        try:
            proc = subprocess.Popen(
                ["wl-paste", "--watch", "cat"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            # Read clipboard contents as they come
            # wl-paste --watch runs `cat` each time clipboard changes,
            # outputting the content followed by EOF on that invocation.
            # But with Popen we get a continuous stream. We need to use
            # wl-paste --watch with a helper that signals content boundaries.
            # Simpler approach: poll wl-paste periodically.
            proc.terminate()
            proc.wait()
        except Exception:
            pass

        # Fallback: polling approach (more reliable across Wayland compositors)
        _run_polling_watcher()


def _run_polling_watcher():
    """Poll clipboard every second for changes."""
    global _last_content

    print("Costa Clipboard: using polling mode", flush=True)

    while True:
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True, text=True, timeout=3,
            )
            content = result.stdout
            if content and content != _last_content:
                handle_clipboard_change(content)
        except subprocess.TimeoutExpired:
            pass
        except FileNotFoundError:
            print("Error: wl-paste not found. Install wl-clipboard.", file=sys.stderr)
            sys.exit(1)
        except Exception:
            pass

        time.sleep(1)


def _run_watch_mode():
    """Use wl-paste --watch with a script that writes to a pipe."""
    print("Costa Clipboard: using watch mode", flush=True)

    fifo_path = Path("/tmp/costa-clipboard-fifo")
    if fifo_path.exists():
        fifo_path.unlink()
    os.mkfifo(str(fifo_path))

    # wl-paste --watch writes to our fifo with a delimiter
    delimiter = "---COSTA-CLIP-END---"
    watch_cmd = f'wl-paste --no-newline --watch bash -c \'cat; echo "{delimiter}"\' > {fifo_path}'

    watch_proc = subprocess.Popen(
        watch_cmd, shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        with open(str(fifo_path), "r") as fifo:
            buffer = []
            for line in fifo:
                if line.strip() == delimiter:
                    content = "".join(buffer)
                    buffer = []
                    handle_clipboard_change(content)
                else:
                    buffer.append(line)
    except KeyboardInterrupt:
        pass
    finally:
        watch_proc.terminate()
        watch_proc.wait()
        if fifo_path.exists():
            fifo_path.unlink()


def main():
    """Entry point."""
    # Handle signals gracefully
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    # Prefer watch mode, fall back to polling
    try:
        # Test if wl-paste supports --watch
        result = subprocess.run(
            ["wl-paste", "--help"],
            capture_output=True, text=True, timeout=3,
        )
        if "--watch" in result.stdout or "--watch" in result.stderr:
            _run_watch_mode()
        else:
            _run_polling_watcher()
    except FileNotFoundError:
        print("Error: wl-paste not found. Install wl-clipboard.", file=sys.stderr)
        sys.exit(1)
    except Exception:
        _run_polling_watcher()


if __name__ == "__main__":
    main()
