#!/usr/bin/env bash
# Costa AI Screenshot Action — Hyprland keybind wrapper
# Bind to SUPER+SHIFT+S in hyprland.conf:
#   bind = $mainMod SHIFT, S, exec, ~/.config/costa/screenshot-ai.sh
# Or for Costa OS:
#   bind = $mainMod SHIFT, S, exec, /path/to/ai-router/screenshot-ai.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/screenshot_action.py"
