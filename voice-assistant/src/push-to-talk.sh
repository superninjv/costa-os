#!/usr/bin/env bash
# Voice Assistant — Push-to-talk with smart routing
# SUPER+ALT+V (claude mode) / SUPER+ALT+B (type mode)

exec 2>>/tmp/ptt-debug.log
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

# --- Configuration (override via environment) ---
WHISPER_BIN="${COSTA_WHISPER_BIN:-$(command -v whisper-cli 2>/dev/null || echo $HOME/.local/bin/whisper-cli)}"
MODEL="${COSTA_WHISPER_MODEL:-$HOME/.local/share/costa/whisper/ggml-tiny.en.bin}"
COSTA_AI="${COSTA_AI_ROUTER:-$(command -v costa-ai 2>/dev/null || echo /usr/local/bin/costa-ai)}"
SYSTEM_AI_PROMPT_FILE="${COSTA_SYSTEM_PROMPT:-$HOME/.config/costa/system-ai.md}"
TERMINAL="${COSTA_TERMINAL:-ghostty}"
OLLAMA_URL="${COSTA_OLLAMA_URL:-http://localhost:11434}"
OLLAMA_FAST="${COSTA_OLLAMA_FAST:-qwen2.5:3b}"
OLLAMA_MODEL=$(cat "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/costa/ollama-smart-model" 2>/dev/null || cat /tmp/ollama-smart-model 2>/dev/null || echo "${COSTA_OLLAMA_DEFAULT:-qwen2.5:14b}")
OLLAMA_SUMMARY="$OLLAMA_FAST"

LOCKFILE="/tmp/ptt.lock"
STATUS_FILE="/tmp/ptt-status"
CLAUDE_MODE=${PTT_MODE:-claude}
SYSTEM_AI_PROMPT=$(cat "$SYSTEM_AI_PROMPT_FILE" 2>/dev/null | tr '\n' ' ' | sed 's/"/\\"/g')

update_status() { echo "$1" > "$STATUS_FILE"; }

# Toggle: if already recording, stop it (with 2s debounce)
if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c%Y "$LOCKFILE") ))
    [ "$LOCK_AGE" -lt 2 ] && exit 0
    rm -f "$LOCKFILE"
    exit 0
fi

# If VAD daemon is busy with a previous recording, reject
VAD_BUSY=$(cat /tmp/vad-status 2>/dev/null)
if [ "$VAD_BUSY" = "listening" ] || [ "$VAD_BUSY" = "speech" ] || [ "$VAD_BUSY" = "starting" ] || [ "$VAD_BUSY" = "pending" ]; then
    notify-send -t 1000 "Still processing..." -a "VoiceMode"
    exit 0
fi

touch "$LOCKFILE"
update_status "listening"

# Pre-warm Ollama while user talks (background, costs nothing if not used)
curl -s "$OLLAMA_URL/api/generate" -d "{\"model\":\"$OLLAMA_MODEL\",\"prompt\":\"\",\"keep_alive\":\"5m\"}" > /dev/null 2>&1 &

# Duck system audio
ORIG_VOL=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null | awk '{print $2}')
wpctl set-volume @DEFAULT_AUDIO_SINK@ 0 2>/dev/null

# Record with VAD auto-stop via daemon
# Daemon keeps Silero model loaded, processes only last 2.5s each check
notify-send -t 1000 "Listening..." -a "VoiceMode"

VAD_STATUS=$(cat /tmp/vad-status 2>/dev/null)
if [ "$VAD_STATUS" = "ready" ]; then
    # Use VAD daemon for auto-stop
    # Remove old output file so we can detect when new one appears
    rm -f /tmp/ptt-raw.wav

    # Set status BEFORE writing cmd — eliminates race condition
    echo "pending" > /tmp/vad-status
    echo "record /tmp/ptt-raw.wav" > /tmp/vad-cmd

    # Phase 1: wait for daemon to start recording (file appears)
    for i in $(seq 1 50); do
        [ -f /tmp/ptt-raw.wav ] && break
        sleep 0.1
    done

    # Phase 2: wait for daemon to finish (status is no longer listening/speech)
    while true; do
        STATUS=$(cat /tmp/vad-status 2>/dev/null)
        # Terminal states
        [ "$STATUS" = "done" ] || [ "$STATUS" = "error" ] || [ "$STATUS" = "ready" ] && break
        # Manual stop
        [ ! -f "$LOCKFILE" ] && break
        # Safety: if file stopped growing for 3s, daemon is done
        sleep 0.2
    done
    # Brief pause to let daemon write final status
    sleep 0.3
else
    # Fallback: 6s hard timeout if daemon not running
    pw-cat --record --format=s16 --rate=16000 --channels=1 /tmp/ptt-raw.wav &
    REC_PID=$!
    (sleep 6; [ -f "$LOCKFILE" ] && rm -f "$LOCKFILE" && kill $REC_PID 2>/dev/null) &
    TIMER_PID=$!
    while [ -f "$LOCKFILE" ] && kill -0 $REC_PID 2>/dev/null; do sleep 0.2; done
    kill $REC_PID $TIMER_PID 2>/dev/null
    wait $REC_PID $TIMER_PID 2>/dev/null
fi

rm -f "$LOCKFILE"

# Restore volume
wpctl set-volume @DEFAULT_AUDIO_SINK@ "${ORIG_VOL:-0.4}" 2>/dev/null

# Check audio
if [ ! -f /tmp/ptt-raw.wav ] || [ "$(stat -c%s /tmp/ptt-raw.wav 2>/dev/null)" -lt 2000 ]; then
    update_status "ready"
    notify-send -t 1500 "No speech detected" -a "VoiceMode"
    rm -f /tmp/ptt-raw.wav
    exit 1
fi

update_status "processing"
notify-send -t 1000 "Processing..." -a "VoiceMode"

# Transcribe with tiny.en (GPU accelerated, ~0.5s)
RESULT=$("$WHISPER_BIN" -m "$MODEL" -f /tmp/ptt-raw.wav --no-timestamps -nt 2>/dev/null \
    | sed '/^$/d; s/^ *//; s/ *$//; s/\[.*\]//g' | tr -s ' ')
rm -f /tmp/ptt-raw.wav

RESULT=$(echo "$RESULT" | xargs -0 | tr -s ' ' | sed 's/^ *//;s/ *$//')
if [ -z "$RESULT" ] || echo "$RESULT" | grep -qiE '^\(.*\)$|^you$|^thank you\.?$|^$'; then
    update_status "ready"
    notify-send -t 1500 "No speech detected" -a "VoiceMode"
    exit 1
fi

# Strip submit/hold keywords
SHOULD_SUBMIT=true
if echo "$RESULT" | grep -qiE '(draft|hold|wait|don.t send|no submit)\s*\.?\s*$'; then
    SHOULD_SUBMIT=false
    RESULT=$(echo "$RESULT" | sed -E "s/\s*(draft|hold|wait|don't send|no submit)\s*\.?\s*$//i" | xargs -0 | tr -s ' ')
fi
RESULT=$(echo "$RESULT" | sed -E "s/\s*(send it|submit|enter|go ahead|send that|over|confirm)\s*\.?\s*$//i" | xargs -0 | tr -s ' ' | sed 's/^ *//;s/ *$//')

echo "$RESULT" | wl-copy
update_status "ready"

if [ "$CLAUDE_MODE" = "claude" ]; then
    echo "running" > /tmp/ptt-voice-status
    echo "$RESULT" > /tmp/ptt-voice-command
    echo "" > /tmp/ptt-voice-output

    (
        # Route through costa-ai — handles context injection, model selection, and auto-escalation
        ROUTER_OUTPUT=$(python3 "$COSTA_AI" --json "$RESULT" 2>/dev/null)
        EXIT_CODE=$?

        if [ -n "$ROUTER_OUTPUT" ]; then
            echo "$ROUTER_OUTPUT" | jq -r '.response' > /tmp/ptt-voice-output 2>&1
            echo "$ROUTER_OUTPUT" | jq -r '.route' > /tmp/ptt-voice-model 2>&1
        fi

        # Handle timeout
        if [ $EXIT_CODE -eq 124 ]; then
            echo "timed out" > /tmp/ptt-voice-status
            notify-send -t 3000 "Voice command timed out" -a "VoiceMode"
            sleep 10
            echo "idle" > /tmp/ptt-voice-status
            rm -f /tmp/ptt-voice-output /tmp/ptt-voice-lastline /tmp/ptt-voice-command /tmp/ptt-voice-model
            exit 0
        fi

        # Handle errors -> escalate to interactive
        if [ $EXIT_CODE -ne 0 ] && [ $EXIT_CODE -ne 124 ]; then
            echo "interactive" > /tmp/ptt-voice-status
            notify-send -t 5000 "Claude needs input — opening window" -a "VoiceMode"
            ESCAPED=$(printf '%s' "$RESULT" | sed "s/'/'\\\\''/g")
            "$TERMINAL" --class=voice-claude -e bash -c "
                if [ -s /tmp/ptt-voice-output ]; then
                    cat /tmp/ptt-voice-output
                    echo ''
                fi
                echo '───────────────────────────────────────'
                if command -v claude &>/dev/null; then
                    EMODEL=\$(cat /tmp/ptt-voice-model 2>/dev/null || echo sonnet)
                    cd ~ && claude --model \$EMODEL --dangerously-skip-permissions '$ESCAPED'
                else
                    echo 'Claude Code not installed. Install with: npm install -g @anthropic-ai/claude-code'
                    echo ''
                    echo 'Query was: $ESCAPED'
                fi
                echo 'done' > /tmp/ptt-voice-status
                sleep 5
            " &
            GHOSTTY_PID=$!
            sleep 1
            hyprctl --batch 'dispatch focuswindow class:voice-claude; dispatch togglefloating class:voice-claude; dispatch resizewindowpixel exact 900 500,class:voice-claude; dispatch centerwindow class:voice-claude' 2>/dev/null
            wait $GHOSTTY_PID
            echo "idle" > /tmp/ptt-voice-status
            rm -f /tmp/ptt-voice-output /tmp/ptt-voice-lastline /tmp/ptt-voice-command /tmp/ptt-voice-model
        else
            # Success — summarize with local Ollama (fast) and display
            OUTPUT_LEN=$(wc -c < /tmp/ptt-voice-output 2>/dev/null || echo "0")
            RAW_TEXT=$(sed 's/[*#`]//g' /tmp/ptt-voice-output | tr '\n' ' ' | tr -s ' ' | head -c 200)

            if [ "$OUTPUT_LEN" -gt 120 ]; then
                # Summarize long output with fast 3b model
                SUMMARY=$(curl -s "$OLLAMA_URL/api/generate" \
                    -d "$(jq -n --arg p "Summarize in one sentence, max 80 chars, no quotes: $RAW_TEXT" --arg m "$OLLAMA_SUMMARY" \
                    '{model:$m,prompt:$p,stream:false,keep_alive:"5m"}')" \
                    | jq -r '.response' | head -c 100)
                [ -z "$SUMMARY" ] && SUMMARY="$RAW_TEXT"
            else
                SUMMARY="$RAW_TEXT"
            fi

            echo "scroll" > /tmp/ptt-voice-status
            echo "$SUMMARY" > /tmp/ptt-voice-scroll
            notify-send -t 5000 "$SUMMARY" -a "VoiceMode"
            sleep 20
            echo "idle" > /tmp/ptt-voice-status
            rm -f /tmp/ptt-voice-output /tmp/ptt-voice-lastline /tmp/ptt-voice-command /tmp/ptt-voice-scroll /tmp/ptt-voice-model
        fi
    ) &disown
else
    # Type mode
    if [ "$SHOULD_SUBMIT" = true ]; then
        notify-send -t 2000 "$RESULT [sending]" -a "VoiceMode"
    else
        notify-send -t 3000 "$RESULT [draft]" -a "VoiceMode"
    fi
    wtype -d 20 "$RESULT" 2>/dev/null || true
    if [ "$SHOULD_SUBMIT" = true ]; then
        sleep 0.1
        wtype -k Return 2>/dev/null || true
    fi
fi
