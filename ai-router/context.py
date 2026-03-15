"""Dynamic system context gatherer for Costa AI.

Analyzes the query to determine what system information is relevant,
runs the appropriate commands, and returns context to inject into the prompt.
This gives the local model actual system awareness instead of just static knowledge.
"""

import subprocess
import re
import os
from pathlib import Path


def run(cmd: str, timeout: int = 5) -> str:
    """Run a shell command and return output, empty string on failure."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


def gather_context(query: str) -> str:
    """Analyze query and gather relevant system context.

    Returns a context string to prepend to the prompt, giving the local model
    real system data to reason over instead of guessing.
    """
    q = query.lower()
    context_parts = []

    # Package / software queries
    if _matches(q, r"(package|install|version|what.*install|have.*install|update|upgrade|pacman|yay|aur)"):
        # Check if asking about a specific package
        pkg = _extract_package_name(q)
        if pkg:
            info = run(f"pacman -Qi {pkg} 2>/dev/null || yay -Qi {pkg} 2>/dev/null")
            if info:
                context_parts.append(f"[Package info for {pkg}]\n{info}")
            else:
                # Check if it's available but not installed
                avail = run(f"pacman -Si {pkg} 2>/dev/null | head -5")
                if avail:
                    context_parts.append(f"[{pkg} is available but NOT installed]\n{avail}")
                else:
                    aur = run(f"yay -Si {pkg} 2>/dev/null | head -5")
                    if aur:
                        context_parts.append(f"[{pkg} is available in AUR but NOT installed]\n{aur}")
                    else:
                        context_parts.append(f"[{pkg} is not found in any repository]")
        else:
            # General package listing — check for topic keywords
            topic = _extract_topic(q)
            if topic:
                pkgs = run(f"pacman -Qq | grep -i {topic} 2>/dev/null | head -20")
                if pkgs:
                    context_parts.append(f"[Installed packages matching '{topic}']\n{pkgs}")
                else:
                    context_parts.append(f"[No installed packages match '{topic}']")

    # Service / systemd queries
    if _matches(q, r"(service|systemd|systemctl|running|enabled|status|daemon|start|stop|restart)"):
        svc = _extract_service_name(q)
        if svc:
            status = run(f"systemctl status {svc} 2>/dev/null | head -15")
            if not status:
                status = run(f"systemctl --user status {svc} 2>/dev/null | head -15")
            if status:
                context_parts.append(f"[Service status: {svc}]\n{status}")
            else:
                context_parts.append(f"[Service '{svc}' not found]")
        else:
            # List running services
            svcs = run("systemctl list-units --type=service --state=running --no-pager --no-legend | head -20")
            if svcs:
                context_parts.append(f"[Running services]\n{svcs}")

    # Process / resource queries
    if _matches(q, r"(process|cpu|memory|ram|using|consuming|top|htop|what.*running|kill|pid)"):
        procs = run("ps aux --sort=-%mem | head -12")
        if procs:
            context_parts.append(f"[Top processes by memory]\n{procs}")

    # GPU / VRAM queries
    if _matches(q, r"(gpu|vram|graphics|vulkan|rocm|cuda|render|amdgpu)"):
        gpu_info = run("cat /sys/class/drm/card*/device/mem_info_vram_used 2>/dev/null")
        gpu_total = run("cat /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null")
        if gpu_info and gpu_total:
            used_mb = int(gpu_info) // (1024 * 1024) if gpu_info.isdigit() else 0
            total_mb = int(gpu_total) // (1024 * 1024) if gpu_total.isdigit() else 0
            context_parts.append(f"[GPU VRAM: {used_mb}MB used / {total_mb}MB total]")
        gpu_clients = run("cat /sys/kernel/debug/dri/*/clients 2>/dev/null | head -20")
        if gpu_clients:
            context_parts.append(f"[GPU clients]\n{gpu_clients}")

    # Disk / storage queries
    if _matches(q, r"(disk|storage|space|mount|partition|filesystem|full|free|nvme|ssd)"):
        df = run("df -h --output=source,fstype,size,used,avail,pcent,target -x tmpfs -x devtmpfs 2>/dev/null")
        if df:
            context_parts.append(f"[Disk usage]\n{df}")

    # Network queries
    if _matches(q, r"(network|ip|wifi|ethernet|connection|dns|ping|interface|internet|firewall|port|listening)"):
        ifaces = run("ip -brief addr show 2>/dev/null")
        if ifaces:
            context_parts.append(f"[Network interfaces]\n{ifaces}")
        if _matches(q, r"(port|listening)"):
            ports = run("ss -tlnp 2>/dev/null | head -20")
            if ports:
                context_parts.append(f"[Listening ports]\n{ports}")

    # Audio / PipeWire queries
    if _matches(q, r"(audio|sound|volume|pipewire|wireplumber|speaker|microphone|mic|sink|source)"):
        wpctl = run("wpctl status 2>/dev/null | head -40")
        if wpctl:
            context_parts.append(f"[Audio status]\n{wpctl}")

    # Hyprland / window / workspace queries
    if _matches(q, r"(window|workspace|monitor|hyprland|hyprctl|float|tile|layout|keybind|bind)"):
        if _matches(q, r"(window|client|open|running|focused)"):
            clients = run("hyprctl clients -j 2>/dev/null | python3 -c \"import sys,json;[print(f\\\"{c['class']}: {c['title'][:60]}\\\") for c in json.load(sys.stdin)]\" 2>/dev/null")
            if clients:
                context_parts.append(f"[Open windows]\n{clients}")
        if _matches(q, r"(monitor|display|screen)"):
            monitors = run("hyprctl monitors 2>/dev/null")
            if monitors:
                context_parts.append(f"[Monitors]\n{monitors}")
        if _matches(q, r"(keybind|bind|shortcut|hotkey)"):
            binds = run("hyprctl binds -j 2>/dev/null | python3 -c \"import sys,json;[print(f\\\"{b.get('modmask','')} + {b['key']} → {b['dispatcher']} {b.get('arg','')}\\\") for b in json.load(sys.stdin)]\" 2>/dev/null | head -30")
            if binds:
                context_parts.append(f"[Keybinds]\n{binds}")

    # Docker / container queries
    if _matches(q, r"(docker|container|compose|pod|kubernetes|k8s)"):
        containers = run("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null")
        if containers:
            context_parts.append(f"[Docker containers]\n{containers}")
        else:
            context_parts.append("[Docker: no containers running or Docker not started]")

    # Git queries
    if _matches(q, r"(git|commit|branch|repo|repository|merge|rebase|stash|diff)"):
        # Try to detect which repo user might be asking about
        git_status = run("cd ~ && git -C . status --short 2>/dev/null | head -10")
        # More useful: list recent projects
        projects = run("ls -d ~/projects/*/ 2>/dev/null")
        if projects:
            context_parts.append(f"[Projects in ~/projects/]\n{projects}")

    # File / directory queries
    if _matches(q, r"(file|directory|folder|find|where|locate|config|conf|\.conf|\.config)"):
        # If asking about a specific config file
        config_name = _extract_config_path(q)
        if config_name:
            # Try to find and read it
            found = run(f"find ~/.config -maxdepth 3 -name '*{config_name}*' -type f 2>/dev/null | head -5")
            if found:
                first_file = found.split("\n")[0]
                content = run(f"head -50 '{first_file}' 2>/dev/null")
                context_parts.append(f"[Config file: {first_file}]\n{content}")
            else:
                found = run(f"find /etc -maxdepth 2 -name '*{config_name}*' -type f 2>/dev/null | head -5")
                if found:
                    first_file = found.split("\n")[0]
                    content = run(f"head -50 '{first_file}' 2>/dev/null")
                    context_parts.append(f"[Config file: {first_file}]\n{content}")

    # Ollama / local AI queries
    if _matches(q, r"(ollama|model|llm|local.*(ai|model)|what model)"):
        models = run("ollama list 2>/dev/null")
        if models:
            context_parts.append(f"[Ollama models]\n{models}")
        running = run("ollama ps 2>/dev/null")
        if running:
            context_parts.append(f"[Currently loaded models]\n{running}")

    # User / system info queries
    if _matches(q, r"(uptime|kernel|arch|os|system|hostname|who|user|uname)"):
        info = run("uname -a")
        uptime = run("uptime -p")
        context_parts.append(f"[System: {info}]\n[Uptime: {uptime}]")

    # Environment / path / shell queries
    if _matches(q, r"(env|environment|path|shell|zsh|bash|variable|\$\w+)"):
        if _matches(q, r"(path)"):
            path = run("echo $PATH | tr ':' '\\n' | head -15")
            context_parts.append(f"[PATH entries]\n{path}")
        shell = run("echo $SHELL")
        context_parts.append(f"[Shell: {shell}]")

    # Logs / journal queries
    if _matches(q, r"(log|journal|error|crash|fail|dmesg|kern)"):
        if _matches(q, r"(dmesg|kern|hardware)"):
            logs = run("dmesg --level=err,warn 2>/dev/null | tail -15")
        else:
            logs = run("journalctl --no-pager -p err -n 15 2>/dev/null")
        if logs:
            context_parts.append(f"[Recent error logs]\n{logs}")

    # Date / time queries
    if _matches(q, r"(date|time|day|today|clock|calendar)"):
        dt = run("date '+%A %B %d, %Y %I:%M %p %Z'")
        context_parts.append(f"[Current date/time: {dt}]")

    if not context_parts:
        return ""

    return "\n\n".join(context_parts)


def _matches(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def _extract_package_name(query: str) -> str:
    """Try to extract a specific package name from the query."""
    # "is X installed" / "install X" / "what version of X"
    patterns = [
        r"(?:is|check if)\s+(\S+)\s+installed",
        r"install\s+(\S+)",
        r"version of\s+(\S+)",
        r"update\s+(\S+)",
        r"remove\s+(\S+)",
        r"about\s+(\S+)\s+package",
        r"(\S+)\s+package",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            pkg = m.group(1).strip("?.!,")
            # Filter out common non-package words
            if pkg.lower() not in ("a", "the", "my", "this", "that", "any", "some", "what", "which", "do", "i", "for"):
                return pkg
    return ""


def _extract_service_name(query: str) -> str:
    """Try to extract a service name from the query."""
    patterns = [
        r"(?:status of|start|stop|restart|enable|disable)\s+(\S+)",
        r"(\S+)\s+(?:service|daemon)",
        r"is\s+(\S+)\s+running",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            svc = m.group(1).strip("?.!,")
            if svc.lower() not in ("a", "the", "my", "this", "that", "any"):
                # Append .service if not already there
                if not svc.endswith(".service") and not svc.endswith(".timer") and not svc.endswith(".socket"):
                    return svc
                return svc
    return ""


def _extract_topic(query: str) -> str:
    """Extract a topic keyword for package search."""
    patterns = [
        r"(?:packages?|tools?)\s+(?:for|related to|about)\s+(\w+)",
        r"(?:installed|have).*?(\w+)\s+(?:packages?|tools?|stuff)",
        r"what\s+(\w+)\s+(?:packages?|tools?|stuff)",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            topic = m.group(1)
            if topic.lower() not in ("any", "my", "the", "some", "all", "do", "i"):
                return topic
    return ""


def _extract_config_path(query: str) -> str:
    """Extract a config file or app name for config lookup."""
    patterns = [
        r"(?:config|configuration|conf|settings?)\s+(?:for|of|file)\s+(\w+)",
        r"(\w+)\s+(?:config|configuration|conf|settings?)",
        r"(?:show|read|open|find|where is)\s+(?:the\s+)?(\w+)\s+(?:config|conf)",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            name = m.group(1)
            if name.lower() not in ("my", "the", "this", "a", "show", "me", "find"):
                return name
    return ""
