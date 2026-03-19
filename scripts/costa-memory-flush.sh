#!/bin/bash
# Costa OS — Memory Flush Script
# Called by Claude Code PreCompact hook to save session context before compaction.
# Writes a reminder to stdout that gets injected into Claude's post-compact context.

NOTES_DIR="${HOME}/notes"
DAILY_DIR="${NOTES_DIR}/daily"
TODAY=$(date +%Y-%m-%d)
DAILY_FILE="${DAILY_DIR}/${TODAY}.md"

mkdir -p "$DAILY_DIR"

# Create today's daily note if it doesn't exist
if [ ! -f "$DAILY_FILE" ]; then
    cat > "$DAILY_FILE" << EOF
---
date: ${TODAY}
type: daily
---
# ${TODAY}

EOF
fi

# Output reminder that gets injected into Claude's context after compaction
cat << 'EOF'
CONTEXT COMPACTION OCCURRED — IMPORTANT REMINDERS:

Before continuing, you MUST save any important session context that would be lost:

1. **Save session progress**: Append a summary of what you've been working on to today's daily note at ~/notes/daily/ using the obsidian MCP server. Include: current task, decisions made, blockers encountered, and next steps.

2. **Save any user corrections**: If the user corrected your approach during this session, save it to ~/notes/feedback/ so you don't repeat the mistake.

3. **Check daily note**: Read today's daily note (~/notes/daily/) to recover any context from earlier in this session that was just compacted.

4. **Check feedback notes**: Read ~/notes/feedback/ for behavioral guidance you should continue following.

After saving context, continue with the user's task.
EOF
