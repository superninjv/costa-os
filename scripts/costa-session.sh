#!/bin/bash
# costa-session — Run an autonomous Claude Code session with logging and notifications
#
# Usage:
#   costa-session --workdir ~/projects/foo --budget 10 "Refactor the auth module"
#   costa-session --prompt-file ~/tasks/refactor.md --budget 25 --model opus
#   costa-session --allowed-tools "Bash(git:*) Read Edit Glob Grep" "Add tests"

set -euo pipefail

SESSION_LOG_DIR="$HOME/.local/share/costa/claude-sessions"
STATUS_FILE="/tmp/costa-session-status.json"
mkdir -p "$SESSION_LOG_DIR"

# Defaults
WORKDIR="$(pwd)"
BUDGET="5.0"
MODEL=""
ALLOWED_TOOLS=""
PERMISSION_MODE="acceptEdits"
PROMPT=""
PROMPT_FILE=""
TIMEOUT="14400"

usage() {
    cat <<'USAGE'
costa-session — Autonomous Claude Code sessions

Usage:
  costa-session [options] "prompt"
  costa-session [options] --prompt-file <path>
  costa-session log [session-name]

Options:
  --workdir <dir>          Working directory (default: current)
  --budget <dollars>       Max spend in USD (default: 5, cap: 50)
  --model <name>           Model override (sonnet, opus, haiku)
  --allowed-tools <spec>   Tool restriction (Claude --allowedTools format)
  --permission-mode <mode> Permission mode (default: acceptEdits)
  --prompt-file <path>     Read prompt from file
  --timeout <seconds>      Session timeout (default: 14400 = 4 hours)

Examples:
  costa-session --workdir ~/projects/myapp --budget 10 "Add unit tests for all API endpoints"
  costa-session --prompt-file ~/tasks/refactor.md --budget 25 --model opus
  costa-session log                    # List recent sessions
  costa-session log session-20260322   # Show specific session
USAGE
    exit 0
}

# --- Log subcommand ---
if [[ "${1:-}" == "log" ]]; then
    if [[ -n "${2:-}" ]]; then
        # Show specific session
        LOG_FILE=$(find "$SESSION_LOG_DIR" -name "${2}*.json" -not -name "*.stderr" -type f | head -1)
        if [[ -n "$LOG_FILE" ]]; then
            python3 - "$LOG_FILE" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"Session: {d.get('session', '?')}")
print(f"Status:  {d.get('status', '?')}")
print(f"Started: {d.get('started', '?')}")
print(f"Ended:   {d.get('finished', '?')}")
dur = d.get('duration_seconds', 0)
print(f"Duration: {dur // 60}m {dur % 60}s")
print(f"Budget:  ${d.get('budget', '?')}")
print(f"Model:   {d.get('model', '?')}")
print(f"Workdir: {d.get('workdir', '?')}")
if d.get('output'):
    # Claude's output may be JSON — extract the result text
    try:
        parsed = json.loads(d['output'])
        text = parsed.get('result', d['output'][:2000])
    except (json.JSONDecodeError, AttributeError):
        text = d['output'][:2000]
    print(f"\nResult:\n{text}")
PYEOF
        else
            echo "No session found matching: $2"
        fi
    else
        # List recent sessions
        echo "Recent sessions:"
        for f in $(ls -t "$SESSION_LOG_DIR"/*.json 2>/dev/null | head -10); do
            python3 - "$f" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
dur = d.get('duration_seconds', 0)
print(f"  {d.get('session','?'):36s} {d.get('status','?'):10s} ${d.get('budget','?')}  {d.get('model','?'):8s} {dur//60}m{dur%60}s")
PYEOF
        done
    fi
    exit 0
fi

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workdir)    WORKDIR="$2"; shift 2 ;;
        --budget)     BUDGET="$2"; shift 2 ;;
        --model)      MODEL="$2"; shift 2 ;;
        --allowed-tools) ALLOWED_TOOLS="$2"; shift 2 ;;
        --permission-mode) PERMISSION_MODE="$2"; shift 2 ;;
        --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
        --timeout)    TIMEOUT="$2"; shift 2 ;;
        -h|--help)    usage ;;
        *)            PROMPT="$1"; shift ;;
    esac
done

# Read prompt from file if specified
if [[ -n "$PROMPT_FILE" ]]; then
    if [[ -f "$PROMPT_FILE" ]]; then
        PROMPT="$(cat "$PROMPT_FILE")"
    else
        echo "Error: prompt file not found: $PROMPT_FILE" >&2
        exit 1
    fi
fi

if [[ -z "$PROMPT" ]]; then
    echo "Error: no prompt provided. Use costa-session --help for usage." >&2
    exit 1
fi

# Enforce budget cap
if [[ "${BUDGET%.*}" -gt 50 ]]; then
    echo "Warning: budget capped at \$50 (was \$$BUDGET)" >&2
    BUDGET="50.0"
fi

# Session ID and log
SESSION_NAME="session-$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$SESSION_LOG_DIR/$SESSION_NAME.json"
STDERR_LOG="$SESSION_LOG_DIR/$SESSION_NAME.stderr"

# Build command
CMD=(claude -p --output-format json --permission-mode "$PERMISSION_MODE" --max-budget-usd "$BUDGET")
[[ -n "$MODEL" ]] && CMD+=(--model "$MODEL")
[[ -n "$ALLOWED_TOOLS" ]] && CMD+=(--allowedTools "$ALLOWED_TOOLS")
CMD+=("$PROMPT")

# Write running status
echo "{\"session\":\"$SESSION_NAME\",\"started\":\"$(date -Iseconds)\",\"workdir\":\"$WORKDIR\",\"budget\":$BUDGET,\"model\":\"${MODEL:-default}\",\"status\":\"running\"}" > "$STATUS_FILE"

echo "Starting session: $SESSION_NAME"
echo "  Workdir: $WORKDIR"
echo "  Budget:  \$$BUDGET"
echo "  Model:   ${MODEL:-default}"
echo "  Timeout: ${TIMEOUT}s"
echo "  Log:     $LOG_FILE"
echo ""

# Run Claude Code
cd "$WORKDIR"
START_TIME=$(date +%s)

if timeout "$TIMEOUT" "${CMD[@]}" > "$LOG_FILE.raw" 2>"$STDERR_LOG"; then
    EXIT_CODE=0
    STATUS="completed"
else
    EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 124 ]]; then
        STATUS="timeout"
    else
        STATUS="failed"
    fi
fi

END_TIME=$(date +%s)
DURATION=$(( END_TIME - START_TIME ))

# Build final log JSON
python3 -c "
import json
raw = ''
try:
    with open('$LOG_FILE.raw') as f:
        raw = f.read()
except: pass

log = {
    'session': '$SESSION_NAME',
    'started': '$(date -Iseconds -d @$START_TIME)',
    'finished': '$(date -Iseconds -d @$END_TIME)',
    'duration_seconds': $DURATION,
    'workdir': '$WORKDIR',
    'budget': $BUDGET,
    'model': '${MODEL:-default}',
    'status': '$STATUS',
    'exit_code': $EXIT_CODE,
    'output': raw[:50000],
}

stderr = ''
try:
    with open('$STDERR_LOG') as f:
        stderr = f.read()
except: pass
if stderr:
    log['stderr'] = stderr[:5000]

with open('$LOG_FILE', 'w') as f:
    json.dump(log, f, indent=2)
"

# Clean up raw file
rm -f "$LOG_FILE.raw"

# Clear running status
echo '{"status":"idle"}' > "$STATUS_FILE"

# Notify
NOTIFY_BODY="Status: $STATUS | Duration: ${DURATION}s | Budget: \$$BUDGET"
notify-send -a "Costa Session" "Session Complete: $SESSION_NAME" "$NOTIFY_BODY" 2>/dev/null || true

echo ""
echo "Session $STATUS in ${DURATION}s"
echo "Log: $LOG_FILE"
