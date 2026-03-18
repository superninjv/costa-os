---
l0: "Keybind configuration: GUI configurator, CLI tool, Hyprland bind syntax, mouse button mapping"
l1_sections: ["Keybind Configurator GUI", "CLI Tool", "Hyprland Bind Syntax", "Mouse Buttons", "Adding Keybinds"]
tags: [keybind, shortcut, hotkey, bind, mouse, button, remap, gui, configurator, hyprland]
---

# Costa OS Keybinds

## Keybind Configurator GUI
Open the graphical keybind & mouse configurator:
- Click the 󰌌 icon in waybar (left-click toggles open/close)
- Or run: `costa-keybinds-gui`

The GUI has two tabs:
- **Keyboard** — all keybinds grouped by category, searchable, with edit/add/delete
- **Mouse** — auto-discovers all connected mice, shows buttons, "Press to Detect" identifies buttons, configure bindings per-button

To add a keybind: click the + button in the header bar.
To edit: click the pencil icon on any row.
To delete: click the trash icon.

When recording a shortcut, Hyprland may intercept bound keys before the GUI sees them.
Use the "Or type manually" field as a fallback (e.g. type `SUPER SHIFT, K`).

## CLI Tool
```bash
costa-keybinds list                    # show all keybinds
costa-keybinds list --filter volume    # filter by keyword
costa-keybinds add "SUPER" "F1" "exec" "firefox"    # add new
costa-keybinds remove "SUPER" "F1"     # remove
costa-keybinds mouse                   # show mouse button mappings
costa-keybinds mouse enable-all        # make all mouse buttons bindable
costa-keybinds mouse detect            # identify a button by pressing it
```

Or via voice: "show my keybinds", "bind super+F5 to open firefox", "what mouse buttons do I have"

## Hyprland Bind Syntax
```
bind = MODS, KEY, dispatcher, args
```
- `bind` — normal bind
- `binde` — repeats while held (for resize/volume)
- `bindm` — mouse bind (for drag operations)
- `bindl` — works even when locked
- `bindr` — triggers on key release
- `bindn` — no inhibit (won't prevent other binds)

Common dispatchers:
- `exec` — run a command
- `killactive` — close focused window
- `workspace` — switch workspace
- `movetoworkspace` — move window to workspace
- `movefocus` — move focus (l/r/u/d)
- `movewindow` — move window (l/r/u/d)
- `resizeactive` — resize window (dx dy)
- `fullscreen` — toggle fullscreen
- `togglefloating` — toggle float/tile
- `togglesplit` — toggle horizontal/vertical split

## Mouse Buttons
Any connected mouse is auto-discovered (no special driver needed).
If you have a gaming mouse with extra buttons:
```bash
costa-keybinds mouse enable-all    # unlock hardware buttons for binding (needs ratbagctl)
```
Then bind them: `bind = , mouse:275, exec, playerctl play-pause`

Mouse button codes:
- 272 = left, 273 = right, 274 = middle
- 275 = back/side, 276 = forward
- 277-279 = extra buttons (DPI, G7, G8 on Logitech mice)

To identify an unknown button: open the GUI → Mouse tab → "Start Detection" → press the button.

If `ratbagctl` is installed (libratbag package), the GUI also shows hardware remapping options
(DPI shift, resolution switching). Without ratbagctl, Hyprland bindings still work for any
button that sends an evdev event.

## Adding Keybinds
Three ways:
1. **GUI**: costa-keybinds-gui → click + → record shortcut or type manually → pick dispatcher → save
2. **CLI**: `costa-keybinds add "SUPER" "F5" "exec" "costa-ai 'what time is it'"`
3. **Manual**: edit ~/.config/hypr/hyprland.conf, then `hyprctl reload`

The GUI and CLI both write to hyprland.conf and reload automatically.
