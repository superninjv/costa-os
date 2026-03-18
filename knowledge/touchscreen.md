---
l0: "Touchscreen support: on-screen keyboard, multi-touch gestures, hyprgrass plugin, squeekboard, toggle on/off"
l1_sections: ["Overview", "On-Screen Keyboard", "Touch Gestures", "Configuration", "Toggle Touchscreen", "Troubleshooting"]
tags: [touchscreen, touch, gestures, hyprgrass, squeekboard, keyboard, on-screen, swipe, pinch, input, tablet, convertible]
---

# Touchscreen Support

## Overview
Costa OS auto-detects touchscreens during install and configures:
- **squeekboard** — on-screen keyboard that appears automatically in text fields
- **hyprgrass** — Hyprland plugin for multi-touch gestures (swipe, pinch, long press)
- **libinput** — kernel-level touch input handling (built into Hyprland)

If no touchscreen is detected, these components are not installed or configured.

## On-Screen Keyboard

### How do I get an on-screen keyboard?
Squeekboard starts automatically when a touchscreen is detected. It appears when you tap a text input field and hides when you tap outside.

### How do I manually show/hide the keyboard?
```bash
# Show keyboard
busctl call --user sm.puri.OSK0 /sm/puri/OSK0 sm.puri.OSK0 SetVisible b true

# Hide keyboard
busctl call --user sm.puri.OSK0 /sm/puri/OSK0 sm.puri.OSK0 SetVisible b false
```

### How do I restart squeekboard if it crashes?
```bash
killall squeekboard
squeekboard &disown
```

### Where does squeekboard appear?
Squeekboard floats at the bottom of the screen. Hyprland window rules pin it there:
- Always floats (never tiled)
- Pinned to bottom edge
- Appears on all workspaces
- Does not steal focus

## Touch Gestures

### What gestures are available?
All gestures use the **hyprgrass** plugin:

| Gesture | Fingers | Action |
|---------|---------|--------|
| Swipe up | 3 | Open app launcher (rofi) |
| Swipe down | 3 | Close focused window |
| Swipe left | 3 | Next workspace |
| Swipe right | 3 | Previous workspace |
| Swipe up | 4 | Toggle fullscreen |
| Swipe down | 4 | Toggle floating |
| Long press | 2 | Move window (drag after press) |

### How do I remember the gestures?
- **3 fingers** = workspace and window management (the basics)
- **4 fingers** = window state changes (fullscreen, floating)
- **2-finger long press** = grab and move

## Configuration

### Where is the touch config?
`~/.config/hypr/touch.conf` — sourced automatically from `hyprland.conf`.

### How do I customize gestures?
Edit `~/.config/hypr/touch.conf`. Gesture syntax:
```ini
# hyprgrass gesture binds
plugin {
    touch_gestures {
        sensitivity = 4.0

        hyprgrass-bind = , swipe:3:u, exec, rofi -show drun
        hyprgrass-bind = , swipe:3:d, killactive
        hyprgrass-bind = , swipe:3:l, workspace, +1
        hyprgrass-bind = , swipe:3:r, workspace, -1
        hyprgrass-bind = , swipe:4:u, fullscreen, 0
        hyprgrass-bind = , swipe:4:d, togglefloating
        hyprgrass-bindm = , longpress:2, movewindow
    }
}
```
After editing, reload: `hyprctl reload`

### How do I adjust gesture sensitivity?
In `~/.config/hypr/touch.conf`, change the `sensitivity` value:
- Higher value (e.g., 6.0) = need to swipe further to trigger
- Lower value (e.g., 2.0) = triggers more easily
- Default: 4.0

### How do I handle a rotated touchscreen?
If your touchscreen is on a rotated monitor (like a portrait display), set the transform to match:
```ini
# In touch.conf
input:touchdevice {
    transform = 1    # 0=none, 1=90°, 2=180°, 3=270°
    output = HDMI-A-1  # bind to specific monitor
}
```

## Toggle Touchscreen

### How do I turn touchscreen on or off?
**Option 1: Settings Hub**
Settings Hub → Input → Touchscreen → toggle switch

**Option 2: Terminal**
```bash
# Disable touchscreen
hyprctl keyword input:touchdevice:enabled false

# Enable touchscreen
hyprctl keyword input:touchdevice:enabled true
```

**Option 3: Keybind**
No default keybind is set, but you can add one to `hyprland.conf`:
```ini
bind = SUPER, F10, exec, hyprctl keyword input:touchdevice:enabled $(hyprctl getoption input:touchdevice:enabled -j | jq '.int == 0')
```

### What happens when I disable touchscreen?
- Touch input is ignored
- Squeekboard stops appearing
- Hyprgrass gestures are inactive
- Everything else works normally (mouse, keyboard, stylus)

## Troubleshooting

### Touch input not working
```bash
# Check if touchscreen is detected
libinput list-devices | grep -i touch

# Check if hyprgrass plugin is loaded
hyprctl plugin list

# Check if touch is enabled
hyprctl getoption input:touchdevice:enabled
```

### Gestures not triggering
```bash
# Verify hyprgrass is loaded
hyprctl plugin list | grep hyprgrass

# If not loaded, re-enable it
hyprctl plugin load /usr/lib/hyprland/plugins/hyprgrass.so
```

### Squeekboard not appearing
```bash
# Check if it's running
pgrep squeekboard

# Start it
squeekboard &disown

# Check for errors
journalctl --user -u squeekboard -n 20
```

### Touch coordinates are wrong on a rotated display
Set the `transform` value in `~/.config/hypr/touch.conf` to match your monitor's rotation. See the "How do I handle a rotated touchscreen?" section above.

### Touch works but is laggy
Check if compositing is keeping up:
```bash
# Monitor frame times
hyprctl monitors -j | jq '.[].currentFormat'
```
Touch latency is typically <16ms. If laggy, check GPU load with `btop` or `radeontop`.
