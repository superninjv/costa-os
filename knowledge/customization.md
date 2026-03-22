---
l0: "Desktop customization: Costa theme palette, wallpaper, window rules, AGS shell bar, monitor config"
l1_sections: ["Theme — Costa Palette", "Changing Wallpaper", "Adding Applications", "Window Rules", "AGS Shell", "Monitor Configuration", "Changing Default Apps"]
tags: [theme, color, wallpaper, font, opacity, ags, shell-bar, bar, monitor, customization, mpvpaper]
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
- AGS shell: CSS variables in ~/.config/ags/style.css
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

## AGS Shell

### Shell Bar Layout
The AGS shell (Aylur's GTK Shell v3) provides the desktop bar with these sections:
- **Left** — workspaces, active window title
- **Center** — Costa AI widget, clock, media controls
- **Right** — system tray, system monitors (CPU, GPU, temps), notifications, quick settings

### Multi-Monitor Support
AGS auto-detects all connected monitors (physical + headless) via Hyprland events. No manual config regeneration is needed — the shell adapts automatically when monitors are added or removed.

### Headless Monitor Preview
Click the 󰍹 icon in the shell bar (next to Claude launcher) to toggle a live preview window showing Claude's virtual headless monitor. The preview auto-updates every 2 seconds and shows what windows Claude has open. Only appears when AI navigation is enabled (headless monitor exists).

### Restarting the Shell Bar
```bash
ags quit; ags run -d ~/.config/ags
```

### Customizing the Shell Bar
Edit the TypeScript source in `~/.config/ags/`:
- Widget definitions and layout in TypeScript modules
- Styling in `style.css` using GTK CSS
- Costa theme colors are defined as CSS variables

Shell bar source for the ISO lives in `shell/` in the Costa OS repo.

## Monitor Configuration
Monitors are auto-detected at first boot. Edit manually in ~/.config/hypr/hyprland.conf:
```
monitor = NAME, WIDTHxHEIGHT@RATE, POSITION, SCALE
```
After changing monitors, the AGS shell bar adapts automatically.

## Changing Default Apps
Edit the variables at the top of ~/.config/hypr/hyprland.conf:
```
$terminal = ghostty
$fileManager = thunar
$menu = rofi -show drun
$browser = firefox
```
