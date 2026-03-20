#!/bin/bash
# Costa OS — Session Start Script
# Called by Claude Code SessionStart hook to load recent context.
# Outputs today's + yesterday's daily notes and recent feedback for context injection.

NOTES_DIR="${HOME}/notes"
DAILY_DIR="${NOTES_DIR}/daily"
FEEDBACK_DIR="${NOTES_DIR}/feedback"
BASELINE_TEMPLATE="${HOME}/projects/costa-os/configs/claude/CLAUDE-baseline.md"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null)

# Auto-create baseline CLAUDE.md in projects that don't have one
# Uses CLAUDE_CWD if set (Claude Code working directory), otherwise PWD
PROJECT_DIR="${CLAUDE_CWD:-$PWD}"
if [ -d "$PROJECT_DIR/.git" ] && [ ! -f "$PROJECT_DIR/CLAUDE.md" ] && [ -f "$BASELINE_TEMPLATE" ]; then
    cp "$BASELINE_TEMPLATE" "$PROJECT_DIR/CLAUDE.md"
    echo "--- Baseline CLAUDE.md created for $(basename "$PROJECT_DIR") ---"
    echo "Edit $PROJECT_DIR/CLAUDE.md to add project-specific instructions."
    echo ""
fi

# Create today's daily note if it doesn't exist
mkdir -p "$DAILY_DIR"
if [ ! -f "$DAILY_DIR/${TODAY}.md" ]; then
    cat > "$DAILY_DIR/${TODAY}.md" << EOF
---
date: ${TODAY}
type: daily
---
# ${TODAY}

EOF
fi

# Output context for injection
echo "=== DAILY CONTEXT (auto-loaded from Obsidian vault) ==="
echo ""

# Yesterday's notes (if they exist)
if [ -f "$DAILY_DIR/${YESTERDAY}.md" ]; then
    echo "--- Yesterday (${YESTERDAY}) ---"
    cat "$DAILY_DIR/${YESTERDAY}.md"
    echo ""
fi

# Today's notes
if [ -f "$DAILY_DIR/${TODAY}.md" ]; then
    CONTENT=$(cat "$DAILY_DIR/${TODAY}.md")
    # Only show if there's actual content beyond the template
    LINE_COUNT=$(echo "$CONTENT" | wc -l)
    if [ "$LINE_COUNT" -gt 6 ]; then
        echo "--- Today (${TODAY}) ---"
        echo "$CONTENT"
        echo ""
    fi
fi

# Recent feedback (last 5 modified files)
if [ -d "$FEEDBACK_DIR" ] && ls "$FEEDBACK_DIR"/*.md &>/dev/null; then
    echo "--- Active Feedback ---"
    for f in $(ls -t "$FEEDBACK_DIR"/*.md 2>/dev/null | head -5); do
        # Skip YAML frontmatter, get first heading or meaningful line
        TITLE=$(awk '/^---$/{fm++; next} fm<2{next} /^#/{gsub(/^#+ /,""); print; exit} /[a-zA-Z]/{print; exit}' "$f")
        [ -n "$TITLE" ] && echo "• $TITLE"
    done
    echo ""
fi

echo "=== END DAILY CONTEXT ==="
echo ""
echo "Remember: Append session progress to ~/notes/daily/${TODAY}.md throughout this session."
echo "Save user corrections to ~/notes/feedback/. Check ~/notes/projects/ for project context."
