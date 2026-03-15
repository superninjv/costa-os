"""Costa AI Project Context Switching — switch workspace layouts per project.

"Switch to sonical" opens the right workspace with the right terminals, editor, and env.

Project configs are YAML files in ~/.config/costa/projects/.

Usage:
    python3 project_switch.py sonical
    python3 project_switch.py --list
    python3 project_switch.py --fuzzy "music tabs"
"""

import subprocess
import sys
import os
import re
import time
import json
from pathlib import Path
from dataclasses import dataclass, field


PROJECTS_DIR = Path.home() / ".config" / "costa" / "projects"


@dataclass
class LayoutEntry:
    app: str
    command: str
    position: str = ""


@dataclass
class ProjectConfig:
    name: str
    directory: str
    workspace: int = 1
    layout: list[LayoutEntry] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    on_switch: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    config_path: str = ""


def load_yaml_simple(path: Path) -> dict:
    """Load a YAML file. Uses PyYAML if available, otherwise a simple parser."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        pass

    # Minimal YAML parser for our specific config format
    return _parse_yaml_fallback(path.read_text())


def _parse_yaml_fallback(text: str) -> dict:
    """Minimal YAML-like parser for project configs.

    Handles our specific format: top-level keys, string/int values,
    simple lists (- item), and list-of-dicts (- key: value).
    """
    result = {}
    current_key = None
    current_list = None
    current_dict = None
    indent_level = 0

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        leading = len(line) - len(line.lstrip())

        # Top-level key
        if leading == 0 and ":" in stripped:
            # Save previous list
            if current_key and current_list is not None:
                if current_dict:
                    current_list.append(current_dict)
                    current_dict = None
                result[current_key] = current_list

            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            if val:
                # Inline value
                val = val.strip('"').strip("'")
                # Try int
                try:
                    result[key] = int(val)
                except ValueError:
                    result[key] = val
                current_key = None
                current_list = None
            else:
                # Start of a list or nested structure
                current_key = key
                current_list = []
                current_dict = None
                indent_level = leading
        elif stripped.startswith("- ") and current_list is not None:
            # List item
            if current_dict:
                current_list.append(current_dict)
                current_dict = None

            item_content = stripped[2:].strip()
            if ":" in item_content:
                # Dict entry in list
                k, _, v = item_content.partition(":")
                current_dict = {k.strip(): v.strip().strip('"').strip("'")}
            else:
                # Simple list item
                current_list.append(item_content.strip('"').strip("'"))
        elif ":" in stripped and current_dict is not None:
            # Continuation of a dict in a list
            k, _, v = stripped.partition(":")
            current_dict[k.strip()] = v.strip().strip('"').strip("'")

    # Save last list
    if current_key and current_list is not None:
        if current_dict:
            current_list.append(current_dict)
        result[current_key] = current_list

    return result


def parse_project_config(path: Path) -> ProjectConfig | None:
    """Parse a project YAML config into a ProjectConfig."""
    try:
        data = load_yaml_simple(path)
    except Exception as e:
        print(f"Error loading {path}: {e}", file=sys.stderr)
        return None

    if not data or "name" not in data:
        return None

    layout = []
    for entry in data.get("layout", []):
        if isinstance(entry, dict):
            layout.append(LayoutEntry(
                app=entry.get("app", ""),
                command=entry.get("command", ""),
                position=entry.get("position", ""),
            ))

    return ProjectConfig(
        name=data.get("name", ""),
        directory=data.get("directory", ""),
        workspace=int(data.get("workspace", 1)),
        layout=layout,
        env=[str(e) for e in data.get("env", [])],
        on_switch=[str(c) for c in data.get("on_switch", [])],
        keywords=[str(k) for k in data.get("keywords", [])],
        config_path=str(path),
    )


def list_projects() -> list[ProjectConfig]:
    """List all available project configs."""
    projects = []
    if not PROJECTS_DIR.exists():
        return projects

    for f in sorted(PROJECTS_DIR.glob("*.yaml")):
        cfg = parse_project_config(f)
        if cfg:
            projects.append(cfg)

    for f in sorted(PROJECTS_DIR.glob("*.yml")):
        cfg = parse_project_config(f)
        if cfg:
            projects.append(cfg)

    return projects


def fuzzy_match(query: str, projects: list[ProjectConfig]) -> ProjectConfig | None:
    """Find the best matching project by name or keywords."""
    query_lower = query.lower().strip()
    query_words = set(query_lower.split())

    best = None
    best_score = 0

    for proj in projects:
        score = 0

        # Exact name match
        if query_lower == proj.name.lower():
            return proj

        # Name contains query
        if query_lower in proj.name.lower():
            score += 10

        # Query contains name
        if proj.name.lower() in query_lower:
            score += 8

        # Keyword matching
        for kw in proj.keywords:
            if kw.lower() in query_lower:
                score += 5
            for word in query_words:
                if word in kw.lower() or kw.lower() in word:
                    score += 3

        # Partial name match
        name_lower = proj.name.lower()
        for word in query_words:
            if word in name_lower:
                score += 4

        if score > best_score:
            best_score = score
            best = proj

    return best if best_score > 0 else None


def notify(title: str, body: str, urgency: str = "normal", timeout: int = 5000):
    """Show a dunst notification."""
    subprocess.run([
        "notify-send", "-u", urgency, "-t", str(timeout),
        "-a", "Costa AI", title, body,
    ], check=False)


def run_cmd(cmd: str, timeout: int = 10) -> tuple[int, str]:
    """Run a shell command, return (returncode, output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, "(timed out)"
    except Exception as e:
        return 1, str(e)


def hyprctl(cmd: str) -> str:
    """Run a hyprctl command."""
    try:
        result = subprocess.run(
            ["hyprctl"] + cmd.split(),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_workspace_windows(workspace: int) -> list[dict]:
    """Get list of windows on a specific workspace."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        clients = json.loads(result.stdout)
        return [c for c in clients if c.get("workspace", {}).get("id") == workspace]
    except Exception:
        return []


def close_workspace_windows(workspace: int):
    """Close all windows on the target workspace."""
    windows = get_workspace_windows(workspace)
    for win in windows:
        addr = win.get("address", "")
        if addr:
            hyprctl(f"dispatch closewindow address:{addr}")
            time.sleep(0.1)


def expand_path(path: str) -> str:
    """Expand ~ and env vars in a path."""
    return os.path.expandvars(os.path.expanduser(path))


def switch_project(name: str, close_existing: bool = False) -> bool:
    """Switch to a project by name.

    1. Find matching project config
    2. Optionally close windows on target workspace
    3. Switch to target workspace
    4. Set environment variables
    5. Launch apps in layout
    6. Run on_switch commands
    7. Notify

    Returns True on success.
    """
    projects = list_projects()
    if not projects:
        notify("Project Switch", "No project configs found in ~/.config/costa/projects/", urgency="critical")
        return False

    project = fuzzy_match(name, projects)
    if not project:
        available = ", ".join(p.name for p in projects)
        notify("Project Switch", f"No project matches '{name}'.\nAvailable: {available}", urgency="critical")
        return False

    directory = expand_path(project.directory)

    # Validate directory exists
    if project.directory and not Path(directory).exists():
        notify("Project Switch", f"Directory not found: {directory}", urgency="critical")
        return False

    # Close existing windows on target workspace if requested
    if close_existing:
        close_workspace_windows(project.workspace)
        time.sleep(0.3)

    # Switch to target workspace
    hyprctl(f"dispatch workspace {project.workspace}")
    time.sleep(0.3)

    # Set environment variables
    env = os.environ.copy()
    for var in project.env:
        if "=" in var:
            key, _, val = var.partition("=")
            env[key] = expand_path(val)

    # Launch apps in layout
    for i, entry in enumerate(project.layout):
        if not entry.command:
            continue

        command = expand_path(entry.command)

        # Launch the app
        subprocess.Popen(
            ["bash", "-c", command],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait for window to appear before positioning
        time.sleep(0.8)

        # Position windows using Hyprland dispatch
        if entry.position and len(project.layout) > 1:
            _position_window(entry.position, i, len(project.layout))

    # Run on_switch commands (background tasks like docker compose)
    for cmd in project.on_switch:
        cmd = expand_path(cmd)
        subprocess.Popen(
            ["bash", "-c", cmd],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    notify("Project Switch", f"Switched to {project.name}")
    return True


def _position_window(position: str, index: int, total: int):
    """Position the most recently focused window based on layout position."""
    pos = position.lower()

    if total == 2:
        if pos == "left" and index == 1:
            # Second window appeared — swap so it goes right, first goes left
            hyprctl("dispatch layoutmsg swapwithmaster auto")
        elif pos == "right" and index == 0:
            pass  # First window is master (left by default), that's fine
    elif total == 3:
        if pos == "left" and index == 0:
            pass  # Master position
        elif pos in ("right", "top-right", "bottom-right"):
            if index > 0:
                pass  # Stack position, auto-handled by master layout

    # For explicit positioning with floating or specific coords, use movewindowpixel
    # But for tiling layouts, Hyprland's master/dwindle handle it automatically


def list_projects_formatted() -> str:
    """Return a formatted list of projects for display."""
    projects = list_projects()
    if not projects:
        return "No projects configured.\nAdd YAML configs to ~/.config/costa/projects/"

    lines = []
    for p in projects:
        kw = ", ".join(p.keywords) if p.keywords else ""
        lines.append(f"{p.name} (workspace {p.workspace}) — {p.directory}")
        if kw:
            lines.append(f"  keywords: {kw}")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Costa AI Project Context Switching")
    parser.add_argument("project", nargs="*", help="Project name or search terms")
    parser.add_argument("--list", action="store_true", help="List available projects")
    parser.add_argument("--fuzzy", help="Fuzzy search for a project by name/keywords")
    parser.add_argument("--close-existing", action="store_true",
                        help="Close windows on target workspace before switching")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.list:
        if args.json:
            projects = list_projects()
            data = [{"name": p.name, "directory": p.directory, "workspace": p.workspace,
                      "keywords": p.keywords} for p in projects]
            print(json.dumps(data, indent=2))
        else:
            print(list_projects_formatted())
        return

    query = args.fuzzy or (" ".join(args.project) if args.project else "")
    if not query:
        parser.print_help()
        sys.exit(1)

    success = switch_project(query, close_existing=args.close_existing)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
