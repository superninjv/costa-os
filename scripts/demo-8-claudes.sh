#!/bin/bash
# Launch 8 Claude Code instances in a tiled grid on a target workspace
# Usage: ./scripts/demo-8-claudes.sh [workspace]
# Default workspace: 5 (HDMI-A-2)

set -e

WORKSPACE="${1:-5}"

# Non-sensitive prompts — these produce visually interesting output (tool calls, code, file reads)
# without touching config files, API keys, or personal data
# Add your project directories here (need at least 8 for a full grid)
declare -a PROJECTS=(
    "$HOME/projects/costa-os"
    "$HOME/projects/project-2"
    "$HOME/projects/project-3"
    "$HOME/projects/project-4"
    "$HOME/projects/project-5"
    "$HOME/projects/project-6"
    "$HOME/projects/project-7"
    "$HOME/projects/project-8"
)

declare -a PROMPTS=(
    "Review the ai-router test coverage. Read test files and identify which functions have no tests. List them."
    "Read the main page component and suggest 3 specific performance improvements with code snippets."
    "Analyze the API endpoints for consistent error handling. Read each route handler and check for missing try-catch blocks."
    "Read the Tauri config and the main Rust backend. Map out the IPC command flow from frontend to backend."
    "Read the upload handler and trace the full job lifecycle from upload to completion. Draw an ASCII diagram."
    "Read the mod loader code. Write a brief architecture doc as comments explaining how mods are discovered and loaded."
    "Read the analytics queries and suggest index optimizations. Show the current queries and what indexes would help."
    "Read the main application entry point and map all the routes and middleware. Output as a tree."
)

echo "╔══════════════════════════════════════╗"
echo "║   Costa OS Demo — 8 Claude Codes     ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Target workspace: $WORKSPACE"
echo ""

# Switch to target workspace
hyprctl dispatch workspace "$WORKSPACE"
sleep 0.5

# Launch all 8
for i in "${!PROJECTS[@]}"; do
    PROJECT="${PROJECTS[$i]}"
    PROMPT="${PROMPTS[$i]}"
    NAME=$(basename "$PROJECT")

    if [ ! -d "$PROJECT" ]; then
        echo "⚠ Skipping $NAME (directory not found)"
        continue
    fi

    echo "→ Launching Claude Code in $NAME..."

    # Launch ghostty with claude in the project dir
    # Using --print mode so it runs the task and streams output visually
    # --no-session-persistence to avoid cluttering session history
    hyprctl dispatch exec "[workspace $WORKSPACE silent]" \
        "ghostty -e zsh -lc 'cd \"$PROJECT\" && claude --no-session-persistence -p \"$PROMPT\"'"

    # Small delay so Hyprland can tile properly
    sleep 0.3
done

echo ""
echo "✓ Launched ${#PROJECTS[@]} Claude Code instances on workspace $WORKSPACE"
echo "  Switch to workspace $WORKSPACE to see the grid"
echo ""
echo "  Tip: hyprctl dispatch workspace $WORKSPACE"
