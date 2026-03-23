#!/bin/bash
# costa-session-loop — Run autonomous Claude Code sessions in a loop
# Each session gets fresh context. Summary file persists across sessions.
#
# Usage:
#   costa-session-loop --cycles 10 --prompt-file ~/tasks/job.md [costa-session args...]
#   costa-session-loop --hours 8 --prompt-file ~/tasks/job.md --budget 10 --model opus

set -euo pipefail

CYCLES=0
HOURS=0
PROMPT_FILE=""
COOLDOWN=10  # seconds between sessions
EXTRA_ARGS=()

usage() {
    cat <<'USAGE'
costa-session-loop — Loop autonomous Claude Code sessions

Usage:
  costa-session-loop [--cycles N | --hours N] [costa-session args...]

Loop options:
  --cycles N       Run N sessions then stop (default: unlimited)
  --hours N        Run for N hours then stop (default: unlimited)
  --cooldown N     Seconds between sessions (default: 10)

All other args are passed through to costa-session.
At least one of --cycles or --hours is required.

Examples:
  costa-session-loop --hours 8 --prompt-file ~/tasks/debug.md --budget 10 --model opus
  costa-session-loop --cycles 5 --prompt-file ~/tasks/refactor.md --budget 5
USAGE
    exit 0
}

# Parse loop-specific args, pass rest through
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cycles)    CYCLES="$2"; shift 2 ;;
        --hours)     HOURS="$2"; shift 2 ;;
        --cooldown)  COOLDOWN="$2"; shift 2 ;;
        -h|--help)   usage ;;
        *)           EXTRA_ARGS+=("$1"); shift ;;
    esac
done

if [[ "$CYCLES" -eq 0 && "$HOURS" -eq 0 ]]; then
    echo "Error: specify --cycles N or --hours N" >&2
    exit 1
fi

START_TIME=$(date +%s)
END_TIME=0
if [[ "$HOURS" -gt 0 ]]; then
    END_TIME=$(( START_TIME + HOURS * 3600 ))
fi

CYCLE=0
echo "═══════════════════════════════════════════"
echo " costa-session-loop"
echo " Cycles: ${CYCLES:-unlimited}  Hours: ${HOURS:-unlimited}"
echo " Started: $(date)"
echo "═══════════════════════════════════════════"

while true; do
    CYCLE=$(( CYCLE + 1 ))

    # Check cycle limit
    if [[ "$CYCLES" -gt 0 && "$CYCLE" -gt "$CYCLES" ]]; then
        echo ""
        echo "Completed $CYCLES cycles. Stopping."
        break
    fi

    # Check time limit
    if [[ "$END_TIME" -gt 0 && $(date +%s) -ge "$END_TIME" ]]; then
        echo ""
        echo "Time limit reached ($HOURS hours). Stopping."
        break
    fi

    echo ""
    echo "───── Cycle $CYCLE $(date '+%H:%M:%S') ─────"

    # Run costa-session (foreground, blocks until complete)
    costa-session --permission-mode bypassPermissions "${EXTRA_ARGS[@]}" || true

    echo "───── Cycle $CYCLE complete ─────"

    # Cooldown between sessions
    if [[ "$COOLDOWN" -gt 0 ]]; then
        echo "Cooldown ${COOLDOWN}s..."
        sleep "$COOLDOWN"
    fi
done

TOTAL_TIME=$(( $(date +%s) - START_TIME ))
echo ""
echo "═══════════════════════════════════════════"
echo " Loop complete: $CYCLE cycles in $(( TOTAL_TIME / 3600 ))h $(( (TOTAL_TIME % 3600) / 60 ))m"
echo " Summary: cat /tmp/costa-session-summary.txt"
echo " Sessions: costa-session log"
echo "═══════════════════════════════════════════"

notify-send -a "Costa Session" "Session Loop Complete" "$CYCLE cycles finished in $(( TOTAL_TIME / 3600 ))h $(( (TOTAL_TIME % 3600) / 60 ))m" 2>/dev/null || true
