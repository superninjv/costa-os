#!/usr/bin/env python3
"""Costa OS — First-run setup wizard.

Terminal-based wizard that configures the system on first boot.
Detects hardware, lets user choose AI tier, packages, and API keys.
Future: GTK4 GUI version.
"""

import os
import sys
import json
from pathlib import Path

from config_schema import CostaConfig, AiTier, GpuVendor
from hardware_detect import detect_all, detect_monitors, detect_audio_devices


# Costa palette for terminal output
class C:
    SEA = "\033[38;2;91;148;168m"
    FOAM = "\033[38;2;126;181;176m"
    SAND = "\033[38;2;201;169;110m"
    TERRACOTTA = "\033[38;2;192;122;86m"
    OLIVE = "\033[38;2;139;153;104m"
    ROSE = "\033[38;2;184;114;114m"
    TEXT = "\033[38;2;212;207;196m"
    DIM = "\033[38;2;154;158;181m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def banner():
    print(f"""
{C.SEA}╔══════════════════════════════════════════════════════╗
║                                                      ║
║   {C.FOAM}█▀▀ █▀█ █▀ ▀█▀ █▀█   {C.SEA}█▀█ █▀                      ║
║   {C.FOAM}█▄▄ █▄█ ▄█  █  █▀█   {C.SEA}█▄█ ▄█                      ║
║                                                      ║
║   {C.DIM}AI-Native Linux Distribution{C.SEA}                       ║
║   {C.DIM}First-Run Setup Wizard{C.SEA}                             ║
║                                                      ║
╚══════════════════════════════════════════════════════╝{C.RESET}
""")


def prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {C.FOAM}›{C.RESET} {question}{C.DIM}{suffix}{C.RESET}: ").strip()
    return answer or default


def prompt_choice(question: str, options: list[tuple[str, str]], default: int = 0) -> int:
    print(f"\n  {C.FOAM}›{C.RESET} {question}")
    for i, (label, desc) in enumerate(options):
        marker = f"{C.SEA}●{C.RESET}" if i == default else f"{C.DIM}○{C.RESET}"
        print(f"    {marker} {C.BOLD}{i + 1}{C.RESET}. {label} {C.DIM}— {desc}{C.RESET}")
    while True:
        choice = input(f"    {C.DIM}Enter choice [{ default + 1}]: {C.RESET}").strip()
        if not choice:
            return default
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(f"    {C.ROSE}Invalid choice{C.RESET}")


def prompt_bool(question: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"  {C.FOAM}›{C.RESET} {question} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def section(title: str):
    print(f"\n{C.SEA}── {C.BOLD}{title}{C.RESET} {C.SEA}{'─' * (50 - len(title))}{C.RESET}\n")


def run_wizard() -> CostaConfig:
    config = CostaConfig()

    banner()
    print(f"  {C.TEXT}Welcome to Costa OS. Let's configure your system.{C.RESET}\n")

    # Hardware detection
    section("Hardware Detection")
    print(f"  {C.DIM}Scanning hardware...{C.RESET}")
    config.hardware = detect_all()
    config.monitors = detect_monitors()
    sources, sinks = detect_audio_devices()

    print(f"  {C.OLIVE}✓{C.RESET} CPU: {config.hardware.cpu_name} ({config.hardware.cpu_cores} cores)")
    print(f"  {C.OLIVE}✓{C.RESET} RAM: {config.hardware.ram_mb // 1024} GB")
    print(f"  {C.OLIVE}✓{C.RESET} GPU: {config.hardware.gpu_name} ({config.hardware.gpu_vram_mb} MB VRAM)")
    print(f"  {C.OLIVE}✓{C.RESET} Monitors: {len(config.monitors)}")
    for m in config.monitors:
        print(f"      {m.name}: {m.resolution}@{m.refresh_rate}Hz")
    if sources:
        print(f"  {C.OLIVE}✓{C.RESET} Microphones: {', '.join(sources)}")
    if sinks:
        print(f"  {C.OLIVE}✓{C.RESET} Speakers: {', '.join(sinks)}")

    max_tier = config.hardware.max_ai_tier
    print(f"\n  {C.FOAM}Max AI capability: {C.BOLD}{max_tier.name}{C.RESET}")
    models = config.hardware.recommended_models
    if models.smart_model:
        pair_str = f"{models.smart_model} (smart) + {models.fast_model} (fast)" if models.fast_model else models.smart_model
        print(f"  {C.FOAM}Recommended local models: {C.BOLD}{pair_str}{C.RESET}")

    # User setup
    section("User Setup")
    config.username = prompt("Username", os.environ.get("USER", "costa"))
    config.hostname = prompt("Hostname", "costa")
    config.timezone = prompt("Timezone", "America/New_York")

    # AI Configuration
    section("AI Configuration")
    tier_options = []
    for tier in AiTier:
        enabled = tier.value <= max_tier.value
        descriptions = {
            AiTier.CLOUD_ONLY: "Claude API only, no local models",
            AiTier.VOICE_ONLY: "Local Whisper STT + Claude API for answers",
            AiTier.VOICE_AND_LLM: "Local Whisper + local LLM + Claude for complex tasks",
            AiTier.FULL_WORKSTATION: "Everything local + ML training capability",
        }
        label = f"{tier.name}" + ("" if enabled else f" {C.ROSE}(insufficient VRAM){C.RESET}")
        tier_options.append((label, descriptions[tier]))

    default_tier = min(max_tier.value, AiTier.VOICE_AND_LLM.value)
    chosen_tier = prompt_choice("AI tier", tier_options, default=default_tier)
    config.ai_tier = AiTier(chosen_tier)

    if config.ai_tier.value >= AiTier.VOICE_AND_LLM.value:
        models = config.hardware.recommended_models
        config.ollama_smart_model = models.smart_model or "qwen2.5:3b"
        config.ollama_fast_model = models.fast_model or config.ollama_smart_model
        print(f"\n  {C.DIM}Smart model: {config.ollama_smart_model}{C.RESET}")
        print(f"  {C.DIM}Fast model:  {config.ollama_fast_model}{C.RESET}")

    config.whisper_model = config.hardware.whisper_model
    print(f"  {C.DIM}Whisper model: {config.whisper_model} ({config.hardware.whisper_backend.value}){C.RESET}")

    # API Key
    section("Claude API")
    print(f"  {C.DIM}An Anthropic API key enables cloud AI features (Sonnet, Opus, web search).{C.RESET}")
    print(f"  {C.DIM}Get one at: https://console.anthropic.com/keys{C.RESET}")
    config.anthropic_api_key = prompt("Anthropic API key (optional, Enter to skip)")
    if not config.anthropic_api_key:
        print(f"  {C.SAND}Skipped — you can add it later in ~/.config/costa/config.json{C.RESET}")

    # Package selection
    section("Packages")
    config.install_dev_tools = prompt_bool("Install developer tools? (git, docker, lazygit, VS Code, etc.)")
    config.install_creative = prompt_bool("Install creative apps? (GIMP, Inkscape, Krita, REAPER)", default=False)
    config.install_gaming = prompt_bool("Install gaming? (Steam, Gamemode, MangoHud)", default=False)

    # Audio
    section("Audio")
    config.has_microphone = prompt_bool("Do you have a microphone for voice commands?")
    if sources and config.has_microphone:
        mic_idx = prompt_choice("Select microphone", [(s, "") for s in sources])
        config.mic_device = sources[mic_idx]
    if sinks:
        spk_idx = prompt_choice("Select speakers/output", [(s, "") for s in sinks])
        config.speaker_device = sinks[spk_idx]

    # Summary
    section("Summary")
    print(f"  User:       {C.BOLD}{config.username}@{config.hostname}{C.RESET}")
    print(f"  AI Tier:    {C.BOLD}{config.ai_tier.name}{C.RESET}")
    print(f"  GPU:        {config.hardware.gpu_name}")
    if config.ai_tier.value >= 2:
        print(f"  Local LLM:  {config.ollama_smart_model} + {config.ollama_fast_model}")
    else:
        print(f"  Local LLM:  None")
    print(f"  Whisper:    {config.whisper_model} ({config.hardware.whisper_backend.value})")
    print(f"  Claude API: {'Configured' if config.anthropic_api_key else 'Not set'}")
    print(f"  Packages:   base" +
          (" + dev" if config.install_dev_tools else "") +
          (" + creative" if config.install_creative else "") +
          (" + gaming" if config.install_gaming else ""))
    print()

    errors = config.validate()
    if errors:
        for e in errors:
            print(f"  {C.ROSE}✗ {e}{C.RESET}")
        return config

    if prompt_bool("Proceed with installation?"):
        save_config(config)
        print(f"\n  {C.OLIVE}✓ Configuration saved to ~/.config/costa/config.json{C.RESET}")
        print(f"  {C.FOAM}Starting installation...{C.RESET}\n")
    else:
        print(f"\n  {C.SAND}Installation cancelled.{C.RESET}\n")

    return config


def save_config(config: CostaConfig):
    """Save configuration to JSON."""
    config_dir = Path.home() / ".config" / "costa"
    config_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "username": config.username,
        "hostname": config.hostname,
        "timezone": config.timezone,
        "ai_tier": config.ai_tier.name,
        "ollama_smart_model": config.ollama_smart_model,
        "ollama_fast_model": config.ollama_fast_model,
        "whisper_model": config.whisper_model,
        "whisper_backend": config.hardware.whisper_backend.value,
        "anthropic_api_key": config.anthropic_api_key,
        "gpu_vendor": config.hardware.gpu_vendor.value,
        "gpu_name": config.hardware.gpu_name,
        "gpu_vram_mb": config.hardware.gpu_vram_mb,
        "install_dev_tools": config.install_dev_tools,
        "install_creative": config.install_creative,
        "install_gaming": config.install_gaming,
        "has_microphone": config.has_microphone,
        "mic_device": config.mic_device,
        "speaker_device": config.speaker_device,
        "theme": config.theme,
        "monitors": [
            {
                "name": m.name,
                "resolution": m.resolution,
                "refresh_rate": m.refresh_rate,
                "position": m.position,
                "scale": m.scale,
                "transform": m.transform,
                "primary": m.primary,
            }
            for m in config.monitors
        ],
    }

    with open(config_dir / "config.json", "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    config = run_wizard()
