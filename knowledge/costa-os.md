---
l0: "Costa OS system overview: architecture, keybinds, config locations, window management, workflows, usage tracking, troubleshooting"
l1_sections: ["Architecture", "Key Commands", "Config Locations", "Reloading Configs", "Default Keybinds", "Window Management", "Security", "IMPORTANT — This is Linux", "Costa Apps (GTK4/libadwaita)", "Music", "Troubleshooting", "Gotchas & Pitfalls"]
tags: [overview, getting-started, architecture, keybinds, config, window-management, troubleshooting, wayland, hyprland, pacman, workflow, costa-flow, usage, budget, ags, shell-bar]
---
# Costa OS — System Guide

Costa OS is an AI-native Linux distribution built on Arch Linux + Hyprland.
The AI is the primary interface — users interact via voice, text, or traditional keybinds.

## Architecture
- Base: Arch Linux (rolling release, pacman + yay for AUR)
- Compositor: Hyprland (Wayland tiling window manager)
- AI Layer: costa-ai router (local Ollama + Claude API with 30+ tools + ML routing)
- Persistence: SQLite database (~/.config/costa/costa.db) for query history, usage, costs
- Knowledge: Obsidian vault (~/notes/) — Claude's persistent memory, connected via MCP
- Workflows: costa-flow engine with YAML definitions + systemd timers
- Voice: Whisper.cpp STT → costa-ai → action/response
- Theme: Costa (Mediterranean coastal dark palette)

## Key Commands
- `costa-ai "question"` — ask the AI anything about the system
- `costa-ai --json "query"` — get structured JSON response
- `costa-ai --history` — browse past queries and responses
- `costa-ai --search "term"` — search query history
- `costa-ai --usage` — usage stats by model and cost
- `costa-ai --budget 5.00` — set daily spending limit
- `costa-ai --stop` — cancel a running AI query
- `costa-ai --index ~/docs` — index documents for RAG search
- `costa-ai --train-router` — retrain ML routing classifier
- `costa-ai --preset code` — switch routing preset (code/research/fast)
- `costa-flow run morning-briefing` — run a workflow
- `costa-flow list` — list available workflows
- `costa-flow enable system-health` — activate workflow on timer
- `costa-settings` — open the settings hub (also in rofi or shell bar ⚙ icon)
- `costa-keybinds-gui` — open the keybinds/mouse configurator (also in rofi or shell bar 󰌌 icon)
- `costa-keybinds list` — show all keyboard shortcuts (CLI)
- `costa-keybinds mouse` — show mouse button mappings (CLI)

## Config Locations
- Hyprland: ~/.config/hypr/hyprland.conf
- Monitor overrides: ~/.config/hypr/monitors.conf (auto-generated)
- AGS shell: ~/.config/ags/
- Ghostty terminal: ~/.config/ghostty/config
- Rofi launcher: ~/.config/rofi/config.rasi
- Dunst notifications: ~/.config/dunst/dunstrc
- Costa AI config: ~/.config/costa/config.json
- AI system prompt: ~/.config/costa/system-ai.md
- Knowledge bases: ~/.config/costa/knowledge/
- AI database: ~/.config/costa/costa.db (query history, usage, costs)
- Workflows: ~/.config/costa/workflows/ (YAML definitions)
- GPU config: ~/.config/costa/gpu.conf
- AI PID file: /tmp/costa-ai.pid (for --stop cancellation)

## Reloading Configs
- Hyprland: `hyprctl reload` (no restart needed)
- AGS shell: `ags quit; ags run -d ~/.config/ags`
- Dunst: `killall dunst; dunst &disown`
- Rofi: no reload needed (reads config on each launch)

## Default Keybinds
- SUPER+Return — terminal
- SUPER+B — browser
- SUPER+E — file manager
- SUPER+Space — app launcher (rofi)
- SUPER+Q — close window
- SUPER+F — fullscreen
- SUPER+SHIFT+F — toggle floating
- SUPER+H/J/K/; — focus left/down/up/right (vim-style)
- SUPER+SHIFT+H/J/K/; — move window
- SUPER+CTRL+H/J/K/; — resize window
- SUPER+1-9 — switch workspace
- SUPER+SHIFT+1-9 — move window to workspace
- SUPER+ALT+V — voice command (Claude mode)
- SUPER+ALT+B — voice command (type mode)
- SUPER+V — clipboard history
- SUPER+]/[ — next/prev track
- SUPER+\ — play/pause
- Print — screenshot region to file
- SUPER+Print — screenshot region to clipboard

## Window Management
- Hide a window (keep running): `hyprctl dispatch movetoworkspacesilent special:name,address:ADDR`
- Show hidden windows: `hyprctl dispatch togglespecialworkspace name`
- Find window address: `hyprctl clients -j | jq '.[] | select(.class == "appname") | .address'`
- Minimize to special workspace: useful for background apps like music players
- Strawberry runs hidden in `special:music` — toggle with SUPER+ALT+M

## Security
- Face authentication (howdy) — Windows Hello-style face unlock via IR camera
  - Login (greetd), sudo, screen lock (hyprlock)
  - Password always works as fallback
  - Manage: `sudo howdy add` (enroll), `sudo howdy test`, `sudo howdy list`
- Touchscreen support — libinput + squeekboard (on-screen keyboard) + hyprgrass (gestures)
  - Config: ~/.config/hypr/touch.conf
  - Both are hardware-gated — only enabled if detected during first-boot

## IMPORTANT — This is Linux
This is Arch Linux with Hyprland (Wayland). NEVER give Windows or macOS advice.
- Window manager: Hyprland (hyprctl commands), NOT Windows taskbar
- Package manager: pacman/yay, NOT apt/brew/chocolatey
- Audio: PipeWire + WirePlumber (wpctl), NOT PulseAudio/ALSA directly
- Display server: Wayland via Hyprland, NOT X11 (though XWayland runs for some apps)
- Service manager: systemd (systemctl), NOT services.msc
- File paths: /home/user/.config/, NOT C:\Users\ or ~/Library/
- Keybinds: Hyprland bind syntax, NOT Windows shortcuts

## Costa Apps (GTK4/libadwaita)
- **Costa OS Settings** — central setup hub (monitors, AI, keys, updates). App ID: `com.costa.settings`
- **Keybind Configurator** — keyboard shortcuts + mouse button bindings. App ID: `com.costa.keybinds`
- **Music Widget** — MPRIS controller with queue, search, playlists, quality badge (GTK3). Class: `costa-music`
All Costa apps are pinned to the primary monitor and float centered.

## Music
- Click the now-playing text in the shell bar to open the music widget
- The widget can cold-start Strawberry and begin playback without opening the Strawberry window
- Search tab searches the Strawberry SQLite database — no need to open Strawberry's GUI
- Quality badge shows live stream format from PipeWire (e.g. "24bit / 96kHz")
- Strawberry runs hidden on special:music workspace — toggle visibility from the widget's eye icon

## Troubleshooting
- Check Hyprland errors: `hyprctl configerrors`
- Check logs: `journalctl --user -u <service> -f`
- GPU info: `source ~/.config/costa/gpu.conf && echo $GPU_NAME`
- Audio issues: `wpctl status` and `wpctl set-default <id>`
- Ollama not responding: `systemctl restart ollama`
- Model not loaded: check `$XDG_RUNTIME_DIR/costa/ollama-smart-model` and `ollama ps`
- App won't close: `hyprctl dispatch closewindow address:ADDR` or `kill PID`
- Hide app but keep running: move to special workspace (see Window Management above)
- Electron apps may need `--ozone-platform=wayland` or `=x11` flags for full functionality

## Gotchas & Pitfalls
- Hyprland `exec` doesn't support inline env vars (e.g. `VAR=val command`) — wrap in `bash -c`
- `xargs` breaks on apostrophes in filenames — always use `xargs -0`
- `pw-cat --target` flag is unreliable — use the default source instead
- PipeWire filter chains can silently intercept the default source — test recording after audio config changes
- NVMe device names can swap between boots — fstab uses UUIDs, never /dev/nvmeXnY
- Firefox in terminal spams Gdk-WARNING lines — these are harmless, ignore them
- Electron apps (VS Code, etc.) may need `--ozone-platform=wayland` or `=x1` flags
