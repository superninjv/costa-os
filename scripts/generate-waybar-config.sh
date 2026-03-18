#!/usr/bin/env bash
# Costa OS — Waybar config generator
# Detects monitors and assembles bar templates into ~/.config/waybar/config
#
# Usage:
#   generate-waybar-config.sh              # auto-detect monitors
#   generate-waybar-config.sh --dry-run    # print config to stdout
#   generate-waybar-config.sh --primary DP-1 --perf HDMI-A-1 --minimal HDMI-A-2
#
# Bar assignment logic:
#   1 monitor  → main bar only
#   2 monitors → main on primary, performance on secondary
#   3+ monitors → main on primary, performance on first secondary,
#                 minimal on remaining secondaries
#   Headless HEADLESS-1 → claude screen bar (if present)
#   Taskbar goes on same monitor as performance bar (or primary if only 1)

set -euo pipefail

TEMPLATE_DIR="${COSTA_TEMPLATE_DIR:-$(dirname "$0")/../configs/waybar/templates}"
OUTPUT_FILE="${HOME}/.config/waybar/config"
DRY_RUN=false
TIMEZONE=$(timedatectl show -p Timezone --value 2>/dev/null || echo "UTC")

# ─── Read Costa config for feature flags ───
COSTA_CONFIG="${COSTA_DIR:-$HOME/.config/costa}/config.json"
AI_TIER="VOICE_AND_LLM"  # default: all features
HAS_MIC=true
if [ -f "$COSTA_CONFIG" ] && command -v jq &>/dev/null; then
    AI_TIER=$(jq -r '.ai_tier // "VOICE_AND_LLM"' "$COSTA_CONFIG")
    HAS_MIC=$(jq -r '.has_microphone // true' "$COSTA_CONFIG")
fi

# Manual overrides
MANUAL_PRIMARY=""
MANUAL_PERF=""
MANUAL_MINIMAL=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --primary)    MANUAL_PRIMARY="$2"; shift 2 ;;
        --perf)       MANUAL_PERF="$2"; shift 2 ;;
        --minimal)    MANUAL_MINIMAL+=("$2"); shift 2 ;;
        --templates)  TEMPLATE_DIR="$2"; shift 2 ;;
        --output)     OUTPUT_FILE="$2"; shift 2 ;;
        *)            echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ─── Detect monitors ───

detect_monitors() {
    # Try hyprctl first (running Hyprland)
    if command -v hyprctl &>/dev/null && hyprctl monitors -j &>/dev/null; then
        hyprctl monitors -j | python3 -c "
import json, sys
monitors = json.load(sys.stdin)
for m in monitors:
    name = m['name']
    w, h = m['width'], m['height']
    refresh = m.get('refreshRate', 60)
    desc = m.get('description', '')
    # Mark headless monitors
    is_headless = name.startswith('HEADLESS')
    print(f'{name}\t{w}x{h}\t{refresh}\t{is_headless}\t{desc}')
"
    # Fallback: wlr-randr
    elif command -v wlr-randr &>/dev/null; then
        wlr-randr | awk '/^[A-Z]/{name=$1} /current/{gsub(/,/,""); print name "\t" $1 "\t60\tFalse\t"}'
    else
        echo "ERROR: No monitor detection available (need hyprctl or wlr-randr)" >&2
        exit 1
    fi
}

# ─── Detect hardware paths ───

find_gpu_busy_path() {
    # AMD GPU busy percent
    for card in /sys/class/drm/card*/device/gpu_busy_percent; do
        if [[ -r "$card" ]]; then
            echo "$card"
            return
        fi
    done
    echo "/sys/class/drm/card0/device/gpu_busy_percent"
}

find_hwmon_path() {
    local search="$1"  # "cpu" or "gpu"
    if [[ "$search" == "cpu" ]]; then
        # AMD CPU temp: k10temp or zenpower
        for hwmon in /sys/class/hwmon/hwmon*/name; do
            name=$(cat "$hwmon" 2>/dev/null)
            if [[ "$name" == "k10temp" || "$name" == "zenpower" || "$name" == "coretemp" ]]; then
                dirname "$hwmon"
                return
            fi
        done
        # Fallback: find any hwmon under the CPU thermal zone
        for path in /sys/devices/pci0000:00/0000:00:18.3/hwmon/hwmon*; do
            if [[ -d "$path" ]]; then
                echo "$(dirname "$path")"
                return
            fi
        done
    elif [[ "$search" == "gpu" ]]; then
        # AMD GPU: amdgpu hwmon
        for hwmon in /sys/class/hwmon/hwmon*/name; do
            name=$(cat "$hwmon" 2>/dev/null)
            if [[ "$name" == "amdgpu" ]]; then
                dirname "$hwmon"
                return
            fi
        done
    fi
    echo ""
}

# ─── Template processing ───

read_template() {
    local name="$1"
    local file="${TEMPLATE_DIR}/${name}.jsonc"
    if [[ ! -f "$file" ]]; then
        echo "Template not found: $file" >&2
        return 1
    fi
    # Strip // comments (but not :// in URLs)
    sed 's|^\s*//.*||; s|\s\+//\s\+.*||' "$file" | grep -v '^\s*$'
}

fill_template() {
    local template="$1"
    local output="$2"
    local persistent_workspaces="$3"

    local gpu_busy_path
    gpu_busy_path=$(find_gpu_busy_path)
    local cpu_hwmon_path
    cpu_hwmon_path=$(find_hwmon_path cpu)
    local gpu_hwmon_path
    gpu_hwmon_path=$(find_hwmon_path gpu)

    # Remove battery module on desktops (no /sys/class/power_supply/BAT*)
    local has_battery=false
    ls /sys/class/power_supply/BAT* &>/dev/null && has_battery=true

    # Use a temp file to avoid echo/printf mangling \n escapes in JSON strings
    local tmpfile
    tmpfile=$(mktemp)
    printf '%s\n' "$template" > "$tmpfile"

    sed -i "s|\"__OUTPUT__\"|\"${output}\"|g" "$tmpfile"
    sed -i "s|\"__PERSISTENT_WORKSPACES__\"|${persistent_workspaces}|g" "$tmpfile"
    sed -i "s|__TIMEZONE__|${TIMEZONE}|g" "$tmpfile"
    sed -i "s|__GPU_BUSY_PATH__|${gpu_busy_path}|g" "$tmpfile"
    sed -i "s|__CPU_HWMON_PATH__|${cpu_hwmon_path}|g" "$tmpfile"
    sed -i "s|__GPU_HWMON_PATH__|${gpu_hwmon_path}|g" "$tmpfile"

    if ! $has_battery; then
        python3 /dev/stdin "$tmpfile" << 'PYEOF'
import re, sys
f = sys.argv[1]
text = open(f).read()
# Remove "battery" from module arrays only (not from "battery": key)
text = re.sub(r'"battery"\s*,\s*(?!")', '', text)
text = re.sub(r',\s*"battery"\s*(?=[\]\n])', '', text)
# Remove "battery": { ... } block (with nested braces)
start = text.find('"battery":')
if start >= 0:
    brace = text.index('{', start)
    depth, i = 1, brace + 1
    while i < len(text) and depth > 0:
        if text[i] == '{': depth += 1
        elif text[i] == '}': depth -= 1
        i += 1
    # Eat leading comma if present
    s = start
    j = s - 1
    while j >= 0 and text[j] in ' \t\n\r': j -= 1
    if j >= 0 and text[j] == ',':
        s = j
    else:
        # Eat trailing comma
        k = i
        while k < len(text) and text[k] in ' \t\n\r': k += 1
        if k < len(text) and text[k] == ',':
            i = k + 1
    text = text[:s] + text[i:]
open(f, 'w').write(text)
PYEOF
    fi

    # Strip modules based on AI tier and mic availability
    if [[ "$AI_TIER" == "CLOUD_ONLY" ]]; then
        sed -i '/"custom\/costa-ai"/d; /"custom\/ai-report"/d; /"custom\/ptt"/d; /"custom\/headless-preview"/d' "$tmpfile"
    fi
    if [[ "$HAS_MIC" == "false" ]] || [[ "$AI_TIER" == "CLOUD_ONLY" ]]; then
        sed -i '/"custom\/ptt"/d' "$tmpfile"
    fi

    cat "$tmpfile"
    rm -f "$tmpfile"
}

# ─── Main ───

# Read monitors
mapfile -t MONITOR_LINES < <(detect_monitors)

if [[ ${#MONITOR_LINES[@]} -eq 0 ]]; then
    echo "No monitors detected!" >&2
    exit 1
fi

# Parse into arrays
NAMES=()
WIDTHS=()
REFRESHES=()
HEADLESS=()
for line in "${MONITOR_LINES[@]}"; do
    IFS=$'\t' read -r name res refresh headless desc <<< "$line"
    NAMES+=("$name")
    w="${res%x*}"
    WIDTHS+=("$w")
    REFRESHES+=("$refresh")
    HEADLESS+=("$headless")
done

# Determine primary: manual override, or highest-refresh non-headless, then largest
if [[ -n "$MANUAL_PRIMARY" ]]; then
    PRIMARY="$MANUAL_PRIMARY"
else
    PRIMARY=""
    best_score=0
    for i in "${!NAMES[@]}"; do
        [[ "${HEADLESS[$i]}" == "True" ]] && continue
        # Score: refresh * 10000 + width
        score=$(python3 -c "print(int(${REFRESHES[$i]} * 10000 + ${WIDTHS[$i]}))")
        if (( score > best_score )); then
            best_score=$score
            PRIMARY="${NAMES[$i]}"
        fi
    done
fi

# Collect non-primary, non-headless monitors
SECONDARIES=()
HEADLESS_MONITORS=()
for i in "${!NAMES[@]}"; do
    [[ "${NAMES[$i]}" == "$PRIMARY" ]] && continue
    if [[ "${HEADLESS[$i]}" == "True" ]]; then
        HEADLESS_MONITORS+=("${NAMES[$i]}")
    else
        SECONDARIES+=("${NAMES[$i]}")
    fi
done

echo "Detected monitors:" >&2
echo "  Primary: $PRIMARY" >&2
for s in "${SECONDARIES[@]+"${SECONDARIES[@]}"}"; do
    echo "  Secondary: $s" >&2
done
for h in "${HEADLESS_MONITORS[@]+"${HEADLESS_MONITORS[@]}"}"; do
    echo "  Headless: $h" >&2
done

# ─── Assign workspaces ───
# Primary gets workspaces 1-4 (or all if single monitor)
# First secondary gets 5-6
# Additional secondaries get 7+

build_persistent_ws() {
    local output="$1"
    shift
    local ws_list=("$@")
    local result="{"
    local first=true
    for ws in "${ws_list[@]}"; do
        $first || result+=", "
        result+="\"${ws}\": [\"${output}\"]"
        first=false
    done
    result+="}"
    echo "$result"
}

# ─── Assemble config ───

BARS=()

# Main bar (always present)
if [[ ${#SECONDARIES[@]} -eq 0 && ${#HEADLESS_MONITORS[@]} -eq 0 ]]; then
    # Single monitor: all workspaces
    main_ws=$(build_persistent_ws "$PRIMARY" 1 2 3 4 5 6)
else
    main_ws=$(build_persistent_ws "$PRIMARY" 1 2 3 4)
fi
main_template=$(read_template "main-bar")
BARS+=("$(fill_template "$main_template" "$PRIMARY" "$main_ws")")

# Performance bar on first secondary (or manual override)
PERF_OUTPUT=""
if [[ -n "$MANUAL_PERF" ]]; then
    PERF_OUTPUT="$MANUAL_PERF"
elif [[ ${#SECONDARIES[@]} -ge 1 ]]; then
    PERF_OUTPUT="${SECONDARIES[0]}"
fi

if [[ -n "$PERF_OUTPUT" ]]; then
    perf_ws_nums=(5 6)
    # If 3+ physical monitors, first secondary gets 5, second gets 6
    if [[ ${#SECONDARIES[@]} -ge 2 ]]; then
        perf_ws_nums=(5)
    fi
    perf_ws=$(build_persistent_ws "$PERF_OUTPUT" "${perf_ws_nums[@]}")
    perf_template=$(read_template "performance-bar")
    BARS+=("$(fill_template "$perf_template" "$PERF_OUTPUT" "$perf_ws")")

    # Taskbar on same monitor as performance bar
    taskbar_template=$(read_template "taskbar")
    BARS+=("$(fill_template "$taskbar_template" "$PERF_OUTPUT" "{}")")
fi

# Minimal bars on remaining secondaries
REMAINING_WS=7
for i in "${!SECONDARIES[@]}"; do
    [[ "${SECONDARIES[$i]}" == "$PERF_OUTPUT" ]] && continue

    # Check manual minimal list
    if [[ ${#MANUAL_MINIMAL[@]} -gt 0 ]]; then
        found=false
        for mm in "${MANUAL_MINIMAL[@]}"; do
            [[ "$mm" == "${SECONDARIES[$i]}" ]] && found=true
        done
        $found || continue
    fi

    min_ws=$(build_persistent_ws "${SECONDARIES[$i]}" "$REMAINING_WS")
    min_template=$(read_template "minimal-bar")
    BARS+=("$(fill_template "$min_template" "${SECONDARIES[$i]}" "$min_ws")")
    ((REMAINING_WS++))
done

# Claude screen bar on headless monitors
for hm in "${HEADLESS_MONITORS[@]+"${HEADLESS_MONITORS[@]}"}"; do
    claude_ws=$(build_persistent_ws "$hm" 10)
    claude_template=$(read_template "claude-screen-bar")
    BARS+=("$(fill_template "$claude_template" "$hm" "$claude_ws")")
done

# ─── Output ───

config="["
first=true
for bar in "${BARS[@]}"; do
    $first || config+=","
    config+=$'\n'"  ${bar}"
    first=false
done
config+=$'\n'"]"$'\n'

if $DRY_RUN; then
    echo "$config"
else
    mkdir -p "$(dirname "$OUTPUT_FILE")"
    # Backup existing config
    if [[ -f "$OUTPUT_FILE" ]]; then
        cp "$OUTPUT_FILE" "${OUTPUT_FILE}.bak"
    fi
    echo "$config" > "$OUTPUT_FILE"
    echo "Waybar config written to ${OUTPUT_FILE}" >&2
    echo "Backup saved to ${OUTPUT_FILE}.bak" >&2

    # Restart waybar if running
    if pgrep -x waybar &>/dev/null; then
        killall waybar
        waybar &disown 2>/dev/null
        echo "Waybar restarted." >&2
    fi
fi
