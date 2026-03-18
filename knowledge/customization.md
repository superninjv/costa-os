---
l0: "Desktop customization: Costa theme palette, wallpaper, window rules, Waybar templates, monitor config"
l1_sections: ["Theme — Costa Palette", "Changing Wallpaper", "Adding Applications", "Window Rules", "Waybar", "Monitor Configuration", "Changing Default Apps"]
tags: [theme, color, wallpaper, font, opacity, waybar, template, bar, monitor, customization, mpvpaper]
---

# Costa OS Customization

## Theme — Costa Palette
The Costa theme uses a Mediterranean coastal dark palette:
- Base: #1b1d2b (dark navy)
- Surface: #252836
- Text: #d4cfc4 (warm white)
- Sea: #5b94a8 (teal blue — primary accent)
- Terracotta: #c07a56 (warm orange — secondary accent)
- Foam: #7eb5b0 (light teal)
- Sand: #c9a96e (golden)
- Olive: #8b9968 (muted green)
- Lavender: #9884b8 (purple)
- Rose: #b87272 (muted red — errors/urgent)

Colors are defined in:
- Hyprland: $sea, $foam, $terracotta, etc. in hyprland.conf
- Waybar: @define-color in style.css
- Rofi: defined in config.rasi
- Ghostty: palette entries in ghostty/config
- GTK apps (libadwaita): overridden via CSS in Costa apps (e.g. keybinds GUI)

## Changing Wallpaper
Costa OS uses mpvpaper for animated wallpapers:
```bash
# Set a video wallpaper
mpvpaper '*' /path/to/video.mp4 --fork

# Set a static wallpaper
swww img /path/to/image.jpg
```
Edit ~/.config/costa/scripts/wallpaper.sh to set the default.

### Wallpaper Engine (optional)
- Install: `yay -S linux-wallpaperengine-git`
- Requires Steam with Wallpaper Engine
- Set wallpaper: edit `~/.config/costa/config.json` → set `wallpaper` to the scene's `project.json` path
- Or run directly: `linux-wallpaperengine --screen-root '*' /path/to/scene/`
- Video and 2D scenes work well; complex 3D scenes may crash

## Adding Applications
```bash
# Official repos
sudo pacman -S <package>

# AUR (if yay is installed)
yay -S <package>
```

To add an app to autostart, add to ~/.config/hypr/hyprland.conf:
```
exec-once = <command>
```

## Window Rules
Make specific apps float, set size, set opacity:
```
windowrule = match:class ^(app-class)$, float on, size 800 600, center on
```
Find an app's class: `hyprctl clients -j | jq '.[].class'`

## Waybar

### Bar Templates
Waybar config is generated from templates in `configs/waybar/templates/`:
- **main-bar** — full-featured bar for the primary monitor (all modules, tray, costa-ai widget, claude)
- **performance-bar** — system monitoring (GPU, CPU, temps, memory, disk I/O) for a secondary monitor
- **minimal-bar** — lightweight (workspaces + weather + clock) for additional secondaries
- **taskbar** — bottom taskbar showing all windows, paired with the performance bar monitor
- **claude-screen-bar** — for the headless virtual monitor Claude uses for AI navigation

### Headless Monitor Preview
Click the 󰍹 icon in waybar (next to Claude launcher) to toggle a live preview window showing Claude's virtual headless monitor. The preview auto-updates every 2 seconds and shows what windows Claude has open. Only appears when AI navigation is enabled (headless monitor exists).

### Regenerating Waybar Config
When monitors change or after first boot:
```bash
# Auto-detect monitors and generate config
~/.config/costa/scripts/generate-waybar-config.sh

# Preview without writing
~/.config/costa/scripts/generate-waybar-config.sh --dry-run

# Manual monitor assignment
~/.config/costa/scripts/generate-waybar-config.sh --primary DP-1 --perf HDMI-A-1 --minimal HDMI-A-2
```

The generator:
- Auto-detects all monitors (physical + headless) via `hyprctl monitors -j`
- Picks primary by highest refresh rate, then resolution
- Auto-discovers GPU/CPU hardware sensor paths for the performance bar
- Assigns workspaces: 1-4 on primary, 5-6 on first secondary, 7+ on others
- Single-monitor setups get just the main bar with all workspaces

### Adding/Modifying Waybar Modules
Edit the template files in `configs/waybar/templates/`, then regenerate.
Each template is a JSONC file (JSON with // comments) using placeholders:
- `__OUTPUT__` — replaced with the monitor name
- `__PERSISTENT_WORKSPACES__` — replaced with workspace assignments
- `__TIMEZONE__` — replaced with system timezone
- `__GPU_BUSY_PATH__`, `__CPU_HWMON_PATH__`, `__GPU_HWMON_PATH__` — hardware sensor paths

Style modules in ~/.config/waybar/style.css.

## Monitor Configuration
Monitors are auto-detected at first boot. Edit manually in ~/.config/hypr/hyprland.conf:
```
monitor = NAME, WIDTHxHEIGHT@RATE, POSITION, SCALE
```
After changing monitors, regenerate the waybar config.

## Changing Default Apps
Edit the variables at the top of ~/.config/hypr/hyprland.conf:
```
$terminal = ghostty
$fileManager = thunar
$menu = rofi -show drun
$browser = firefox
```
