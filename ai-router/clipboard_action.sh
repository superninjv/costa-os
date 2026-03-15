#!/usr/bin/env bash
# Costa OS Clipboard Action Handler
#
# Called by clipboard_daemon.py when a user clicks a notification action.
# Usage: clipboard_action.sh <action_type> <content_file>
#
# Action types: error, url, code, path, json, command

set -euo pipefail

ACTION_TYPE="${1:-}"
CONTENT_FILE="${2:-}"

if [[ -z "$ACTION_TYPE" || -z "$CONTENT_FILE" || ! -f "$CONTENT_FILE" ]]; then
    notify-send "Costa Clipboard" "Error: missing action type or content file" --urgency=critical
    exit 1
fi

CONTENT="$(cat "$CONTENT_FILE")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COSTA_AI="${SCRIPT_DIR}/costa-ai"

case "$ACTION_TYPE" in
    error)
        # Pipe the error to costa-ai for explanation
        response=$(echo "$CONTENT" | python3 "$COSTA_AI" "explain this error and suggest a fix:")
        # Show the explanation in a dunst notification (long timeout)
        notify-send "Costa AI — Error Explanation" "$response" \
            --app-name="Costa AI" \
            --urgency=normal \
            --expire-time=30000
        # Also copy the explanation to clipboard for easy pasting
        echo "$response" | wl-copy
        ;;

    url)
        # Open the URL in the default browser
        xdg-open "$CONTENT" &>/dev/null &
        ;;

    code)
        # Pipe the code to costa-ai for analysis
        response=$(echo "$CONTENT" | python3 "$COSTA_AI" "explain this code concisely:")
        notify-send "Costa AI — Code Analysis" "$response" \
            --app-name="Costa AI" \
            --urgency=normal \
            --expire-time=30000
        echo "$response" | wl-copy
        ;;

    path)
        # Expand ~ and open the path
        expanded="${CONTENT/#\~/$HOME}"
        if [[ -d "$expanded" ]]; then
            # Open directory in file manager
            if command -v nautilus &>/dev/null; then
                nautilus "$expanded" &>/dev/null &
            elif command -v thunar &>/dev/null; then
                thunar "$expanded" &>/dev/null &
            else
                # Fall back to terminal
                ghostty -e bash -c "cd '$expanded' && exec zsh" &>/dev/null &
            fi
        elif [[ -f "$expanded" ]]; then
            # Open file in editor
            code "$expanded" &>/dev/null &
        else
            notify-send "Costa Clipboard" "Path does not exist: $expanded" --urgency=normal
        fi
        ;;

    json)
        # Format JSON with jq and copy back to clipboard
        formatted=$(echo "$CONTENT" | jq . 2>/dev/null)
        if [[ $? -eq 0 && -n "$formatted" ]]; then
            echo "$formatted" | wl-copy
            notify-send "Costa Clipboard" "JSON formatted and copied back" \
                --app-name="Costa Clipboard" \
                --urgency=low \
                --expire-time=3000
        else
            notify-send "Costa Clipboard" "Failed to format JSON" \
                --urgency=normal
        fi
        ;;

    command)
        # Open a terminal and run the command
        # Extract just the first line (the actual command)
        cmd_line=$(head -1 <<< "$CONTENT")
        ghostty -e bash -c "echo '$ $cmd_line'; echo; $cmd_line; echo; echo 'Press Enter to close...'; read" &>/dev/null &
        ;;

    *)
        notify-send "Costa Clipboard" "Unknown action type: $ACTION_TYPE" --urgency=normal
        ;;
esac

# Clean up the content file
rm -f "$CONTENT_FILE" 2>/dev/null || true
