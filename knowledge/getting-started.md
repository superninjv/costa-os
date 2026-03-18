---
l0: "New user guide: keybinds, navigation, app launching, config locations, getting help"
l1_sections: ["Keybinds Cheat Sheet", "Opening Apps", "Workspaces & Monitors", "Where Things Are", "Getting Help"]
tags: [getting-started, keybinds, navigation, workspaces, help, tutorial, beginner]
---
# Getting Started with Costa OS

## Keybinds Cheat Sheet

### Essential
| Key | Action |
|-----|--------|
| `SUPER+Enter` | Open terminal (Ghostty) |
| `SUPER+Q` | Close focused window |
| `SUPER+D` | App launcher (Rofi) |
| `SUPER+F` | Toggle fullscreen |
| `SUPER+V` | Toggle floating window |

### Focus & Movement (vim-style)
| Key | Action |
|-----|--------|
| `SUPER+H/J/K/L` | Move focus left/down/up/right |
| `SUPER+SHIFT+H/J/K/L` | Move window left/down/up/right |

### Workspaces
| Key | Action |
|-----|--------|
| `SUPER+1` through `SUPER+6` | Switch to workspace 1–6 |
| `SUPER+SHIFT+1` through `SUPER+SHIFT+6` | Move window to workspace 1–6 |

### Voice & AI
| Key | Action |
|-----|--------|
| `SUPER+ALT+V` | Voice command (Claude mode — AI responds) |
| `SUPER+ALT+B` | Voice command (Type mode — types into window) |

## Opening Apps

Launch the app launcher:
```
SUPER+D
```
Start typing the app name, press Enter to launch. Arrow keys or Tab to navigate results.

Common apps from terminal:
```sh
ghostty          # terminal
code             # VS Code
firefox          # browser
spotify          # music (via spotify-launcher)
```

## Workspaces & Monitors

Costa OS assigns workspaces per monitor (auto-detected at first boot):

| Workspace | Monitor | Description |
|-----------|---------|-------------|
| 1–4 | Primary (highest res/refresh) | Main workspaces |
| 5–6 | Secondary monitors (if present) | Reference, media, chat |
| 7 | Virtual headless (if enabled) | AI navigation |

Switch workspaces: `SUPER+<number>`
Move a window there: `SUPER+SHIFT+<number>`

## Where Things Are

| Path | Contents |
|------|----------|
| `~/.config/hypr/hyprland.conf` | Hyprland config (keybinds, monitors, rules) |
| `~/.config/waybar/` | Waybar panels (config.jsonc, style.css) |
| `~/.config/costa/` | Costa AI config, knowledge bases, workflows |
| `~/.config/rofi/` | App launcher theme and power menu |
| `~/.config/dunst/dunstrc` | Notification daemon config |
| `~/.config/ghostty/config` | Terminal config |

## Getting Help

Ask the AI assistant anything about the system:
```sh
costa-ai "how do I change my wallpaper"
```

Or use voice: hold `SUPER+ALT+V`, speak your question, release.

Or click the Costa icon (center of waybar) and type your question.

The AI has full knowledge of your system config, installed packages, and running services.
