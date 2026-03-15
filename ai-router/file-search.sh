#!/usr/bin/env bash
# Costa OS Natural Language File Search — Rofi integration
#
# Opens a rofi prompt for natural language file queries.
# Results are shown as a selectable list; selecting one opens it
# in VS Code (or $EDITOR).
#
# Usage:
#   ./file-search.sh              # interactive rofi mode
#   ./file-search.sh "query"      # direct query mode (still shows rofi for results)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEARCH_SCRIPT="$SCRIPT_DIR/file_search.py"
EDITOR_CMD="${VISUAL:-${EDITOR:-code}}"

# Costa theme colors for rofi
ROFI_THEME='
* {
    bg: #1a1f2e;
    fg: #c8d0e0;
    accent: #5b9ea6;
    urgent: #c97d60;
    selected-bg: #2a3347;
    border-color: #5b9ea6;
}
window {
    width: 50%;
    border: 2px;
    border-color: @border-color;
    background-color: @bg;
}
inputbar {
    padding: 8px 12px;
    background-color: @bg;
    text-color: @fg;
}
prompt {
    text-color: @accent;
}
entry {
    text-color: @fg;
    placeholder: "Describe the file you are looking for...";
    placeholder-color: #5a6378;
}
listview {
    lines: 10;
    padding: 4px 0;
    background-color: @bg;
}
element {
    padding: 6px 12px;
    background-color: @bg;
    text-color: @fg;
}
element selected {
    background-color: @selected-bg;
    text-color: @accent;
}
element-text {
    text-color: inherit;
}
'

run_search() {
    local query="$1"
    if [[ -z "$query" ]]; then
        return
    fi

    # Run the Python search
    local raw_results
    raw_results=$(python3 "$SEARCH_SCRIPT" "$query" 2>/dev/null)

    if [[ -z "$raw_results" || "$raw_results" == "No matching files found." ]]; then
        echo "No matching files found."
        return
    fi

    echo "$raw_results"
}

extract_path() {
    # Extract the file path from a result line like:
    #  1. ~/projects/foo/bar.rs  (content, score: 25)
    local line="$1"
    local path
    path=$(echo "$line" | sed 's/^[[:space:]]*[0-9]*\.[[:space:]]*//' | sed 's/[[:space:]]*(.*$//')
    # Expand ~ to $HOME
    path="${path/#\~/$HOME}"
    echo "$path"
}

main() {
    local initial_query="$1"

    if [[ -n "$initial_query" ]]; then
        # Direct query mode — search and show results in rofi
        local results
        results=$(run_search "$initial_query")

        if [[ "$results" == "No matching files found." ]]; then
            notify-send "Costa File Search" "No files found for: $initial_query" 2>/dev/null
            return 1
        fi

        local selected
        selected=$(echo "$results" | rofi -dmenu -i \
            -p "Results" \
            -theme-str "$ROFI_THEME" \
            -mesg "Query: $initial_query")

        if [[ -n "$selected" ]]; then
            local filepath
            filepath=$(extract_path "$selected")
            if [[ -f "$filepath" ]]; then
                # Record the open for frecency tracking
                python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from file_search import record_file_open
record_file_open('$filepath')
" 2>/dev/null
                $EDITOR_CMD "$filepath" &
            else
                notify-send "Costa File Search" "File not found: $filepath" 2>/dev/null
            fi
        fi
    else
        # Interactive mode — get query from rofi, then search
        local query
        query=$(echo "" | rofi -dmenu -i \
            -p "  Search" \
            -theme-str "$ROFI_THEME" \
            -mesg "Describe the file (e.g. 'rust file with websocket code from yesterday')")

        if [[ -n "$query" ]]; then
            # Re-run with the query
            main "$query"
        fi
    fi
}

main "$@"
