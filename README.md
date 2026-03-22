# Costa OS

A Linux distribution built on Arch Linux and Hyprland. Claude Code ships with full system access, so you describe what you want and the system does it.

**[Documentation](https://synoros.io/costa-os/docs)** | **[Download](https://synoros.io/costa-os)** | **[Terms](https://synoros.io/costa-os/terms)** | **[Privacy](https://synoros.io/costa-os/privacy)**

## What This Repo Contains

This is the open-source intelligence layer that powers Costa OS. It includes the query router, knowledge base, MCP server, voice assistant pipeline, AGS desktop shell, and system agents. You can use these components on any existing Arch Linux + Hyprland setup, or download the full OS from [synoros.io/costa-os](https://synoros.io/costa-os).

```
ai-router/          Query router, ML classifier, auto-escalation, agents, tools
configs/            Hyprland defaults, Ghostty, Rofi, Dunst (Costa theme)
knowledge/          30+ topic-specific files injected into the local model at query time
mcp-server/         Claude Code MCP server with 30+ system tools
voice-assistant/    Push-to-talk pipeline: DeepFilterNet + Silero VAD + Whisper
scripts/            VRAM manager, wallpaper, theme tools
shell/              AGS v3 desktop shell (hover-reveal bar, widgets)
branding/           Wallpapers and logo
docs/               User guide, terms, privacy policy, hardware compatibility
packages/           Package lists by category
```

## How It Works

Costa OS is powered by Claude Code in combination with a local model running on your GPU.

- **Claude Code** handles complex tasks: code generation, debugging, system management, multi-step workflows. It has full system access through 30+ MCP tools and a hardware-aware context file generated at first boot.
- **Local models** (Ollama, qwen2.5 family) handle routine queries with sub-second latency and no internet needed.
- **Routing is automatic.** A PyTorch neural classifier learns which model handles which queries best. It ships pre-trained and improves based on your usage.

When cloud models are used, queries go directly to Anthropic. Costa OS has no servers in the middle.

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
- Any GPU from the last ~10 years, including integrated graphics on Intel/AMD laptops (Vulkan support for voice transcription)

  - Not Required, but intended: Claude Code with an Anthropic account (Pro, Max, or API key)

## No Telemetry

Costa OS collects nothing. No analytics, no crash reports, no usage data, no accounts, no servers. The intelligence layer is open source under the Apache License 2.0 so you can verify this yourself.

## License

[Apache License 2.0](LICENSE)
