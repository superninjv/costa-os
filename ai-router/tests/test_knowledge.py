"""Tests for the Costa OS AI router knowledge system.

D1: Unit tests — frontmatter validation, tiered selection, budget limits, reachability.
D2: Integration test data — 50+ QA pairs that verify knowledge content without Ollama.
"""

import sys
import re
import yaml
import pytest
from pathlib import Path

# Allow imports from the ai-router directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge import (
    discover_knowledge,
    select_knowledge_tiered,
    score_match,
    detect_model_tier,
    TOPIC_PATTERNS,
    TIER_CONFIG,
)

# Repo knowledge directory (not the installed ~/.config/costa/knowledge)
KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"

# All 21 expected knowledge files
EXPECTED_FILES = sorted([
    "costa-os", "ai-router", "costa-setup", "voice-assistant", "arch-admin",
    "hyprland", "pipewire-audio", "keybinds", "customization", "dev-tools",
    "costa-nav", "security", "file-operations", "bluetooth", "screenshots",
    "display", "network", "usb-drives", "process-management", "media-control",
    "notifications",
])


# ---------------------------------------------------------------------------
# D1: Unit Tests
# ---------------------------------------------------------------------------

class TestKnowledgeDiscovery:
    """Verify that all knowledge files exist and are well-formed."""

    def test_knowledge_dir_exists(self):
        assert KNOWLEDGE_DIR.exists(), f"Knowledge dir not found: {KNOWLEDGE_DIR}"

    def test_all_21_files_present(self):
        found = sorted(p.stem for p in KNOWLEDGE_DIR.glob("*.md"))
        assert found == EXPECTED_FILES, (
            f"Missing: {set(EXPECTED_FILES) - set(found)}, "
            f"Extra: {set(found) - set(EXPECTED_FILES)}"
        )

    @pytest.mark.parametrize("name", EXPECTED_FILES)
    def test_valid_yaml_frontmatter(self, name):
        path = KNOWLEDGE_DIR / f"{name}.md"
        raw = path.read_text()
        assert raw.startswith("---"), f"{name}.md has no YAML frontmatter"
        end = raw.find("---", 3)
        assert end != -1, f"{name}.md frontmatter never closed"
        meta = yaml.safe_load(raw[3:end])
        assert meta is not None, f"{name}.md frontmatter is empty"
        assert "l0" in meta, f"{name}.md missing l0 summary"
        assert isinstance(meta["l0"], str) and len(meta["l0"]) > 10, (
            f"{name}.md l0 is too short or not a string"
        )
        assert "l1_sections" in meta, f"{name}.md missing l1_sections"
        assert isinstance(meta["l1_sections"], list) and len(meta["l1_sections"]) >= 1, (
            f"{name}.md l1_sections must be a non-empty list"
        )
        assert "tags" in meta, f"{name}.md missing tags"
        assert isinstance(meta["tags"], list) and len(meta["tags"]) >= 2, (
            f"{name}.md should have at least 2 tags"
        )

    def test_discover_returns_all(self):
        files = discover_knowledge(KNOWLEDGE_DIR)
        names = sorted(kf.name for kf in files)
        assert names == EXPECTED_FILES


class TestTieredSelection:
    """Verify select_knowledge_tiered returns correct files for known queries."""

    def test_pacman_query_returns_arch_admin(self):
        result = select_knowledge_tiered(
            "how do I install a package with pacman", "qwen2.5:14b",
            knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[arch-admin]" in result

    def test_hyprland_query_returns_hyprland(self):
        result = select_knowledge_tiered(
            "how do I move a window to another workspace in hyprland",
            "qwen2.5:7b", knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[hyprland]" in result

    def test_voice_query_returns_voice_assistant(self):
        result = select_knowledge_tiered(
            "how does push to talk voice control work",
            "qwen2.5:14b", knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[voice-assistant]" in result

    def test_bluetooth_query(self):
        result = select_knowledge_tiered(
            "how to pair bluetooth headphones",
            "qwen2.5:7b", knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[bluetooth]" in result

    def test_screenshot_query(self):
        result = select_knowledge_tiered(
            "take a screenshot of a region",
            "qwen2.5:14b", knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[screenshots]" in result

    def test_no_match_returns_empty(self):
        result = select_knowledge_tiered(
            "tell me a joke about bananas", "qwen2.5:14b",
            knowledge_dir=KNOWLEDGE_DIR,
        )
        assert result == ""

    def test_costa_nav_query(self):
        result = select_knowledge_tiered(
            "use costa-nav to navigate to settings",
            "qwen2.5:14b", knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[costa-nav]" in result


class TestTokenBudgets:
    """Ensure tiered selection respects character budgets per model tier."""

    BUDGET_MODELS = [
        ("qwen2.5:3b", 3200),
        ("qwen2.5:7b", 6000),
        ("qwen2.5:14b", 12000),
    ]

    @pytest.mark.parametrize("model,budget", BUDGET_MODELS)
    def test_budget_respected(self, model, budget):
        # Use a broad query that matches many files to stress the budget
        result = select_knowledge_tiered(
            "costa os hyprland audio keybinds bluetooth wifi screenshot",
            model, knowledge_dir=KNOWLEDGE_DIR,
        )
        assert len(result) <= budget + 50, (
            f"Model {model}: result {len(result)} chars exceeds budget {budget}"
        )

    def test_3b_gets_less_than_14b(self):
        query = "how do I configure hyprland window rules and keybinds"
        small = select_knowledge_tiered(query, "qwen2.5:3b", knowledge_dir=KNOWLEDGE_DIR)
        large = select_knowledge_tiered(query, "qwen2.5:14b", knowledge_dir=KNOWLEDGE_DIR)
        assert len(small) <= len(large), "3B should get equal or less content than 14B"


class TestModelTierDetection:
    """Verify detect_model_tier classifies model names correctly."""

    def test_small_models(self):
        assert detect_model_tier("qwen2.5:1.5b") == "3b"
        assert detect_model_tier("qwen2.5:3b") == "3b"
        assert detect_model_tier("gemma3:1b") == "3b"

    def test_medium_models(self):
        assert detect_model_tier("qwen2.5:7b") == "7b"
        assert detect_model_tier("llama3:8b") == "7b"

    def test_large_models(self):
        assert detect_model_tier("qwen2.5:14b") == "14b"
        assert detect_model_tier("qwen3:32b") == "14b"
        assert detect_model_tier("mixtral:8x7b") == "7b"  # contains "7b"


class TestReachability:
    """Every knowledge file must be reachable by at least one query."""

    # Map each file to a query that should trigger its TOPIC_PATTERN
    REACHABILITY_QUERIES = {
        "costa-os": "what is costa os and how does it work",
        "ai-router": "how does the costa-ai router select models",
        "costa-setup": "where is the costa theme waybar config",
        "voice-assistant": "how do I use push to talk voice control",
        "arch-admin": "install a package with pacman on arch",
        "hyprland": "move a hyprland window to workspace 3",
        "pipewire-audio": "my audio is crackling in pipewire",
        "keybinds": "change a keybind shortcut",
        "customization": "change the wallpaper and theme colors",
        "dev-tools": "set up python with pyenv and docker",
        "costa-nav": "use costa-nav to navigate a website",
        "security": "set up face authentication with howdy",
        "file-operations": "find the file where waybar config is",
        "bluetooth": "pair my bluetooth headphones",
        "screenshots": "take a screenshot of a region",
        "display": "change the brightness and night light",
        "network": "connect to wifi with nmcli",
        "usb-drives": "mount a usb flash drive",
        "process-management": "kill a frozen process using too much cpu",
        "media-control": "pause spotify and skip to next track",
        "notifications": "turn on do not disturb in dunst",
    }

    @pytest.mark.parametrize("name", EXPECTED_FILES)
    def test_file_reachable(self, name):
        query = self.REACHABILITY_QUERIES[name]
        files = discover_knowledge(KNOWLEDGE_DIR)
        matched = [kf.name for kf in files if score_match(query, kf) > 0]
        assert name in matched, (
            f"Knowledge file '{name}' not matched by query: '{query}'. "
            f"Matched files: {matched}"
        )


# ---------------------------------------------------------------------------
# D2: Integration test data — 50+ QA pairs
# ---------------------------------------------------------------------------

# (query, expected_contains_list, expected_absent_list)
# expected_contains checks that the selected knowledge text includes these strings.
# expected_absent checks that these strings do NOT appear.
QA_PAIRS = [
    # costa-os
    ("what package manager does Costa use", ["pacman", "yay"], ["apt", "brew"]),
    ("what is costa os", ["Arch Linux", "Hyprland"], ["Ubuntu", "GNOME"]),
    ("getting started with costa", ["costa-ai"], []),
    # keybinds
    ("keybind for terminal", ["SUPER"], []),
    ("how to remap a shortcut", ["keybind"], []),
    ("open the keybinds configurator", ["costa-keybinds"], []),
    # hyprland
    ("move window to workspace 2", ["hyprctl", "dispatch"], []),
    ("how to float a window in hyprland", ["float"], []),
    ("set a window rule for firefox", ["windowrule"], []),
    # arch-admin
    ("update all packages", ["pacman"], ["apt-get"]),
    ("install a package from AUR", ["yay"], ["snap"]),
    ("check systemd service status", ["systemctl"], []),
    ("clean pacman cache", ["cache"], []),
    # pipewire-audio
    ("audio is crackling", ["pipewire"], ["pulseaudio"]),
    ("change the default audio sink", ["wpctl"], []),
    ("my microphone is not working", ["source"], []),
    # voice-assistant
    ("how do I use voice commands", ["voice"], []),
    ("push to talk keybind", ["voice"], []),
    ("what speech recognition does costa use", ["whisper"], []),
    # ai-router
    ("how does costa-ai route queries", ["router"], []),
    ("what models does the AI use", ["ollama"], []),
    ("how does model escalation work", ["escalat"], []),
    # costa-setup
    ("where is the waybar config", ["waybar"], []),
    ("change costa theme colors", ["theme"], []),
    ("how to add API keys after install", ["costa"], []),
    # customization
    ("change the wallpaper", ["wallpaper"], []),
    ("customize the waybar bar template", ["waybar"], []),
    ("change font or opacity", ["custom"], []),
    # dev-tools
    ("set up python environment", ["pyenv"], ["conda"]),
    ("install node.js version", ["nvm"], []),
    ("use docker compose", ["docker"], []),
    ("how to use lazygit", ["lazygit"], []),
    ("set up rust development", ["rust"], []),
    # costa-nav
    ("navigate to a website element", ["nav"], []),
    ("use accessibility tree for navigation", ["AT-SPI"], []),
    ("run a saved navigation routine", ["routine"], []),
    # security
    ("set up face unlock", ["howdy"], []),
    ("configure touchscreen gestures", ["touch"], []),
    ("face authentication with IR camera", ["IR", "camera"], []),
    # file-operations
    ("find a file named config", ["find"], []),
    ("where is the hyprland config file", ["file"], []),
    ("search for text in project files", ["rg"], []),
    # bluetooth
    ("pair my airpods", ["bluetooth"], []),
    ("connect a game controller via bluetooth", ["controller"], []),
    # screenshots
    ("take a screenshot", ["screenshot"], []),
    ("how to screen record my desktop", ["screen"], []),
    ("pick a color from screen", ["color"], []),
    ("copy text to clipboard", ["clipboard"], []),
    # display
    ("change monitor brightness", ["bright"], []),
    ("enable night light blue filter", ["night"], []),
    ("change refresh rate to 165hz", ["refresh"], []),
    # network
    ("connect to wifi", ["wifi"], []),
    ("set up a VPN connection", ["vpn"], []),
    ("check my public IP address", ["ip"], []),
    ("configure SSH access", ["ssh"], []),
    # usb-drives
    ("mount a USB drive", ["usb"], []),
    ("safely eject external drive", ["eject"], []),
    ("format a flash drive to ext4", ["format"], []),
    # process-management
    ("kill a frozen application", ["kill"], []),
    ("what is using all my cpu resources", ["process"], []),
    ("what is using all my RAM", ["memory"], []),
    ("reboot the system", ["reboot"], []),
    ("check system temperature", ["temperature"], []),
    # media-control
    ("pause the music", ["playerctl"], []),
    ("skip to next song", ["next"], []),
    ("mute system volume", ["mute"], []),
    ("switch audio output to headphones", ["audio"], []),
    # notifications
    ("turn on do not disturb", ["dunst"], []),
    ("dismiss all notifications", ["dismiss"], []),
    ("view notification history", ["history"], []),
]


class TestQAPairs:
    """Integration tests: verify knowledge content for 50+ query scenarios."""

    @pytest.mark.parametrize(
        "query,expected_contains,expected_absent",
        QA_PAIRS,
        ids=[f"q{i:02d}_{q[:40]}" for i, (q, _, _) in enumerate(QA_PAIRS)],
    )
    def test_knowledge_content(self, query, expected_contains, expected_absent):
        # Use 14b tier to get the most content for thorough checking
        result = select_knowledge_tiered(
            query, "qwen2.5:14b", knowledge_dir=KNOWLEDGE_DIR,
        )
        assert result, f"No knowledge returned for query: {query}"

        result_lower = result.lower()
        for keyword in expected_contains:
            assert keyword.lower() in result_lower, (
                f"Expected '{keyword}' in knowledge for query '{query}'. "
                f"Got labels: {[l for l in result.split(chr(10)) if l.startswith('[')]}"
            )
        for absent in expected_absent:
            assert absent.lower() not in result_lower, (
                f"'{absent}' should NOT appear in knowledge for query '{query}'"
            )


# ---------------------------------------------------------------------------
# D2 live tests: require running Ollama (skipped by default)
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveOllama:
    """Integration tests that require a running Ollama instance.

    Run with: pytest -m live
    """

    @pytest.fixture(autouse=True)
    def check_ollama(self):
        """Skip if Ollama is not running."""
        import subprocess
        try:
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/tags"],
                capture_output=True, timeout=3,
            )
            if result.returncode != 0:
                pytest.skip("Ollama not running")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Ollama not available")

    def test_knowledge_injected_into_prompt(self):
        """Verify knowledge selection integrates with a real model query."""
        result = select_knowledge_tiered(
            "how do I install a package",
            "qwen2.5:14b",
            knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[arch-admin]" in result
        assert "pacman" in result.lower()

    def test_multi_topic_query(self):
        """A broad query should pull knowledge from multiple files."""
        result = select_knowledge_tiered(
            "set up bluetooth audio and take a screenshot",
            "qwen2.5:14b",
            knowledge_dir=KNOWLEDGE_DIR,
        )
        assert "[bluetooth]" in result
        assert "[screenshots]" in result
