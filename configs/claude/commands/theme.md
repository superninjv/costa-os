Run a Costa OS theme customization helper.

Follow these steps:

1. Read the customization knowledge file via MCP resource `costa://knowledge/customization` to understand the Costa theme system and available options.

2. Read the current theme color variables from `~/.config/hypr/hyprland.conf` to see what is currently set.

3. Read the current Waybar stylesheet from `~/.config/waybar/style.css` to see the active color values.

4. Present the current theme colors to the user and ask what they want to change (e.g., accent color, background opacity, specific component colors).

5. Once the user specifies changes, apply them to all relevant config files:
   - `~/.config/hypr/hyprland.conf` — border colors, window decoration colors
   - `~/.config/waybar/style.css` — bar colors, module styling
   - `~/.config/dunst/dunstrc` — notification colors
   - `~/.config/rofi/config.rasi` — launcher colors
   - `~/.config/ghostty/config` — terminal colors

6. Reload all affected components:
   - `hyprctl reload` for Hyprland
   - `killall waybar; waybar &disown` for Waybar
   - `killall dunst; dunst &disown` for Dunst

7. Verify no config errors with `hyprctl configerrors`.

Use the costa-system MCP tools where available. Read relevant knowledge files via MCP resources before making changes.
