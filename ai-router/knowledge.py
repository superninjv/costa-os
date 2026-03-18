"""Tiered knowledge loader — auto-discovers knowledge files and loads content
matched to query relevance and model capability.

Replaces the inline select_knowledge() in router.py with:
- YAML frontmatter parsing (l0 summaries, l1 section lists, tags)
- Regex + tag-based scoring
- Model-tier-aware loading (3B gets less context, 14B gets more)
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field


KNOWLEDGE_DIR = Path.home() / ".config" / "costa" / "knowledge"

# Regex patterns per topic — same as router.py but used for scoring here
TOPIC_PATTERNS = {
    "arch-admin": r"(package|pacman|yay|install|update|upgrade|systemd|systemctl|service|journal|orphan|cache|downgrade)",
    "hyprland": r"(hyprland|hyprctl|window|workspace|monitor|keybind|bind|dispatch|float|tile|rule|config.*hypr|mouse\s*button|remap|hotkey|shortcut)",
    "pipewire-audio": r"(audio|sound|volume|pipewire|wireplumber|speaker|mic|microphone|sink|source|alsa|pulse|crackling)",
    "costa-setup": r"(costa|theme|waybar|ghostty|rofi|dunst|wallpaper|config|dotfile|chezmoi|setup|customize)",
    "dev-tools": r"(python|pyenv|node|nvm|rust|cargo|java|sdk|docker|compose|git|lazygit|zellij|kubectl|k9s)",
    "voice-assistant": r"(voice|whisper|speech|transcri|speak|say|talk.*ai|ptt|push.*talk|vad|silero)",
    "ai-router": r"(costa.ai|router|route|model\s*select|escalat|ollama\s*model|local\s*model|cloud\s*model)",
    "keybinds": r"(keybind|shortcut|hotkey|bind|mouse\s*button|remap|rebind|costa-keybinds|keybinds?\s*gui|configurator)",
    "customization": r"(custom|theme|color|wallpaper|font|opacity|animation|window\s*rule|config.*change|waybar|bar\s*template|monitor.*bar|performance\s*bar|taskbar|generate.*waybar)",
    "costa-os": r"(costa\s*os|how\s*does|getting\s*started|overview|what\s*is|help\s*me|tutorial)",
    "costa-nav": r"(costa.nav|navigate|navigation|at.spi|accessibility\s*tree|screen\s*read|headless|virtual\s*monitor|saved\s*routine)",
    "security": r"(face\s*(auth|unlock|recognition|login)|howdy|ir\s*camera|touchscreen|touch\s*(gesture|input|screen)|squeekboard|hyprgrass|pam|biometric)",
    "file-operations": r"(find\s*(file|folder|dir|the)|where\s*is|locate|search\s*for|look\s*for|open\s*(file|folder)|file\s*manager|rename|move\s*file|copy\s*file|delete\s*file|disk\s*(usage|space)|large\s*files)",
    "bluetooth": r"(bluetooth|bt\s|pair|airpod|headphone|earbuds|controller\s*(connect|pair|bluetooth)|bluetoothctl|wireless\s*(headphone|speaker|earbuds))",
    "screenshot-ai": r"(screenshot|screen\s*shot|screen\s*record|record\s*screen|snip|capture\s*screen|color\s*pick|ocr|analyze\s*screen)",
    "display": r"(bright|dim\s*(screen|display)|night\s*light|blue\s*light|gamma|color\s*temp|refresh\s*rate|resolution|scale|rotate\s*monitor|mirror\s*monitor|hdmi|displayport)",
    "network": r"(wifi|wi-fi|internet|ethernet|vpn|wireguard|dns|firewall|ip\s*addr|ssh\s|connect\s*to\s*(network|wifi|internet)|nmcli|hostname|public\s*ip|speed\s*test)",
    "usb-drives": r"(usb\s*(drive|stick|flash)|mount|unmount|eject|external\s*(drive|disk|ssd|hdd)|thumb\s*drive|flash\s*drive|format\s*(drive|usb|disk)|fat32|ntfs|ext4\s*format)",
    "process-management": r"(kill|frozen|hang|not\s*responding|cpu\s*usage|ram\s*usage|memory\s*usage|what.s\s*(running|using)|shutdown|reboot|restart\s*(computer|system)|suspend|sleep\s*mode|lock\s*screen|uptime|temperature|overheat)",
    "music-control": r"(play|pause|skip|next\s*track|prev|volume|mute|unmute|now\s*playing|what.s\s*playing|music|spotify|playerctl|switch\s*(audio|output|speaker|headphone)|cold\s*start|music\s*widget)",
    "notifications": r"(notification|notify|do\s*not\s*disturb|dnd|dunst|dismiss|alert|toast)",
    "getting-started": r"(get(ting)?\s*started|first\s*time|new\s*(user|to)|beginner|basics|cheat\s*sheet|essential\s*keybind|where\s*do\s*i\s*start|how\s*do\s*i\s*(start|begin|use\s*this)|learn|tutorial|help\s*me|teach\s*me|show\s*me\s*how)",
    "ai-intelligence": r"(costa.ai|smart\s*routing|model\s*routing|escalat|train\s*router|ml\s*router|report\s*bad|usage\s*stats|budget|query\s*history)",
    "vram-manager": r"(vram|gpu\s*memory|model\s*tier|ollama\s*manager|gpu\s*budget|model\s*switch|auto.?load|unload\s*model)",
    "workflows": r"(workflow|costa.flow|automat|schedule|cron|multi.step|pipeline|morning\s*briefing|system.health\s*check)",
    "project-management": r"(project\s*(switch|manage|config|context)|switch\s*to\s*\w+\s*project|workspace\s*setup|project\s*yaml)",
    "claude-code": r"(claude\s*code|mcp\s*server|slash\s*command|custom\s*command|virtual\s*monitor|headless|claude\s*launch|claude\s*model\s*pick)",
    "clipboard-intelligence": r"(clipboard|copy\s*paste|auto.?classify|clipboard\s*daemon|clipboard\s*action)",
    "face-auth": r"(face\s*(auth|unlock|recognition|login|enroll)|howdy|ir\s*camera|biometric)",
    "touchscreen": r"(touchscreen|touch\s*(gesture|input|screen)|squeekboard|hyprgrass|on.screen\s*keyboard|swipe\s*gesture)",
    "settings-hub": r"(settings|costa.settings|settings\s*hub|configure\s*display|configure\s*ai|system\s*settings)",
    "agents": r"(agent|sysadmin\s*agent|architect\s*agent|costa.agents|agent\s*pool|dispatch\s*agent)",
}

# Token budget per model tier (approximate — measured in chars, ~4 chars/token)
TIER_CONFIG = {
    "3b": {"top_l1": 2, "full": 0, "budget_chars": 3200},    # ~800 tokens
    "7b": {"top_l1": 3, "full": 0, "budget_chars": 6000},    # ~1500 tokens
    "14b": {"top_l1": 3, "full": 1, "budget_chars": 12000},   # ~3000 tokens
}


@dataclass
class KnowledgeFile:
    """Parsed knowledge file with frontmatter metadata."""
    name: str               # filename without .md
    path: Path
    l0: str = ""            # one-line summary
    l1_sections: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    _content: str | None = None
    _sections: dict | None = None

    @property
    def content(self) -> str:
        """Full file content (without frontmatter)."""
        if self._content is None:
            self._load()
        return self._content

    @property
    def sections(self) -> dict[str, str]:
        """Dict of H2 header -> section content."""
        if self._sections is None:
            self._parse_sections()
        return self._sections

    def _load(self):
        """Load and strip frontmatter from content."""
        raw = self.path.read_text()
        # Strip YAML frontmatter
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                self._content = raw[end + 3:].strip()
                return
        self._content = raw.strip()

    def _parse_sections(self):
        """Parse H2 sections from content."""
        self._sections = {}
        current_header = None
        current_lines = []

        for line in self.content.split("\n"):
            if line.startswith("## "):
                if current_header:
                    self._sections[current_header] = "\n".join(current_lines).strip()
                current_header = line[3:].strip()
                current_lines = []
            elif current_header is not None:
                current_lines.append(line)
            # Lines before first H2 go under the H1 title
            elif current_header is None and not line.startswith("# "):
                current_lines.append(line)

        if current_header:
            self._sections[current_header] = "\n".join(current_lines).strip()

    def l1_content(self, section_names: list[str] | None = None) -> str:
        """Return selected H2 sections. If no names given, uses l1_sections from frontmatter."""
        names = section_names or self.l1_sections
        parts = []
        for name in names:
            if name in self.sections:
                parts.append(f"## {name}\n{self.sections[name]}")
        return "\n\n".join(parts) if parts else self.content[:500]


def discover_knowledge(knowledge_dir: Path | str | None = None) -> list[KnowledgeFile]:
    """Auto-discover and parse all knowledge files with frontmatter."""
    kdir = Path(knowledge_dir) if knowledge_dir else KNOWLEDGE_DIR
    if not kdir.exists():
        return []

    files = []
    for path in sorted(kdir.glob("*.md")):
        if path.name.startswith("."):
            continue

        kf = KnowledgeFile(name=path.stem, path=path)

        # Parse YAML frontmatter
        raw = path.read_text()
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                try:
                    meta = yaml.safe_load(raw[3:end])
                    if meta:
                        kf.l0 = meta.get("l0", "")
                        kf.l1_sections = meta.get("l1_sections", [])
                        kf.tags = meta.get("tags", [])
                except yaml.YAMLError:
                    pass

        files.append(kf)

    return files


def score_match(query: str, kf: KnowledgeFile) -> int:
    """Score how relevant a knowledge file is to a query.

    Scoring:
    - Regex pattern match: 3 points
    - Tag hit: 1 point each
    """
    score = 0
    q = query.lower()

    # Regex pattern match (from TOPIC_PATTERNS)
    pattern = TOPIC_PATTERNS.get(kf.name)
    if pattern and re.search(pattern, q, re.IGNORECASE):
        score += 3

    # Tag matching
    for tag in kf.tags:
        # Tags can be multi-word like "face-auth" — match either hyphenated or spaced
        tag_variants = [tag, tag.replace("-", " "), tag.replace("-", "")]
        for variant in tag_variants:
            if variant in q:
                score += 1
                break

    return score


def detect_model_tier(model_name: str) -> str:
    """Detect the tier from an Ollama model name."""
    name = model_name.lower()
    if "1.5b" in name or "1b" in name or "3b" in name:
        return "3b"
    if "7b" in name or "8b" in name:
        return "7b"
    # 14b, 32b, 72b, or unknown — use 14b tier (most generous)
    return "14b"


def select_knowledge_tiered(query: str, model_name: str,
                            knowledge_dir: Path | str | None = None) -> str:
    """Select and format knowledge for a query, respecting model tier limits.

    Returns formatted knowledge string ready for prompt injection.
    """
    files = discover_knowledge(knowledge_dir)
    if not files:
        return ""

    tier = detect_model_tier(model_name)
    config = TIER_CONFIG[tier]

    # Score all files
    scored = [(score_match(query, kf), kf) for kf in files]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Filter to files with any relevance
    relevant = [(s, kf) for s, kf in scored if s > 0]
    if not relevant:
        return ""

    # Build output within budget
    budget = config["budget_chars"]
    parts = []
    used = 0

    # Top N files at L1 (selected sections)
    top_l1_count = config["top_l1"]
    full_count = config["full"]

    for i, (score, kf) in enumerate(relevant):
        if used >= budget:
            break

        if i < full_count:
            # Full content for top file(s) on 14B
            text = kf.content
            label = f"[{kf.name}]"
        elif i < full_count + top_l1_count:
            # L1 — selected sections
            text = kf.l1_content()
            label = f"[{kf.name}]"
        else:
            # L0 — just the summary line
            text = kf.l0
            label = f"[{kf.name}]"

        entry = f"{label}\n{text}"
        if used + len(entry) > budget:
            # Truncate to fit
            remaining = budget - used - len(label) - 2
            if remaining > 100:
                entry = f"{label}\n{text[:remaining]}..."
            else:
                # Just use L0 summary
                entry = f"{label}\n{kf.l0}"
        parts.append(entry)
        used += len(entry)

    return "\n\n".join(parts)


def get_matched_files(query: str, knowledge_dir: Path | str | None = None) -> list[str]:
    """Return list of knowledge file names that match a query (for report.py)."""
    files = discover_knowledge(knowledge_dir)
    return [kf.name for kf in files if score_match(query, kf) > 0]
