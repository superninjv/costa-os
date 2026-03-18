---
l0: "Configuration locations, Costa theme colors, settings app, wallpaper, multi-monitor waybar setup"
l1_sections: ["Config Locations", "Costa OS Settings App", "Re-running Setup", "Adding API Keys After Install", "Costa Theme Colors", "Waybar", "Ghostty Terminal", "Rofi Launcher", "Dunst Notifications", "Wallpaper", "Multi-Monitor"]
tags: [config, setup, theme, colors, settings, api-keys, waybar, wallpaper, ghostty, rofi, dunst]
---
# Costa OS Setup & Configuration

## Config Locations
- Main config: ~/.config/costa/config.json
- AI system prompt: ~/.config/costa/system-ai.md
- API keys: ~/.config/costa/env (mode 600)
- GPU detection: ~/.config/costa/gpu.conf
- Knowledge bases: ~/.config/costa/knowledge/
- Hyprland: ~/.config/hypr/hyprland.conf
- Monitor overrides: ~/.config/hypr/monitors.conf
- Waybar: ~/.config/waybar/config and style.css
- Ghostty: ~/.config/ghostty/config
- Rofi: ~/.config/rofi/config.rasi
- Dunst: ~/.config/dunst/dunstrc
- Howdy (face auth): /lib/security/howdy/config.ini
- Touch config: ~/.config/hypr/touch.conf

## Costa OS Settings App
Open from any of these:
- Rofi/app launcher: search "Costa OS Settings"
- Waybar: click the ⚙ gear icon (next to power button)
- Terminal: `costa-settings`

The settings app provides buttons for:
- Face authentication enrollment and testing (if IR camera detected)
- Touchscreen configuration (if touchscreen detected)
- Monitor detection and waybar regeneration
- Wallpaper picker (images + video)
- Keybinds GUI launcher
- Ollama model management (list/pull)
- API key entry (Anthropic/OpenAI)
- Voice assistant status
- GitHub CLI login
- SSH key management
- System updates
- Dotfiles sync (chezmoi)
- Re-run first boot

## Installer
The ISO boots into a GTK4 graphical installer (costa-install-gui). No CLI needed.
Supports three partition modes: erase entire disk, install alongside existing OS (dual-boot with resize), or manual partition selection.
Password is set securely via printf pipe to chpasswd (no shell interpolation issues).

## Agent Pool
Specialized background agents for infrastructure tasks:
```bash
costa-agents list                           # Show all agents
costa-agents dispatch sysadmin "check disk" # Background task
costa-agents run monitor "check server"     # Wait for result
costa-agents status                         # Active tasks
costa-agents log deployer                   # View logs
```
Agents: sysadmin, architect, janitor, builder, deployer, monitor.
Definitions in ~/.config/costa/agents/*.yaml.
Resource queues prevent overload (e.g., only one SSH to a remote server at a time).

## Re-running Setup
To re-run the first-boot wizard:
```bash
costa-settings   # click "Re-run First Boot" under System
# Or from terminal:
~/.config/hypr/first-boot.sh
```

## Adding API Keys After Install
Easiest way: `costa-settings` → AI Assistant → API Keys

Or edit ~/.config/costa/env manually:
```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```
Then reload: `source ~/.config/costa/env`

## Costa Theme Colors
The "Costa" palette is a Mediterranean coastal dark theme:
- Base background: #1b1d2b
- Surface: #252836
- Text: #d4cfc4
- Sea (primary): #5b94a8
- Terracotta (warm accent): #c07a56
- Foam (light accent): #7eb5b0
- Sand (gold): #c9a96e
- Olive (green): #8b9968
- Lavender (purple): #9884b8
- Rose (error/urgent): #b87272

## Waybar
Restart: `killall waybar; waybar &disown`
Config: ~/.config/waybar/config (JSON — modules and layout)
Style: ~/.config/waybar/style.css (CSS — colors and sizing)

## Ghostty Terminal
Config: ~/.config/ghostty/config
Reload: close and reopen terminal (no hot-reload)

## Rofi Launcher
Config: ~/.config/rofi/config.rasi
Test: `rofi -show drun`

## Dunst Notifications
Config: ~/.config/dunst/dunstrc
Restart: `killall dunst; dunst &disown`
Test: `notify-send "Test" "Hello from Costa OS"`
Notifications always appear on the primary monitor (monitor=0, follow=none).

## Wallpaper
Costa uses mpvpaper for animated wallpapers or swww for static.
Change via `costa-settings` → Display → Wallpaper, or edit ~/.config/costa/scripts/wallpaper.sh.

## Multi-Monitor
All floating panels, notifications, and settings dialogs are pinned to the primary monitor
via Hyprland window rules (using the primary monitor name). They never pop up on the wrong screen.

Waybar configs are auto-generated per monitor layout:
```bash
# Regenerate after changing monitors
costa-settings   # click "Waybar Layout" under Display
# Or from terminal:
~/.config/costa/scripts/generate-waybar-config.sh
```
