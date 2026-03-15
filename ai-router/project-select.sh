#!/usr/bin/env bash
# Costa AI Project Selector — rofi integration for project switching
# Bind to a keybind or call from the AI router.
#
# Usage:
#   ./project-select.sh              # interactive rofi picker
#   ./project-select.sh "sonical"    # direct switch (no rofi)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Direct switch if argument provided
if [[ -n "$1" ]]; then
    python3 "$SCRIPT_DIR/project_switch.py" "$1"
    exit $?
fi

# Get project list
PROJECTS=$(python3 "$SCRIPT_DIR/project_switch.py" --list 2>/dev/null)

if [[ -z "$PROJECTS" ]]; then
    notify-send -u critical -a "Costa AI" "Project Switch" "No projects configured."
    exit 1
fi

# Format for rofi: just the project names (first word of each non-indented line)
CHOICES=$(echo "$PROJECTS" | grep -v "^  " | sed 's/ (.*//')

# Show rofi picker
SELECTED=$(echo "$CHOICES" | rofi -dmenu \
    -p "Switch to project" \
    -theme-str 'window { width: 400px; }' \
    -i \
    -no-custom)

if [[ -z "$SELECTED" ]]; then
    exit 0  # User cancelled
fi

# Switch to selected project
python3 "$SCRIPT_DIR/project_switch.py" "$SELECTED"
