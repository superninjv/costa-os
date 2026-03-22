#!/usr/bin/env python3
"""Costa OS — First-run setup wizard.

Terminal-based wizard that configures the system on first boot.
Detects hardware, lets user choose AI tier, packages, and API keys.
Future: GTK4 GUI version.
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path

from config_schema import CostaConfig, AiTier, GpuVendor
from hardware_detect import detect_all, detect_monitors, detect_audio_devices, detect_ir_camera, detect_touchscreen


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
    try:
        answer = input(f"  {C.FOAM}›{C.RESET} {question}{C.DIM}{suffix}{C.RESET}: ").strip()
        return answer or default
    except EOFError:
        print(f"  {C.DIM}(no TTY, using default: {default}){C.RESET}")
        return default


def prompt_choice(question: str, options: list[tuple[str, str]], default: int = 0) -> int:
    print(f"\n  {C.FOAM}›{C.RESET} {question}")
    for i, (label, desc) in enumerate(options):
        marker = f"{C.SEA}●{C.RESET}" if i == default else f"{C.DIM}○{C.RESET}"
        print(f"    {marker} {C.BOLD}{i + 1}{C.RESET}. {label} {C.DIM}— {desc}{C.RESET}")
    while True:
        try:
            choice = input(f"    {C.DIM}Enter choice [{ default + 1}]: {C.RESET}").strip()
        except EOFError:
            print(f"    {C.DIM}(no TTY, using default: {default + 1}){C.RESET}")
            return default
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
    try:
        answer = input(f"  {C.FOAM}›{C.RESET} {question} [{suffix}]: ").strip().lower()
    except EOFError:
        print(f"  {C.DIM}(no TTY, using default: {'yes' if default else 'no'}){C.RESET}")
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def section(title: str):
    print(f"\n{C.SEA}── {C.BOLD}{title}{C.RESET} {C.SEA}{'─' * (50 - len(title))}{C.RESET}\n")


def _run(cmd, **kwargs):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15, **kwargs)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_internet():
    """Return True if we can reach the internet."""
    r = _run(["ping", "-c1", "-W2", "archlinux.org"])
    return r is not None and r.returncode == 0


def wifi_setup():
    """Interactive WiFi connection — runs before anything else."""
    section("Network")

    if check_internet():
        print(f"  {C.OLIVE}✓{C.RESET} Internet connection detected\n")
        return

    # Check if wifi hardware exists
    r = _run(["nmcli", "radio", "wifi"])
    if not r or "enabled" not in r.stdout:
        # Try enabling wifi
        _run(["nmcli", "radio", "wifi", "on"])
        time.sleep(2)
        r = _run(["nmcli", "radio", "wifi"])
        if not r or "enabled" not in r.stdout:
            # No wifi hardware or can't enable — check ethernet
            print(f"  {C.SAND}⚠{C.RESET}  No WiFi adapter found.")
            print(f"  {C.DIM}   Connect an ethernet cable and press Enter to retry,{C.RESET}")
            print(f"  {C.DIM}   or type 'skip' to continue without internet.{C.RESET}")
            try:
                answer = input(f"  {C.FOAM}›{C.RESET} ").strip().lower()
            except EOFError:
                answer = "skip"
            if answer == "skip":
                print(f"  {C.SAND}   Continuing offline — some features won't be available.{C.RESET}\n")
                return
            if check_internet():
                print(f"  {C.OLIVE}✓{C.RESET} Internet connection detected\n")
                return
            print(f"  {C.ROSE}✗{C.RESET} Still no connection. Continuing offline.\n")
            return

    print(f"  {C.TEXT}No internet connection. Let's connect to WiFi.{C.RESET}")
    print(f"  {C.DIM}Scanning for networks...{C.RESET}\n")

    _run(["nmcli", "device", "wifi", "rescan"])
    time.sleep(3)

    while True:
        # Use columnar output — SSIDs can contain colons so -t mode breaks
        r = _run(["nmcli", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
        if not r or r.returncode != 0:
            print(f"  {C.ROSE}✗{C.RESET} Failed to scan WiFi networks.")
            if prompt_bool("Retry?"):
                _run(["nmcli", "device", "wifi", "rescan"])
                time.sleep(3)
                continue
            return

        # Parse columnar output — signal is the rightmost standalone number
        import re
        networks = []
        seen = set()
        for line in r.stdout.strip().splitlines()[1:]:  # skip header
            m = re.match(r'^(.+?)\s{2,}(\d+)\s{2,}(.*)$', line.strip())
            if not m:
                continue
            ssid = m.group(1).strip()
            signal = int(m.group(2))
            security = m.group(3).strip()
            if ssid and ssid != "--" and ssid not in seen:
                seen.add(ssid)
                networks.append({
                    "ssid": ssid,
                    "signal": signal,
                    "security": security if security else "Open",
                })
        networks.sort(key=lambda n: -n["signal"])

        if not networks:
            print(f"  {C.SAND}⚠{C.RESET}  No WiFi networks found.")
            if prompt_bool("Rescan?"):
                _run(["nmcli", "device", "wifi", "rescan"])
                time.sleep(3)
                continue
            return

        # Display networks
        print(f"  {C.FOAM}Available networks:{C.RESET}\n")
        for i, net in enumerate(networks[:20]):
            # Signal bar
            bars = net["signal"] // 20
            bar_str = "█" * bars + "░" * (5 - bars)
            lock = "🔒" if net["security"] != "Open" else "  "
            print(f"    {C.BOLD}{i + 1:2d}{C.RESET}. {lock} {net['ssid']:<32s} {C.DIM}{bar_str} {net['signal']}%  {net['security']}{C.RESET}")

        print(f"\n    {C.DIM} r = rescan  s = skip  q = quit{C.RESET}")
        try:
            choice = input(f"\n  {C.FOAM}›{C.RESET} Network number: ").strip().lower()
        except EOFError:
            choice = "s"

        if choice == "r":
            print(f"\n  {C.DIM}Rescanning...{C.RESET}\n")
            _run(["nmcli", "device", "wifi", "rescan"])
            time.sleep(3)
            continue
        if choice in ("s", "skip"):
            print(f"  {C.SAND}   Continuing offline.{C.RESET}\n")
            return
        if choice in ("q", "quit"):
            sys.exit(0)

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(networks)):
                print(f"  {C.ROSE}Invalid choice{C.RESET}\n")
                continue
        except ValueError:
            print(f"  {C.ROSE}Invalid choice{C.RESET}\n")
            continue

        net = networks[idx]
        ssid = net["ssid"]

        # Try saved connection first
        print(f"\n  {C.DIM}Connecting to {ssid}...{C.RESET}")
        r = _run(["nmcli", "connection", "up", ssid])
        if r and r.returncode == 0:
            time.sleep(2)
            if check_internet():
                print(f"  {C.OLIVE}✓{C.RESET} Connected to {ssid}\n")
                return
            print(f"  {C.OLIVE}✓{C.RESET} Connected (no internet yet — may need captive portal)\n")
            return

        # Need password
        if net["security"] != "Open":
            import getpass
            try:
                password = getpass.getpass(f"  {C.FOAM}›{C.RESET} Password for {ssid}: ")
            except EOFError:
                password = ""
            if not password:
                print(f"  {C.SAND}   Skipped.{C.RESET}\n")
                continue

            print(f"  {C.DIM}Connecting...{C.RESET}")
            r = _run(["nmcli", "device", "wifi", "connect", ssid, "password", password])
        else:
            r = _run(["nmcli", "device", "wifi", "connect", ssid])

        if r and r.returncode == 0:
            time.sleep(2)
            if check_internet():
                print(f"  {C.OLIVE}✓{C.RESET} Connected to {ssid}\n")
                return
            print(f"  {C.OLIVE}✓{C.RESET} Associated with {ssid} (checking internet...)")
            # Give it a few more seconds
            for _ in range(3):
                time.sleep(2)
                if check_internet():
                    print(f"  {C.OLIVE}✓{C.RESET} Internet working!\n")
                    return
            print(f"  {C.SAND}⚠{C.RESET}  Connected but no internet. May need captive portal.\n")
            return
        else:
            err = (r.stderr.strip() if r and r.stderr else "Connection failed")
            print(f"  {C.ROSE}✗{C.RESET} {err}")
            if not prompt_bool("Try another network?"):
                return
            print()


def run_wizard() -> CostaConfig:
    config = CostaConfig()

    banner()
    print(f"  {C.TEXT}Welcome to Costa OS. Let's configure your system.{C.RESET}\n")

    # Network — must come first so packages can be installed
    wifi_setup()

    # Hardware detection
    section("Hardware Detection")
    print(f"  {C.DIM}Scanning hardware...{C.RESET}")
    config.hardware = detect_all()
    config.monitors = detect_monitors()
    sources, sinks = detect_audio_devices()

    print(f"  {C.OLIVE}✓{C.RESET} CPU: {config.hardware.cpu_name} ({config.hardware.cpu_cores} cores)")
    print(f"  {C.OLIVE}✓{C.RESET} RAM: {config.hardware.ram_mb // 1024} GB")
    is_vm = "Virtual" in config.hardware.gpu_name or config.hardware.gpu_name in ("Unknown",)
    if is_vm:
        print(f"  {C.SAND}⚠{C.RESET} GPU: {config.hardware.gpu_name} {C.DIM}(VM detected — local AI models not available){C.RESET}")
    else:
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
    config.timezone = prompt("Timezone", "UTC")

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

    # AI Navigation — requires local LLM for screen reading
    if config.ai_tier.value >= AiTier.VOICE_AND_LLM.value:
        print(f"\n  {C.FOAM}AI Navigation{C.RESET}")
        print(f"  {C.DIM}   Lets Claude Code read and interact with your desktop — browse the web,{C.RESET}")
        print(f"  {C.DIM}   check app state, fill forms — all on an invisible virtual monitor.{C.RESET}")
        print(f"  {C.DIM}   Uses local Ollama to interpret screen content (no extra API cost).{C.RESET}")
        print(f"  {C.DIM}   Requires: AT-SPI accessibility + local LLM.{C.RESET}")
        config.enable_ai_navigation = prompt_bool("   Enable AI navigation?", default=True)
        if config.enable_ai_navigation:
            print(f"  {C.OLIVE}   ✓ Claude will get a virtual headless monitor{C.RESET}")

    # Hardware feature detection: IR camera & touchscreen
    ir_camera = detect_ir_camera()
    has_touch, touch_name = detect_touchscreen()
    config.has_ir_camera = bool(ir_camera)
    config.has_touchscreen = has_touch

    if ir_camera:
        print(f"  {C.OLIVE}✓{C.RESET} IR camera: {ir_camera}")
    if has_touch:
        print(f"  {C.OLIVE}✓{C.RESET} Touchscreen: {touch_name}")

    # Security — Face authentication (only if IR camera detected)
    if config.has_ir_camera:
        section("Security")
        print(f"  {C.FOAM}Face Authentication (Howdy){C.RESET}")
        print(f"  {C.DIM}   Uses your IR camera for Windows Hello-style face unlock.{C.RESET}")
        print(f"  {C.DIM}   Works for login (greetd), sudo, and screen lock (hyprlock).{C.RESET}")
        print(f"  {C.DIM}   Password always works as fallback — face auth is convenience, not security-grade.{C.RESET}")
        config.enable_face_auth = prompt_bool("   Enable face authentication?", default=True)
        if config.enable_face_auth:
            print(f"  {C.OLIVE}   ✓ Howdy will be installed — enroll your face after setup with: sudo howdy add{C.RESET}")

    # Touch — Touchscreen support (only if touchscreen detected)
    if config.has_touchscreen:
        section("Touchscreen")
        print(f"  {C.FOAM}Touch Input & Gestures{C.RESET}")
        print(f"  {C.DIM}   Enables touch input, on-screen keyboard (squeekboard),{C.RESET}")
        print(f"  {C.DIM}   and multi-touch gestures (hyprgrass plugin).{C.RESET}")
        print(f"  {C.DIM}   Gestures: 3-finger swipe for workspaces/launcher, long-press to move windows.{C.RESET}")
        config.enable_touchscreen = prompt_bool("   Enable touchscreen support?", default=True)
        if config.enable_touchscreen:
            print(f"  {C.OLIVE}   ✓ Touch input + on-screen keyboard + gestures will be configured{C.RESET}")

    # API Keys & Services
    section("Services & API Keys")
    print(f"  {C.TEXT}Costa OS connects to external services for cloud AI, voice,{C.RESET}")
    print(f"  {C.TEXT}and communication. All keys are stored locally and never shared.{C.RESET}")
    print(f"  {C.DIM}You can skip any of these and add them later in ~/.config/costa/config.json{C.RESET}\n")

    # Claude API
    print(f"  {C.FOAM}1. Claude Code Authentication{C.RESET}")
    print(f"  {C.DIM}   Powers cloud AI features — code generation, research, web search.{C.RESET}")
    print()
    print(f"  {C.BOLD}   If you have a Claude Pro, Team, or Enterprise plan:{C.RESET}")
    print(f"  {C.OLIVE}   → Skip this step.{C.RESET} {C.DIM}You'll log in with 'claude /login' after install.{C.RESET}")
    print(f"  {C.DIM}   Plan usage is included in your subscription — no API key needed.{C.RESET}")
    print()
    print(f"  {C.DIM}   Only enter an API key if you use pay-per-use billing (console.anthropic.com/keys).{C.RESET}")
    config.anthropic_api_key = prompt("   API key (Enter to skip — most users should skip)")
    if config.anthropic_api_key:
        print(f"  {C.OLIVE}   ✓ API key configured{C.RESET}")
    else:
        print(f"  {C.OLIVE}   ✓ Skipped — you'll authenticate with 'claude /login' after install{C.RESET}")

    # GitHub
    print(f"\n  {C.FOAM}2. GitHub{C.RESET}")
    print(f"  {C.DIM}   Enables gh CLI, git push, PR creation. Authenticate with:{C.RESET}")
    print(f"  {C.DIM}   gh auth login (run after setup){C.RESET}")
    config.setup_github = prompt_bool("   Set up GitHub authentication after install?", default=True)

    # OpenAI (optional, for compatible tools)
    print(f"\n  {C.FOAM}3. OpenAI API (optional){C.RESET}")
    print(f"  {C.DIM}   Some tools support OpenAI-compatible APIs. Not required for Costa AI.{C.RESET}")
    config.openai_api_key = prompt("   OpenAI API key (Enter to skip)")

    print()

    # Keybind configuration
    section("Keybinds")
    print(f"  {C.TEXT}Costa OS uses vim-style keybinds with SUPER as the main modifier.{C.RESET}")
    print(f"  {C.DIM}You can customize all keybinds later with: costa-keybinds{C.RESET}\n")

    ptt_options = [
        ("SUPER+ALT+V", "Default — voice command to AI"),
        ("SUPER+ALT+Space", "Alternative — spacebar is natural for PTT"),
        ("Custom", "Choose your own keybind"),
    ]
    ptt_choice = prompt_choice("Voice assistant push-to-talk keybind", ptt_options, default=0)
    if ptt_choice == 0:
        config.ptt_keybind = ("$mainMod ALT", "V")
    elif ptt_choice == 1:
        config.ptt_keybind = ("$mainMod ALT", "Space")
    else:
        custom_mods = prompt("   Modifiers (e.g., SUPER ALT)", "SUPER ALT")
        custom_key = prompt("   Key (e.g., V, F1, mouse:275)", "V")
        config.ptt_keybind = (custom_mods.replace("SUPER", "$mainMod"), custom_key)

    # Package selection
    section("Packages")
    config.install_dev_tools = prompt_bool("Install developer tools? (git, docker, lazygit, VS Code, etc.)")
    config.install_creative = prompt_bool("Install creative apps? (GIMP, Inkscape, Krita, Audacity, OBS)", default=False)
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
    print(f"  User:         {C.BOLD}{config.username}@{config.hostname}{C.RESET}")
    print(f"  AI Tier:      {C.BOLD}{config.ai_tier.name}{C.RESET}")
    print(f"  GPU:          {config.hardware.gpu_name}")
    if config.ai_tier.value >= 2:
        print(f"  Local LLM:    {config.ollama_smart_model} + {config.ollama_fast_model}")
    else:
        print(f"  Local LLM:    None")
    print(f"  Whisper:      {config.whisper_model} ({config.hardware.whisper_backend.value})")
    print(f"  AI Nav:       {'✓ Virtual monitor' if config.enable_ai_navigation else '✗ Disabled'}")
    if config.has_ir_camera:
        print(f"  Face Auth:    {'✓ Howdy (IR camera)' if config.enable_face_auth else '✗ Disabled'}")
    if config.has_touchscreen:
        print(f"  Touchscreen:  {'✓ Touch + gestures' if config.enable_touchscreen else '✗ Disabled'}")
    print(f"  Claude:       {'✓ API key set' if config.anthropic_api_key else '○ Will use claude /login after install'}")
    print(f"  GitHub:       {'✓ Setup after install' if config.setup_github else '✗ Skipped'}")
    ptt_display = f"{config.ptt_keybind[0]}+{config.ptt_keybind[1]}".replace("$mainMod", "SUPER")
    print(f"  Voice PTT:    {ptt_display}")
    print(f"  Packages:     base" +
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
        "openai_api_key": config.openai_api_key,
        "setup_github": config.setup_github,

        "ptt_keybind": list(config.ptt_keybind),
        "gpu_vendor": config.hardware.gpu_vendor.value,
        "gpu_name": config.hardware.gpu_name,
        "gpu_vram_mb": config.hardware.gpu_vram_mb,
        "install_dev_tools": config.install_dev_tools,
        "install_creative": config.install_creative,
        "install_gaming": config.install_gaming,
        "has_microphone": config.has_microphone,
        "mic_device": config.mic_device,
        "speaker_device": config.speaker_device,
        "enable_ai_navigation": config.enable_ai_navigation,
        "has_ir_camera": config.has_ir_camera,
        "has_touchscreen": config.has_touchscreen,
        "enable_face_auth": config.enable_face_auth,
        "enable_touchscreen": config.enable_touchscreen,
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
