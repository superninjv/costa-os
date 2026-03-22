---
l0: "Costa Settings Hub: centralized GUI for display, security, input, AI, development, and system configuration"
l1_sections: ["How to Open Settings Hub", "Display Settings", "Security Settings", "Input Settings", "AI Settings", "Development Settings", "System Settings", "Status Indicators"]
tags: [settings, configuration, display, security, ai, ollama, chezmoi, github, ssh, monitors, wallpaper, face-auth, touchscreen, keybinds, updates, versioning, costa-update]
---

# Costa Settings Hub

## How to Open Settings Hub
- Click the gear icon (󰒓) in the shell bar
- Or run from terminal: `costa-settings`
- Or voice command: "open settings"
- Keyboard shortcut: `SUPER+I`

The Settings Hub is a GTK4 app organized into tabbed sections. Each section shows a green checkmark (✓) when fully configured and a yellow warning (⚠) when setup is incomplete.

## Display Settings

### How do I detect and configure monitors?
```bash
# Auto-detect monitors and apply layout
costa-settings display detect

# Or from CLI
hyprctl monitors all
```
The Settings Hub scans connected monitors and shows a visual layout editor. Drag monitors to arrange them, set resolution/refresh rate, and apply.

### How do I change my wallpaper?
- Settings Hub → Display → Wallpaper
- Browse local files or paste a Wallpaper Engine workshop URL
- Supported: static images (png/jpg), videos (mp4/webm via mpvpaper), Wallpaper Engine scenes
- Per-monitor wallpapers supported — click a monitor in the layout to set individually
- CLI: edit `~/.config/hypr/wallpaper.sh` and restart it: `killall mpvpaper; bash ~/.config/hypr/wallpaper.sh &disown`

### How do I apply the shell bar to new monitors?
- The AGS shell auto-detects connected monitors and adapts automatically
- No manual config regeneration needed — monitors are detected via Hyprland events
- Restart the shell bar if needed: `ags quit; ags run -d ~/.config/ags`

## Security Settings

### How do I set up face authentication?
- Settings Hub → Security → Face Authentication → "Enroll Face"
- This runs `sudo howdy add` in a terminal window
- Position your face in front of the IR camera when prompted
- Enroll multiple angles for better recognition
- See `face-auth.md` for full details

### How do I manage enrolled faces?
```bash
# List all enrolled face models
sudo howdy list

# Remove a specific model
sudo howdy remove <id>

# Test recognition
sudo howdy test
```

## Input Settings

### How do I toggle touchscreen support?
- Settings Hub → Input → Touchscreen → toggle on/off
- When off, touch input is disabled via `hyprctl keyword input:touchdevice:enabled false`
- When on, squeekboard (on-screen keyboard) and hyprgrass (gestures) activate
- See `touchscreen.md` for gesture reference

### How do I edit keybinds?
- Settings Hub → Input → Keybinds → opens visual keybind editor
- Shows all current bindings from `~/.config/hypr/hyprland.conf`
- Click a binding to reassign, or add new ones
- Changes are written to hyprland.conf and applied with `hyprctl reload`

## AI Settings

### How do I manage Ollama models?
- Settings Hub → AI → Models
- Shows installed models with size, quantization, and last-used date
- Pull new model: click "Add Model" and enter name (e.g., `qwen2.5:14b`)
- Delete model: click the trash icon next to it
- CLI equivalent:
```bash
ollama list              # see installed models
ollama pull qwen2.5:14b  # download a model
ollama rm qwen2.5:3b     # remove a model
```

### How do I set the AI tier?
- Settings Hub → AI → Tier
- Options: Local Only, Local + Cloud Fallback (default), Cloud Primary
- "Local Only" never calls Claude API — fully offline
- "Local + Cloud Fallback" uses Ollama first, escalates to Claude when local says "I don't know"
- "Cloud Primary" routes everything through Claude API (fastest, costs money)
- Config written to: `~/.config/costa/ai-config.yaml`

### How do I enter my Claude API key?
- Settings Hub → AI → Claude API → paste your key
- Or set manually: `echo "YOUR_KEY" > ~/.config/costa/claude-api-key`
- Supports both API keys and Claude Pro/Max plan tokens
- Key is stored locally, never transmitted except to Anthropic's API

## Development Settings

### How do I authenticate GitHub CLI?
- Settings Hub → Development → GitHub → "Authenticate"
- Runs `gh auth login` interactively in a terminal
- Or from CLI: `gh auth login --web`
- Status check: `gh auth status`

### How do I set up SSH keys?
- Settings Hub → Development → SSH → "Generate Key"
- Creates `~/.ssh/id_ed25519` if none exists
- Offers to add the public key to GitHub automatically via `gh ssh-key add`
- CLI:
```bash
ssh-keygen -t ed25519 -C "your@email.com"
gh ssh-key add ~/.ssh/id_ed25519.pub --title "Costa OS"
```

## System Settings

### How do I update Costa OS?
- Settings Hub → System → "Costa OS Update"
- Or run from terminal: `costa-update`
- Shows current version and checks for updates
- Updates Costa layer (ai-router, configs, knowledge) via git
- Updates system packages via pacman/yay
- Claude reviews changes and fixes breakage automatically
- Fallback: local Ollama model, or manual checklist if no AI available

### How do I check my version?
```bash
costa-update --version    # prints current version
costa-update --check      # checks for updates without applying
```

### How do I sync my dotfiles?
- Settings Hub → System → Dotfiles → "Sync Now"
- Runs chezmoi to push current config to your dotfiles repo
- CLI:
```bash
cd ~/.local/share/chezmoi && chezmoi re-add && git add -A && git commit -m "sync" && git push
```

### How do I re-run first-boot setup?
- Settings Hub → System → "Re-run First Boot"
- Launches the installer wizard in reconfigure mode
- Safe to run — skips steps already completed, re-detects hardware
- CLI: `costa-firstboot --reconfigure`

## Status Indicators
Each section in Settings Hub shows its state:
- **Green ✓** — fully configured and working
- **Yellow ⚠** — partially configured or optional step skipped
- **Red ✗** — required setup not completed (e.g., no AI models installed)
- **Gray ○** — not applicable (e.g., touchscreen on a desktop without one)
