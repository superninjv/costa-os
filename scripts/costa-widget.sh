#!/bin/bash
# Launch a Costa GTK widget by name.
# Resolves the widget location automatically — no hardcoded paths needed.
# Usage: costa-widget <name>        (e.g. costa-widget music-widget)
#        costa-widget --toggle <name> (toggle: kill if running, launch if not)

TOGGLE=false
if [ "$1" = "--toggle" ]; then
    TOGGLE=true
    shift
fi

NAME="$1"
if [ -z "$NAME" ]; then
    echo "Usage: costa-widget [--toggle] <widget-name>" >&2
    exit 1
fi

# Search locations in priority order
SEARCH_PATHS=(
    "$HOME/.config/$NAME/widget.py"
    "$HOME/.config/costa/scripts/$NAME.py"
    "/usr/share/costa-os/widgets/$NAME/widget.py"
    "/usr/share/costa-os/scripts/$NAME.py"
)

# Dev environment: check project dir if it exists
for devpath in \
    "$HOME/projects/costa-os/configs/$NAME/widget.py" \
    "$HOME/projects/costa-os/scripts/$NAME.py"; do
    [ -f "$devpath" ] && SEARCH_PATHS=("$devpath" "${SEARCH_PATHS[@]}")
done

WIDGET=""
for path in "${SEARCH_PATHS[@]}"; do
    if [ -f "$path" ]; then
        WIDGET="$path"
        break
    fi
done

if [ -z "$WIDGET" ]; then
    notify-send -u critical "Costa Widget" "Widget '$NAME' not found.\nSearched: ${SEARCH_PATHS[*]}"
    exit 1
fi

if $TOGGLE; then
    # Kill existing instance or launch new one
    PID=$(pgrep -f "$NAME/widget.py" | head -1)
    if [ -n "$PID" ]; then
        kill "$PID"
        exit 0
    fi
fi

exec /usr/bin/python3 "$WIDGET"
