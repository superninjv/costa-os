#!/bin/bash
# Output JSON for static waybar modules with tooltip support.
# Usage: static-module.sh "icon_text" "tooltip_text"
# Use literal \n in tooltip_text for newlines.
# Waybar custom modules need return-type:json + exec for tooltips to work.

TEXT="${1:-·}"
TOOLTIP="${2:-}"

# Escape backslashes and quotes for JSON, but preserve \n as JSON newline
TEXT="${TEXT//\\/\\\\}"
TEXT="${TEXT//\"/\\\"}"
TOOLTIP="${TOOLTIP//\\/\\\\}"
TOOLTIP="${TOOLTIP//\"/\\\"}"
# Restore \\n back to \n for JSON newline
TOOLTIP="${TOOLTIP//\\\\n/\\n}"

printf '{"text": "%s", "tooltip": "%s"}\n' "$TEXT" "$TOOLTIP"
