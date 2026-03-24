# Costa OS

A Linux distribution built on Arch Linux and Hyprland. Claude Code ships with full system access, so you describe what you want and the system does it.

**[Documentation](https://synoros.io/costa-os/docs)** | **[Download](https://synoros.io/costa-os)** | **[Terms](https://synoros.io/costa-os/terms)** | **[Privacy](https://synoros.io/costa-os/privacy)**

## What This Repo Contains

This is the open-source intelligence layer that powers Costa OS. It includes the query router, knowledge base, MCP server, voice assistant pipeline, AGS desktop shell, first-boot OOBE, and system agents. You can use these components on any existing Arch Linux + Hyprland setup, or download the full OS from [synoros.io/costa-os](https://synoros.io/costa-os).

```
ai-router/          Query router, ML classifier, auto-escalation, agents, workflows
cli-wrappers/       CLI-Anything: deterministic app control (Firefox, Thunar, Strawberry, etc.)
configs/            Hyprland, Ghostty, Rofi, Dunst, nwg-dock, AGS theme (Costa palette)
installer/          GTK4 OOBE wizard, GUI installer, hardware detection, settings app
knowledge/          32 topic-specific files injected into the local model at query time
mcp-server/         Claude Code MCP server: 16 system tools (screen reading, navigation, CLI registry)
voice-assistant/    Push-to-talk pipeline: DeepFilterNet + Silero VAD + Whisper (Vulkan)
scripts/            VRAM manager, wallpaper, Ollama manager, costa-session, costa-update
shell/              AGS v3 desktop shell: hover-reveal bar, notch, dock, per-monitor widgets
branding/           Wallpapers and logo
docs/               User guide, terms, privacy, hardware compatibility
packages/           Package lists by category (base, dev, creative, gaming)
```

## How It Works

Costa OS is powered by Claude Code in combination with a local model running on your GPU.

- **Claude Code** handles complex tasks: code generation, debugging, system management, multi-step workflows. It has full system access through 16 MCP tools and a hardware-aware CLAUDE.md generated at first boot.
- **Local models** (Ollama on Vulkan, qwen2.5/qwen3.5 family) handle routine queries with sub-second latency and no internet needed.
- **Routing is automatic.** A PyTorch neural classifier learns which model handles which queries best. It ships pre-trained and improves based on your usage. Category-aware routing picks specialist models per query type.
- **CLI-Anything wrappers** give Claude deterministic, instant (~50ms) control over apps like Firefox, Thunar, and Strawberry without screenshots or screen reading.

When cloud models are used, queries go directly to Anthropic. Costa OS has no servers in the middle.

## What's New in v1.1.x

- **GTK4 OOBE** — Full-screen first-boot wizard replaces the terminal setup. Hardware detection, AI tier selection, Claude OAuth, package picker, live progress.
- **AGS v3 desktop shell** — Hover-reveal glassmorphic bar with notch trigger. Workspaces, git status, now playing, audio, PTT voice, battery, Claude launcher, power menu. Per-monitor routing: primary gets bar + notch, secondary gets minimal pill, portrait gets stats bar.
- **macOS-style dock** — nwg-dock-hyprland with auto-hide, shows for 60 seconds on first boot.
- **All bar buttons work** — Power (rofi menu), audio (mute toggle), music (widget panel), Claude (project launcher), voice PTT. Terminal fallback chain (ghostty/foot/kitty).
- **CLI-Anything wrappers** — 12 app wrappers shipped. Claude Code checks `cli_registry` before falling back to screen reading.
- **Autonomous sessions** — `costa-session` runs Claude Code headless with budget caps, tool restrictions, and session logging.
- **Costa Flow** — YAML workflow engine with `claude-code`, `shell`, `costa-ai`, `notify`, `condition`, `wait` step types. Systemd timer scheduling.
- **7 specialized agents** — deployer, sysadmin, architect, builder, janitor, monitor, navigator. Serial queue, scoped tool access.
- **LLM-judge model scoring** — Benchmark suite with Claude Haiku as judge. Category-aware model routing picks the best local model per query type.
- **Vulkan backend** — Ollama uses mesa RADV instead of ROCm HIP (avoids 100% idle GPU bug on RDNA4).

## Quick Start (Existing Arch + Hyprland)

```bash
git clone https://github.com/superninjv/costa-os.git
cd costa-os

# Install dependencies
pip install -r ai-router/requirements.txt

# Set up the router
sudo ln -sf $(pwd)/ai-router/costa-ai /usr/local/bin/costa-ai

# Try it
costa-ai "what GPU do I have"
```

Full setup instructions, including the installer ISO, are at [synoros.io/costa-os/docs](https://synoros.io/costa-os/docs).

## Requirements

- Arch Linux with Hyprland
- Ollama (for local models)
- Any GPU from the last ~10 years, including integrated graphics (Vulkan support for voice transcription)
- Claude Code with an Anthropic account (Pro, Max, or API key) for cloud features

## No Telemetry

Costa OS collects nothing. No analytics, no crash reports, no usage data, no accounts, no servers. The intelligence layer is open source under the Apache License 2.0 so you can verify this yourself.

## License

[Apache License 2.0](LICENSE)
