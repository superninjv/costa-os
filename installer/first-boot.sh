#!/bin/bash
# Costa OS First-Boot Setup
# Runs after install — detects hardware, generates personalized configs,
# installs AI models, and launches the setup wizard.

# NOTE: do NOT use set -e here — detection functions may fail in VMs
# and we must always reach setup_claude_code() at the end

# Log everything to file AND terminal so we can debug crashes
FIRST_BOOT_LOG="/tmp/costa-first-boot.log"
exec > >(tee -a "$FIRST_BOOT_LOG") 2>&1

# No ERR trap — individual failures are handled inline, script must always complete

COSTA_DIR="$HOME/.config/costa"
HYPR_DIR="$HOME/.config/hypr"
AGS_DIR="$HOME/.config/ags"

echo "╔══════════════════════════════════════╗"
echo "║      Costa OS — First Boot Setup     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Network connectivity ────────────────────────────────────
check_internet() {
    ping -c1 -W2 archlinux.org &>/dev/null
}

wifi_setup() {
    echo "→ Checking network..."

    if check_internet; then
        echo "  ✓ Internet connection detected"
        echo ""
        return 0
    fi

    # Wait for NetworkManager to auto-connect (connection may be saved from installer)
    echo "  Waiting for network (saved connections may auto-connect)..."
    for i in $(seq 1 10); do
        sleep 2
        if check_internet; then
            echo "  ✓ Internet connection detected"
            echo ""
            return 0
        fi
        echo -ne "  \r  Waiting... (${i}0s)"
    done
    echo ""

    # Enable wifi radio if needed
    nmcli radio wifi on 2>/dev/null
    sleep 2

    # Check if wifi hardware exists
    if ! nmcli radio wifi 2>/dev/null | grep -q "enabled"; then
        echo "  ⚠ No WiFi adapter found."
        echo "  Connect an ethernet cable and press Enter to retry,"
        echo "  or type 'skip' to continue offline. (auto-skip in 30s)"
        read -r -t 30 answer || answer="skip"
        if [ "$answer" = "skip" ]; then
            echo "  Continuing offline."
            echo ""
            return 1
        fi
        if check_internet; then
            echo "  ✓ Internet connection detected"
            echo ""
            return 0
        fi
        echo "  ✗ Still no connection. Continuing offline."
        echo ""
        return 1
    fi

    echo "  No internet — let's connect to WiFi."
    echo ""

    nmcli device wifi rescan 2>/dev/null
    sleep 3

    while true; do
        # Scan and display networks
        echo "  Available WiFi networks:"
        echo ""

        NETWORKS=$(nmcli -f SSID,SIGNAL,SECURITY device wifi list --rescan no 2>/dev/null | tail -n +2 | awk '{
            for (i = NF; i >= 1; i--) {
                if ($i ~ /^[0-9]+$/) {
                    ssid = ""; for (j = 1; j < i; j++) ssid = ssid (j>1?" ":"") $j
                    sig = $i
                    sec = ""; for (j = i+1; j <= NF; j++) sec = sec (j>i+1?" ":"") $j
                    if (ssid != "" && ssid != "--") printf "%s\t%s\t%s\n", ssid, sig, sec
                    break
                }
            }
        }')
        if [ -z "$NETWORKS" ]; then
            echo "  No networks found."
            echo -n "  Rescan? (Y/n): "
            read -r yn
            if [ "$yn" = "n" ] || [ "$yn" = "N" ]; then
                echo "  Continuing offline."
                echo ""
                return 1
            fi
            nmcli device wifi rescan 2>/dev/null
            sleep 3
            continue
        fi

        declare -A SEEN_SSIDS
        SSID_LIST=()
        SEC_LIST=()
        NUM=0

        while IFS=$'\t' read -r ssid signal security; do
            [ -z "$ssid" ] && continue
            [ -n "${SEEN_SSIDS[$ssid]+x}" ] && continue
            SEEN_SSIDS[$ssid]=1
            NUM=$((NUM + 1))
            SSID_LIST+=("$ssid")
            SEC_LIST+=("$security")

            signal=${signal:-0}
            [[ "$signal" =~ ^[0-9]+$ ]] || signal=0
            bars=$((signal / 20))
            bar_str=""
            for ((i=0; i<bars; i++)); do bar_str+="█"; done
            for ((i=bars; i<5; i++)); do bar_str+="░"; done

            lock="  "
            [ -n "$security" ] && [ "$security" != "--" ] && [ "$security" != "" ] && lock="🔒"

            printf "    %2d. %s %-32s %s %3s%%  %s\n" "$NUM" "$lock" "$ssid" "$bar_str" "$signal" "$security"

            [ "$NUM" -ge 20 ] && break
        done <<< "$NETWORKS"

        echo ""
        echo "     r = rescan   s = skip"
        echo ""
        echo -n "  Network number: "
        read -r choice

        case "$choice" in
            r|R)
                echo ""
                echo "  Rescanning..."
                echo ""
                unset SEEN_SSIDS
                nmcli device wifi rescan 2>/dev/null
                sleep 3
                continue
                ;;
            s|S|skip)
                echo "  Continuing offline."
                echo ""
                return 1
                ;;
        esac

        # Validate choice
        if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "$NUM" ]; then
            echo "  Invalid choice."
            echo ""
            unset SEEN_SSIDS
            continue
        fi

        idx=$((choice - 1))
        ssid="${SSID_LIST[$idx]}"
        security="${SEC_LIST[$idx]}"

        echo ""
        echo "  Connecting to $ssid..."

        # Try saved connection first
        if nmcli connection up "$ssid" 2>/dev/null; then
            sleep 2
            if check_internet; then
                echo "  ✓ Connected to $ssid"
                echo ""
                return 0
            fi
            echo "  ✓ Connected (no internet yet)"
            echo ""
            return 0
        fi

        # Need password
        if [ -n "$security" ] && [ "$security" != "--" ] && [ "$security" != "Open" ]; then
            echo -n "  Password for $ssid: "
            read -rs password
            echo ""

            if [ -z "$password" ]; then
                echo "  Skipped."
                echo ""
                unset SEEN_SSIDS
                continue
            fi

            echo "  Connecting..."
            if nmcli device wifi connect "$ssid" password "$password" 2>/dev/null; then
                sleep 2
                if check_internet; then
                    echo "  ✓ Connected to $ssid"
                    echo ""
                    return 0
                fi
                # Give it more time
                for i in 1 2 3; do
                    sleep 2
                    if check_internet; then
                        echo "  ✓ Connected to $ssid"
                        echo ""
                        return 0
                    fi
                done
                echo "  ⚠ Connected but no internet. May need captive portal."
                echo ""
                return 0
            else
                echo "  ✗ Connection failed — wrong password?"
                echo -n "  Try another network? (Y/n): "
                read -r yn
                if [ "$yn" = "n" ] || [ "$yn" = "N" ]; then
                    echo "  Continuing offline."
                    echo ""
                    return 1
                fi
                echo ""
                unset SEEN_SSIDS
                continue
            fi
        else
            # Open network
            if nmcli device wifi connect "$ssid" 2>/dev/null; then
                sleep 2
                echo "  ✓ Connected to $ssid"
                echo ""
                return 0
            else
                echo "  ✗ Connection failed."
                unset SEEN_SSIDS
                continue
            fi
        fi
    done
}

wifi_setup

# ─── Early Claude Code install + login ────────────────────────
# P0: The user MUST get a Claude login prompt ASAP after first boot.
# Install the CLI and launch login terminal NOW, before hardware detection
# and the wizard. Full MCP/commands config happens later in setup_claude_code().
early_claude_login() {
    echo "→ Installing Claude Code CLI (for login prompt)..."

    if command -v claude &>/dev/null; then
        echo "  ✓ Claude Code already installed"
    elif ! check_internet; then
        echo "  ⚠ No internet — Claude Code install deferred to later"
        return
    elif command -v npm &>/dev/null; then
        # Try global install with sudo (non-interactive)
        if sudo -n npm install -g @anthropic-ai/claude-code 2>/dev/null; then
            echo "  ✓ Claude Code installed globally"
        else
            # sudo requires password — install to user prefix instead
            echo "  Installing to user prefix (~/.local)..."
            mkdir -p "$HOME/.local/lib/npm"
            npm config set prefix "$HOME/.local"
            npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
            export PATH="$HOME/.local/bin:$PATH"
        fi
    else
        echo "  ⚠ npm not found — Claude Code install deferred to later"
        return
    fi

    if ! command -v claude &>/dev/null; then
        echo "  ⚠ Claude Code not available after install attempt"
        return
    fi

    # Ensure Firefox is default browser for OAuth
    if command -v firefox &>/dev/null; then
        xdg-settings set default-web-browser firefox.desktop 2>/dev/null || true
    fi

    # Create the login script
    local CLAUDE_LOGIN="$HOME/.config/costa/scripts/claude-login.sh"
    mkdir -p "$(dirname "$CLAUDE_LOGIN")"
    cat > "$CLAUDE_LOGIN" << 'LOGINEOF'
#!/bin/bash
# Ensure user-local npm bin is in PATH (claude may be installed there)
export PATH="$HOME/.local/bin:$PATH"
clear
echo "╔══════════════════════════════════════════════════════╗"
echo "║           Claude Code — First-Time Login            ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                     ║"
echo "║  Claude Code needs authentication for AI features.  ║"
echo "║                                                     ║"
echo "║  Options:                                           ║"
echo "║    1. Anthropic Plan (recommended)                  ║"
echo "║       Free with Pro/Team/Enterprise subscription.   ║"
echo "║       Uses browser-based OAuth login.               ║"
echo "║                                                     ║"
echo "║    2. API Key (pay-per-use)                         ║"
echo "║       Set ANTHROPIC_API_KEY in ~/.config/costa/env  ║"
echo "║                                                     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo -n "Log in now? (Y/n): "
read -r choice
if [ "${choice:-y}" != "n" ] && [ "${choice:-y}" != "N" ]; then
    echo ""
    echo "Starting Claude Code — complete the browser login, then type /exit"
    echo ""
    claude --no-update-check
fi
# Remove the autostart trigger after first run
rm -f ~/.config/hypr/costa-claude-login.conf
echo ""
echo "You can always log in later by running: claude"
echo "Press Enter to close..."
read
LOGINEOF
    chmod +x "$CLAUDE_LOGIN"

    # Find a working terminal emulator (ghostty preferred, with fallbacks)
    # Skip ghostty in VMs — it requires GPU acceleration and crashes on QXL/virtio-vga
    local IN_VM=""
    if systemd-detect-virt -q 2>/dev/null || grep -qi "hypervisor\|qemu\|kvm\|virtualbox\|vmware" /proc/cpuinfo 2>/dev/null; then
        IN_VM="1"
    fi

    local TERM_CMD=""
    for term in ghostty foot kitty alacritty; do
        # Skip ghostty in VMs — requires GPU accel
        [ "$IN_VM" = "1" ] && [ "$term" = "ghostty" ] && continue
        if command -v "$term" &>/dev/null; then
            TERM_CMD="$term"
            break
        fi
    done

    if [ -z "$TERM_CMD" ]; then
        # No suitable terminal — create Hyprland autostart for next session
        # The user can also run `claude` manually from any terminal
        echo "  ⚠ No suitable terminal found for login prompt"
        echo "  ✓ Run 'claude' from any terminal to log in"
        return
    fi

    # Build the terminal exec command (each terminal has different -e syntax)
    local EXEC_CMD=""
    case "$TERM_CMD" in
        ghostty)    EXEC_CMD="ghostty -e $CLAUDE_LOGIN" ;;
        foot)       EXEC_CMD="foot $CLAUDE_LOGIN" ;;
        kitty)      EXEC_CMD="kitty $CLAUDE_LOGIN" ;;
        alacritty)  EXEC_CMD="alacritty -e $CLAUDE_LOGIN" ;;
    esac

    # Launch login terminal if Hyprland is running
    if command -v hyprctl &>/dev/null && hyprctl monitors &>/dev/null 2>&1; then
        echo "  → Launching Claude Code login terminal ($TERM_CMD)..."
        hyprctl dispatch exec "$EXEC_CMD" 2>/dev/null || true
        # Mark that we already launched — setup-claude-code.sh will skip the launch
        touch /tmp/costa-claude-login-launched
    else
        # Hyprland not running (shouldn't happen since first-boot runs from exec-once)
        # Create autostart as fallback
        local CLAUDE_AUTOSTART="$HOME/.config/hypr/costa-claude-login.conf"
        echo "exec-once = $EXEC_CMD" > "$CLAUDE_AUTOSTART"
        if ! grep -q "costa-claude-login.conf" "$HOME/.config/hypr/hyprland.conf" 2>/dev/null; then
            echo "" >> "$HOME/.config/hypr/hyprland.conf"
            echo "# Claude Code first-login (auto-removes after use)" >> "$HOME/.config/hypr/hyprland.conf"
            echo "source = ~/.config/hypr/costa-claude-login.conf" >> "$HOME/.config/hypr/hyprland.conf"
        fi
        echo "  ✓ Claude login will prompt on next Hyprland session"
    fi
}

early_claude_login

# ─── Detect monitors ─────────────────────────────────────────
detect_monitors() {
    echo "→ Detecting monitors..."
    MONITORS=$(hyprctl monitors -j 2>/dev/null || echo "[]")
    MON_COUNT=$(echo "$MONITORS" | jq 'length' 2>/dev/null || echo "0")

    if [ "$MON_COUNT" -eq 0 ]; then
        echo "  No monitors detected via hyprctl, using fallback"
        return
    fi

    # Generate monitor config lines
    MONITOR_CONF=""
    WORKSPACE_CONF=""
    WS=1

    while read name res pos; do
        echo "  Found: $name ($res at $pos)"
    done < <(echo "$MONITORS" | jq -r '.[] | "\(.name) \(.width)x\(.height)@\(.refreshRate) \(.x)x\(.y)"')

    # Write monitor-specific hyprland config
    MON_OVERRIDE="$HYPR_DIR/monitors.conf"
    echo "# Auto-generated by Costa OS first-boot" > "$MON_OVERRIDE"
    echo "# Edit this file to customize monitor layout" >> "$MON_OVERRIDE"
    echo "" >> "$MON_OVERRIDE"

    echo "$MONITORS" | jq -r '.[] | "monitor = \(.name), \(.width)x\(.height)@\(.refreshRate | floor), \(.x)x\(.y), 1"' >> "$MON_OVERRIDE"
    echo "" >> "$MON_OVERRIDE"

    # Assign workspaces: first 4 to primary, rest distributed
    PRIMARY=$(echo "$MONITORS" | jq -r '.[0].name')
    echo "workspace = 1, monitor:$PRIMARY, default:true" >> "$MON_OVERRIDE"
    echo "workspace = 2, monitor:$PRIMARY" >> "$MON_OVERRIDE"
    echo "workspace = 3, monitor:$PRIMARY" >> "$MON_OVERRIDE"
    echo "workspace = 4, monitor:$PRIMARY" >> "$MON_OVERRIDE"

    WS=5
    while read name; do
        echo "workspace = $WS, monitor:$name" >> "$MON_OVERRIDE"
        WS=$((WS + 1))
    done < <(echo "$MONITORS" | jq -r '.[1:][].name' 2>/dev/null)

    # Add source line to hyprland.conf if not already there
    if ! grep -q "monitors.conf" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
        sed -i '/^monitor = , preferred/a source = ~/.config/hypr/monitors.conf' "$HYPR_DIR/hyprland.conf"
    fi

    echo "  Saved monitor config to $MON_OVERRIDE"
}

# ─── Detect GPU and set hwmon paths ──────────────────────────
detect_gpu() {
    echo "→ Detecting GPU..."
    GPU_VENDOR=""

    if lspci | grep -qi "AMD.*VGA\|Radeon"; then
        GPU_VENDOR="amd"
        GPU_NAME=$(lspci | grep -i "VGA\|3D" | grep -i AMD | head -1 | sed 's/.*: //')
        echo "  AMD GPU: $GPU_NAME"

        # Find GPU sysfs paths
        GPU_BUSY=$(find /sys/class/drm/card*/device/gpu_busy_percent 2>/dev/null | head -1)
        GPU_VRAM_USED=$(find /sys/class/drm/card*/device/mem_info_vram_used 2>/dev/null | head -1)
        GPU_VRAM_TOTAL=$(find /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null | head -1)
        GPU_TEMP=$(find /sys/class/drm/card*/device/hwmon/hwmon*/temp1_input 2>/dev/null | head -1)

        VRAM_BYTES=$(cat "$GPU_VRAM_TOTAL" 2>/dev/null || echo "0")
        VRAM_GB=$(( VRAM_BYTES / 1024 / 1024 / 1024 ))
        echo "  VRAM: ${VRAM_GB}GB"

    elif lspci | grep -qi "NVIDIA"; then
        GPU_VENDOR="nvidia"
        GPU_NAME=$(lspci | grep -i "VGA\|3D" | grep -i NVIDIA | head -1 | sed 's/.*: //')
        echo "  NVIDIA GPU: $GPU_NAME"
        VRAM_GB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        VRAM_GB=$(( ${VRAM_GB:-0} / 1024 ))

    elif lspci | grep -qi "Intel.*VGA\|Intel.*Graphics"; then
        GPU_VENDOR="intel"
        GPU_NAME=$(lspci | grep -i "VGA\|3D" | grep -i Intel | head -1 | sed 's/.*: //')
        echo "  Intel GPU: $GPU_NAME"
        VRAM_GB=0
    else
        # VM or unknown GPU (Virtio, QEMU, VMware, etc.)
        GPU_VENDOR=""
        GPU_NAME=$(lspci | grep -i "VGA\|3D" | head -1 | sed 's/.*: //' || echo "Unknown")
        GPU_NAME="${GPU_NAME:-Unknown (VM)}"
        VRAM_GB=0
        echo "  No discrete GPU detected: $GPU_NAME"
    fi

    # Save GPU config for shell widgets and ollama-manager
    mkdir -p "$COSTA_DIR"
    cat > "$COSTA_DIR/gpu.conf" << EOF
GPU_VENDOR=$GPU_VENDOR
GPU_NAME=$GPU_NAME
GPU_BUSY_FILE=${GPU_BUSY:-}
GPU_VRAM_USED_FILE=${GPU_VRAM_USED:-}
GPU_VRAM_TOTAL_FILE=${GPU_VRAM_TOTAL:-}
GPU_TEMP_FILE=${GPU_TEMP:-}
VRAM_GB=${VRAM_GB:-0}
EOF
    echo "  Saved GPU config to $COSTA_DIR/gpu.conf"
}

# ─── Detect CPU temperature path ─────────────────────────────
detect_cpu_temp() {
    echo "→ Detecting CPU temperature sensor..."
    # Common paths for CPU temp
    for path in \
        /sys/devices/pci*/*/hwmon/hwmon*/temp1_input \
        /sys/class/hwmon/hwmon*/temp1_input \
        /sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input; do
        if [ -f "$path" ] 2>/dev/null; then
            # Verify it's actually a CPU sensor (not GPU)
            HWMON_DIR=$(dirname "$path")
            SENSOR_NAME=$(cat "$HWMON_DIR/name" 2>/dev/null || echo "unknown")
            if echo "$SENSOR_NAME" | grep -qi "k10temp\|coretemp\|cpu\|zenpower"; then
                echo "  CPU temp: $path ($SENSOR_NAME)"
                echo "CPU_TEMP_FILE=$path" >> "$COSTA_DIR/gpu.conf"
                return
            fi
        fi
    done
    echo "  No CPU temperature sensor found"
}

# ─── Detect IR camera (face auth) ─────────────────────────────
detect_ir_camera() {
    echo "→ Detecting IR camera..."
    IR_CAMERA=""

    if ! command -v v4l2-ctl &>/dev/null; then
        echo "  v4l-utils not installed, skipping IR detection"
        return
    fi

    for dev in /dev/video*; do
        [ -e "$dev" ] || continue
        INFO=$(v4l2-ctl --device="$dev" --all 2>/dev/null || true)
        if echo "$INFO" | grep -qi "infrared\|IR camera\|Windows Hello\|IR Emitter"; then
            IR_CAMERA="$dev"
            echo "  IR camera found: $dev"
            echo "IR_CAMERA=$IR_CAMERA" >> "$COSTA_DIR/gpu.conf"
            return
        fi
        # Check by known IR camera USB names
        CARD=$(echo "$INFO" | grep "Card type" | head -1 || true)
        if echo "$CARD" | grep -qi "IR\b\|infrared\|Tobii\|RealSense\|Hello"; then
            IR_CAMERA="$dev"
            echo "  IR camera found: $dev ($CARD)"
            echo "IR_CAMERA=$IR_CAMERA" >> "$COSTA_DIR/gpu.conf"
            return
        fi
    done
    echo "  No IR camera detected"
}

# ─── Detect touchscreen ──────────────────────────────────────
detect_touchscreen() {
    echo "→ Detecting touchscreen..."
    HAS_TOUCHSCREEN=false
    TOUCHSCREEN_NAME=""

    if ! command -v libinput &>/dev/null && ! [ -x /usr/bin/libinput ]; then
        echo "  libinput not found, skipping touchscreen detection"
        return
    fi

    TOUCH_DEV=$( (sudo -n libinput list-devices 2>/dev/null || libinput list-devices 2>/dev/null) | awk '
        /Device:/ { name=$0; sub(/.*Device: */, "", name) }
        /Capabilities:.*touch/ { print name; exit }
    ')

    if [ -n "$TOUCH_DEV" ]; then
        HAS_TOUCHSCREEN=true
        TOUCHSCREEN_NAME="$TOUCH_DEV"
        echo "  Touchscreen found: $TOUCHSCREEN_NAME"
        echo "HAS_TOUCHSCREEN=true" >> "$COSTA_DIR/gpu.conf"
        echo "TOUCHSCREEN_NAME=\"$TOUCHSCREEN_NAME\"" >> "$COSTA_DIR/gpu.conf"
    else
        echo "  No touchscreen detected"
    fi
}

# ─── Generate system-ai.md for local model ───────────────────
generate_system_prompt() {
    echo "→ Generating AI system prompt..."

    source "$COSTA_DIR/gpu.conf" 2>/dev/null
    CPU_MODEL=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
    RAM_GB=$(free -g | awk '/Mem:/ {print $2}')
    HOSTNAME=$(cat /etc/hostname 2>/dev/null || echo "costa")
    USERNAME=$(whoami)

    cat > "$COSTA_DIR/system-ai.md" << SYSEOF
You are the Costa OS assistant running on $USERNAME's workstation ($HOSTNAME).
You run locally via Ollama. Be concise and direct. Give actionable answers.

## System
- OS: Costa OS (Arch Linux + Hyprland)
- CPU: $CPU_MODEL
- RAM: ${RAM_GB}GB
- GPU: ${GPU_NAME:-unknown} (${VRAM_GB:-0}GB VRAM)
- Shell: zsh
- Terminal: Ghostty
- File manager: Thunar
- Browser: Firefox

## What You Can Do
When the user asks you to DO something (change volume, restart a service, open an app),
output the exact command they need. If a command is safe, it will be auto-executed.

Safe commands (auto-execute): wpctl, hyprctl, playerctl, brightnessctl, systemctl (status/restart for user services), pacman -Q
Dangerous commands (NEVER suggest without warning): rm -rf, dd, mkfs, shutdown, reboot, pacman -Rns

## Response Format
- Be concise — 1-3 sentences for simple questions
- For commands: just give the command, don't explain unless asked
- For errors: suggest the fix, don't just describe the problem
- If you don't know something about THIS system, say so — don't guess
SYSEOF

    echo "  Generated system prompt for $USERNAME@$HOSTNAME"
}

# ─── Set timezone from installer config ───────────────────────
apply_timezone() {
    if [ -f "$COSTA_DIR/config.json" ]; then
        TZ=$(jq -r '.timezone // "UTC"' "$COSTA_DIR/config.json")
    else
        TZ=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "UTC")
    fi
    echo "→ Setting timezone: $TZ"
    sudo -n timedatectl set-timezone "$TZ" 2>/dev/null || \
        sudo -n ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime 2>/dev/null || true
}

# ─── Install and set up Claude Code ──────────────────────────
setup_claude_code() {
    echo "→ Configuring Claude Code (MCP server, commands, CLAUDE.md)..."

    # CLI should already be installed by early_claude_login().
    # If not (e.g., early install failed), try again.
    if ! command -v claude &>/dev/null; then
        echo "  Claude Code CLI not found — retrying install..."
        if command -v npm &>/dev/null; then
            if sudo -n npm install -g @anthropic-ai/claude-code 2>/dev/null; then
                echo "  ✓ Claude Code installed globally"
            else
                mkdir -p "$HOME/.local/lib/npm"
                npm config set prefix "$HOME/.local"
                npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
                export PATH="$HOME/.local/bin:$PATH"
            fi
        else
            echo "  ⚠ npm not found — cannot install Claude Code"
            return
        fi
    fi

    # Run the full setup (MCP server, commands, CLAUDE.md, hooks)
    # Login terminal was already launched by early_claude_login() — setup script will skip it
    SETUP_SCRIPT="/usr/share/costa-os/scripts/setup-claude-code.sh"
    if [ -f "$SETUP_SCRIPT" ]; then
        bash "$SETUP_SCRIPT"
    else
        echo "  Setup script not found at $SETUP_SCRIPT, skipping"
    fi
}

# ─── Ensure directories exist ─────────────────────────────────
mkdir -p "$COSTA_DIR" "$COSTA_DIR/knowledge" "$COSTA_DIR/agents" "$COSTA_DIR/workflows" "$COSTA_DIR/projects" "$HYPR_DIR" "$AGS_DIR"
mkdir -p ~/Pictures/Screenshots

# ─── Set up Obsidian vault (Claude's persistent knowledge) ────
NOTES_DIR="$HOME/notes"
if [ ! -d "$NOTES_DIR" ]; then
    echo "→ Creating Obsidian vault at $NOTES_DIR..."
    mkdir -p "$NOTES_DIR"/{projects,feedback,reference,daily,costa-os,architecture}
    mkdir -p "$NOTES_DIR/.obsidian"

    # Seed the vault with a welcome note
    cat > "$NOTES_DIR/Welcome.md" << 'NOTESEOF'
# Costa OS Knowledge Vault

This is your **Obsidian vault** — Claude's persistent memory and your personal knowledge base.

## How It Works

Claude Code has direct read/write access to this vault via MCP. It uses this space to:

- **Remember your preferences** — coding style, tool choices, workflow corrections
- **Track project context** — what you're working on, decisions made, blockers
- **Store references** — links to docs, dashboards, API endpoints
- **Keep daily notes** — session logs, things learned, ideas

## Folder Structure

| Folder | Purpose |
|--------|---------|
| `projects/` | Per-project context, goals, architecture notes |
| `feedback/` | Corrections and preferences for Claude's behavior |
| `reference/` | External links, API docs, dashboard URLs |
| `daily/` | Daily session notes and logs |
| `costa-os/` | Costa OS system decisions and configuration notes |
| `architecture/` | System design, technical trade-offs |

## Tips

- You can browse and edit these notes in Obsidian (the app) or any text editor
- Claude will read relevant notes before responding to give better answers
- Ask Claude to "remember this" and it will save a note here
- Ask Claude to "check your notes about X" and it will search the vault
NOTESEOF

    # Obsidian settings — minimal, clean defaults
    cat > "$NOTES_DIR/.obsidian/app.json" << 'OBSEOF'
{
  "theme": "obsidian",
  "baseFontSize": 16,
  "alwaysUpdateLinks": true,
  "newFileLocation": "folder",
  "newFileFolderPath": "daily",
  "showLineNumber": true,
  "spellcheck": true
}
OBSEOF

    echo "  ✓ Obsidian vault created at $NOTES_DIR"
else
    echo "  Obsidian vault already exists at $NOTES_DIR"
fi

# ─── Copy shipped knowledge files ─────────────────────────────
SHIPPED_KNOWLEDGE="/usr/share/costa-os/knowledge"
if [ -d "$SHIPPED_KNOWLEDGE" ]; then
    cp -n "$SHIPPED_KNOWLEDGE"/*.md "$COSTA_DIR/knowledge/" 2>/dev/null
    KNOWLEDGE_COUNT=$(ls "$COSTA_DIR/knowledge/"*.md 2>/dev/null | wc -l)
    echo "  ✓ Knowledge base installed ($KNOWLEDGE_COUNT files)"
fi

# ─── Copy shipped ML router model ────────────────────────────
SHIPPED_MODEL="/usr/share/costa-os/ai-router/models/ml_router.pt"
if [ -f "$SHIPPED_MODEL" ] && [ ! -f "$COSTA_DIR/ml_router.pt" ]; then
    cp "$SHIPPED_MODEL" "$COSTA_DIR/ml_router.pt"
    echo "  ✓ Pre-trained ML router model installed"
fi

# ─── Copy shipped agent configs ──────────────────────────────
SHIPPED_AGENTS="/usr/share/costa-os/configs/costa/agents"
if [ -d "$SHIPPED_AGENTS" ]; then
    cp -n "$SHIPPED_AGENTS"/*.yaml "$COSTA_DIR/agents/" 2>/dev/null
    echo "  ✓ Agent configs installed"
fi

# ─── Copy shipped workflow configs ───────────────────────────
SHIPPED_WORKFLOWS="/usr/share/costa-os/configs/costa/workflows"
if [ -d "$SHIPPED_WORKFLOWS" ]; then
    cp -n "$SHIPPED_WORKFLOWS"/*.yaml "$COSTA_DIR/workflows/" 2>/dev/null
    echo "  ✓ Workflow configs installed"
fi

# ─── Install GPU drivers based on detected vendor ────────────
install_gpu_drivers() {
    if [ -z "$GPU_VENDOR" ]; then
        echo "  No GPU vendor detected, skipping driver install"
        return
    fi

    echo "→ Installing GPU drivers for $GPU_VENDOR..."
    case "$GPU_VENDOR" in
        amd)
            sudo -n pacman -S --noconfirm --needed vulkan-radeon lib32-vulkan-radeon 2>&1 | tail -1
            ;;
        nvidia)
            sudo -n pacman -S --noconfirm --needed nvidia nvidia-utils lib32-nvidia-utils 2>&1 | tail -1
            ;;
        intel)
            sudo -n pacman -S --noconfirm --needed vulkan-intel 2>&1 | tail -1
            ;;
    esac
    echo "  GPU drivers installed"
}

# ─── Run detection ────────────────────────────────────────────
detect_monitors
detect_gpu
install_gpu_drivers
detect_cpu_temp
detect_ir_camera
detect_touchscreen
generate_system_prompt

# ─── Run installer wizard if config doesn't exist ─────────────
if [ ! -f "$COSTA_DIR/config.json" ]; then
    echo ""
    echo "→ Launching Costa OS setup wizard..."
    python3 /usr/share/costa-os/installer/wizard.py
fi

# Apply timezone AFTER wizard (so config.json exists with user's choice)
apply_timezone

# ─── Set up Claude Code system knowledge ─────────────────────
setup_claude_code

# ─── Apply keybind configuration ──────────────────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    echo "→ Applying keybind configuration..."

    # Voice PTT keybind
    PTT_MODS=$(jq -r '.ptt_keybind[0] // "$mainMod ALT"' "$COSTA_DIR/config.json")
    PTT_KEY=$(jq -r '.ptt_keybind[1] // "V"' "$COSTA_DIR/config.json")
    sed -i "s|bind = \$mainMod ALT, V, exec, bash -c 'PTT_MODE=claude.*|bind = $PTT_MODS, $PTT_KEY, exec, bash -c 'PTT_MODE=claude ~/.config/hypr/push-to-talk.sh'|" "$HYPR_DIR/hyprland.conf"

    # Store API keys in environment file
    echo "→ Configuring API keys..."
    ENV_FILE="$COSTA_DIR/env"
    echo "# Costa OS service credentials (sourced by costa-ai and voice assistant)" > "$ENV_FILE"

    ANTHROPIC_KEY=$(jq -r '.anthropic_api_key // ""' "$COSTA_DIR/config.json")
    [ -n "$ANTHROPIC_KEY" ] && echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY" >> "$ENV_FILE"

    OPENAI_KEY=$(jq -r '.openai_api_key // ""' "$COSTA_DIR/config.json")
    [ -n "$OPENAI_KEY" ] && echo "OPENAI_API_KEY=$OPENAI_KEY" >> "$ENV_FILE"

    chmod 600 "$ENV_FILE"
    echo "  Saved to $ENV_FILE (mode 600)"

    # Source env file from zshrc if not already
    if ! grep -q "costa/env" ~/.zshrc 2>/dev/null; then
        echo "" >> ~/.zshrc
        echo "# Costa OS API keys" >> ~/.zshrc
        echo '[ -f ~/.config/costa/env ] && source ~/.config/costa/env' >> ~/.zshrc
    fi
fi

# ─── Install Ollama models based on AI tier ───────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    AI_TIER=$(jq -r '.ai_tier // "CLOUD_ONLY"' "$COSTA_DIR/config.json")
    if [ "$AI_TIER" != "CLOUD_ONLY" ] && command -v ollama &>/dev/null; then
        SMART_MODEL=$(jq -r '.ollama_smart_model // "qwen2.5:3b"' "$COSTA_DIR/config.json")
        echo "→ Pulling AI model: $SMART_MODEL (this may take a while)..."
        ollama pull "$SMART_MODEL" 2>&1 | tail -1
        echo "$SMART_MODEL" > /tmp/ollama-smart-model
    fi
fi

# ─── Install CLI-Anything wrappers for costa-nav fast path ────
COSTA_SHARE="/usr/share/costa-os"
if [ -d "$COSTA_SHARE/cli-wrappers" ]; then
    echo "→ Installing CLI-Anything wrappers for app navigation..."
    INSTALLED_COUNT=0
    for wrapper_dir in "$COSTA_SHARE"/cli-wrappers/*/; do
        if [ -f "$wrapper_dir/setup.py" ]; then
            wrapper_name=$(basename "$wrapper_dir")
            # Only install if the target app is actually installed
            case "$wrapper_name" in
                firefox)    command -v firefox &>/dev/null || continue ;;
                thunar)     command -v thunar &>/dev/null || continue ;;
                gimp)       command -v gimp &>/dev/null || continue ;;
                inkscape)   command -v inkscape &>/dev/null || continue ;;
                krita)      command -v krita &>/dev/null || continue ;;
                audacity)   command -v audacity &>/dev/null || continue ;;
                obs-studio) command -v obs &>/dev/null || continue ;;
                code)       command -v code &>/dev/null || continue ;;
                mpv)        command -v mpv &>/dev/null || continue ;;
                strawberry) command -v strawberry &>/dev/null || continue ;;
                steam)      command -v steam &>/dev/null || continue ;;

            esac
            # Use uv if available (fast), fall back to pip with --break-system-packages
            if command -v uv &>/dev/null; then
                uv pip install --system --break-system-packages -e "$wrapper_dir" 2>&1 | tail -1 || true
            else
                pip install --user --break-system-packages -e "$wrapper_dir" 2>&1 | tail -1 || true
            fi
            INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
        fi
    done
    echo "  Installed $INSTALLED_COUNT CLI wrappers"

    # Initialize CLI registry
    if [ -f "$COSTA_SHARE/configs/costa/cli-registry.json" ]; then
        cp "$COSTA_SHARE/configs/costa/cli-registry.json" "$COSTA_DIR/cli-registry.json"
    fi

    # Refresh registry to detect installed wrappers
    python3 -c "
import sys; sys.path.insert(0, '$COSTA_SHARE/ai-router')
from cli_registry import refresh_registry
refresh_registry()
" 2>/dev/null || true
fi

# ─── Install AUR packages (fallback — primary install is in costa-install) ──
if command -v yay &>/dev/null; then
    echo "→ Checking for AUR packages..."
    AUR_PKGS=()

    # Core AUR packages — only install if not already present
    command -v ags &>/dev/null || AUR_PKGS+=(aylurs-gtk-shell libastal-hyprland-git libastal-mpris-git libastal-battery-git)

    # Read additional AUR packages from config.json if the field exists
    if [ -f "$COSTA_DIR/config.json" ]; then
        while read pkg; do
            [ -n "$pkg" ] && AUR_PKGS+=("$pkg")
        done < <(jq -r '.aur_packages[]? // empty' "$COSTA_DIR/config.json" 2>/dev/null)
    fi

    # Also scan base.txt for lines marked with # AUR
    COSTA_SHARE="/usr/share/costa-os"
    if [ -f "$COSTA_SHARE/packages/base.txt" ]; then
        while read pkg; do
            [ -n "$pkg" ] && AUR_PKGS+=("$pkg")
        done < <(grep '# AUR' "$COSTA_SHARE/packages/base.txt" | sed 's/\s*#.*//' | tr -s ' ')
    fi

    if [ ${#AUR_PKGS[@]} -gt 0 ]; then
        echo "  Installing AUR packages: ${AUR_PKGS[*]}"
        yay -S --noconfirm --answerdiff=None --answerclean=None --removemake "${AUR_PKGS[@]}" 2>&1 | tail -3 || true
    else
        echo "  No AUR packages to install"
    fi
else
    echo "→ yay not installed, skipping AUR packages"
fi

# ─── Link AGS shell dependencies if needed ───────────────────
if [ -f "$HOME/.config/ags/package.json" ] && [ ! -L "$HOME/.config/ags/node_modules/ags" ]; then
    echo "→ Linking AGS shell dependencies..."
    mkdir -p "$HOME/.config/ags/node_modules"
    ln -sf /usr/share/ags/js "$HOME/.config/ags/node_modules/ags" 2>/dev/null || true
    [ -d /usr/share/ags/js/node_modules/gnim ] && \
        ln -sf /usr/share/ags/js/node_modules/gnim "$HOME/.config/ags/node_modules/gnim" 2>/dev/null || true
    echo "  ✓ AGS modules linked"
fi

# ─── Install optional package tiers ──────────────────────────
COSTA_SHARE="/usr/share/costa-os"
if [ -f "$COSTA_DIR/config.json" ]; then
    INSTALL_DEV=$(jq -r '.install_dev_tools // false' "$COSTA_DIR/config.json")
    INSTALL_CREATIVE=$(jq -r '.install_creative // false' "$COSTA_DIR/config.json")
    INSTALL_GAMING=$(jq -r '.install_gaming // false' "$COSTA_DIR/config.json")

    # ── Dev tools ──
    if [ "$INSTALL_DEV" = "true" ]; then
        echo "→ Installing developer tools..."

        # Official repo packages from dev.txt
        if [ -f "$COSTA_SHARE/packages/dev.txt" ]; then
            OFFICIAL_PKGS=()
            AUR_DEV_PKGS=()
            while IFS= read -r line; do
                line=$(echo "$line" | sed 's/#.*//' | tr -s ' ' | xargs)
                [ -z "$line" ] && continue
                if echo "$line" | grep -qi "AUR"; then
                    pkg=$(echo "$line" | awk '{print $1}')
                    AUR_DEV_PKGS+=("$pkg")
                else
                    OFFICIAL_PKGS+=("$line")
                fi
            done < "$COSTA_SHARE/packages/dev.txt"

            if [ ${#OFFICIAL_PKGS[@]} -gt 0 ]; then
                echo "  pacman: ${OFFICIAL_PKGS[*]}"
                sudo -n pacman -S --noconfirm --needed "${OFFICIAL_PKGS[@]}" 2>&1 | tail -3 || true
            fi
            if [ ${#AUR_DEV_PKGS[@]} -gt 0 ] && command -v yay &>/dev/null; then
                echo "  AUR: ${AUR_DEV_PKGS[*]}"
                yay -S --noconfirm --answerdiff=None --answerclean=None --removemake "${AUR_DEV_PKGS[@]}" 2>&1 | tail -3 || true
            fi
        fi

        # PostgreSQL
        echo "  Installing PostgreSQL..."
        sudo -n pacman -S --noconfirm --needed postgresql 2>&1 | tail -1 || true
        if [ ! -d /var/lib/postgres/data ] || [ -z "$(ls -A /var/lib/postgres/data 2>/dev/null)" ]; then
            sudo -n -u postgres initdb -D /var/lib/postgres/data 2>&1 | tail -1 || true
        fi
        sudo -n systemctl enable --now postgresql 2>&1 | tail -1 || true

        # Redis
        echo "  Installing Redis..."
        sudo -n pacman -S --noconfirm --needed redis 2>&1 | tail -1 || true
        sudo -n systemctl enable --now redis 2>&1 | tail -1 || true

        # Version managers (user-level, no sudo)
        echo "  Setting up version managers..."

        # pyenv
        if [ ! -d "$HOME/.pyenv" ]; then
            echo "    Installing pyenv..."
            curl -sS https://pyenv.run 2>/dev/null | bash 2>&1 | tail -1 || true
        fi

        # nvm
        if [ ! -d "$HOME/.nvm" ]; then
            echo "    Installing nvm..."
            curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh 2>/dev/null | bash 2>&1 | tail -1 || true
        fi

        # SDKMAN
        if [ ! -d "$HOME/.sdkman" ]; then
            echo "    Installing SDKMAN..."
            curl -s "https://get.sdkman.io?rcupdate=false" 2>/dev/null | bash 2>&1 | tail -1 || true
        fi

        # Rust
        if ! command -v rustup &>/dev/null; then
            echo "    Installing Rust..."
            curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs 2>/dev/null | sh -s -- -y 2>&1 | tail -1 || true
        fi

        echo "  ✓ Developer tools installed"
    fi

    # ── Creative tools ──
    if [ "$INSTALL_CREATIVE" = "true" ]; then
        echo "→ Installing creative tools..."
        if [ -f "$COSTA_SHARE/packages/creative.txt" ]; then
            CREATIVE_PKGS=()
            while IFS= read -r line; do
                line=$(echo "$line" | sed 's/#.*//' | tr -s ' ' | xargs)
                [ -z "$line" ] && continue
                CREATIVE_PKGS+=("$line")
            done < "$COSTA_SHARE/packages/creative.txt"
            if [ ${#CREATIVE_PKGS[@]} -gt 0 ]; then
                sudo -n pacman -S --noconfirm --needed "${CREATIVE_PKGS[@]}" 2>&1 | tail -3 || true
            fi
        fi
        echo "  ✓ Creative tools installed"
    fi

    # ── Gaming ──
    if [ "$INSTALL_GAMING" = "true" ]; then
        echo "→ Installing gaming packages..."
        if [ -f "$COSTA_SHARE/packages/gaming.txt" ]; then
            GAMING_PKGS=()
            while IFS= read -r line; do
                line=$(echo "$line" | sed 's/#.*//' | tr -s ' ' | xargs)
                [ -z "$line" ] && continue
                GAMING_PKGS+=("$line")
            done < "$COSTA_SHARE/packages/gaming.txt"
            if [ ${#GAMING_PKGS[@]} -gt 0 ]; then
                sudo -n pacman -S --noconfirm --needed "${GAMING_PKGS[@]}" 2>&1 | tail -3 || true
            fi
        fi
        echo "  ✓ Gaming packages installed"
    fi
fi

# ─── Face auth setup (howdy) ──────────────────────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    ENABLE_FACE=$(jq -r '.enable_face_auth // false' "$COSTA_DIR/config.json")
    source "$COSTA_DIR/gpu.conf" 2>/dev/null
    if [ "$ENABLE_FACE" = "true" ] && [ -n "$IR_CAMERA" ]; then
        echo "→ Setting up face authentication (howdy)..."
        if command -v yay &>/dev/null; then
            yay -S --noconfirm --answerdiff=None --answerclean=None --removemake howdy 2>&1 | tail -3 || true

            # Configure howdy to use detected IR camera
            HOWDY_CONF="/lib/security/howdy/config.ini"
            if [ -f "$HOWDY_CONF" ]; then
                sudo -n sed -i "s|^device_path.*|device_path = $IR_CAMERA|" "$HOWDY_CONF"
                echo "  Set howdy device to $IR_CAMERA"
            fi

            # Add howdy to PAM configs (as 'sufficient' — password always works as fallback)
            HOWDY_PAM="auth sufficient pam_python.so /lib/security/howdy/pam.py"
            for pam_file in /etc/pam.d/greetd /etc/pam.d/sudo /etc/pam.d/hyprlock; do
                if [ -f "$pam_file" ] && ! grep -q "howdy" "$pam_file"; then
                    sudo -n sed -i "1a $HOWDY_PAM" "$pam_file"
                    echo "  Added howdy to $(basename $pam_file)"
                fi
            done

            echo "  ✓ Face auth configured"
            echo "  → Enroll your face with: sudo howdy add"
            echo "  → Test with: sudo howdy test"
        else
            echo "  yay not available — install howdy manually: yay -S howdy"
        fi
    fi
fi

# ─── Touchscreen setup ───────────────────────────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    ENABLE_TOUCH=$(jq -r '.enable_touchscreen // false' "$COSTA_DIR/config.json")
    source "$COSTA_DIR/gpu.conf" 2>/dev/null
    if [ "$ENABLE_TOUCH" = "true" ] && [ "$HAS_TOUCHSCREEN" = "true" ]; then
        echo "→ Setting up touchscreen support..."

        # Generate touch.conf for Hyprland
        TOUCH_CONF="$HYPR_DIR/touch.conf"
        cat > "$TOUCH_CONF" << 'TOUCHEOF'
# Costa OS — Touchscreen Configuration (auto-generated)

input {
    touchdevice {
        enabled = true
        transform = 0
    }
}

# hyprgrass touch gestures (requires hyprgrass plugin)
plugin {
    touch_gestures {
        sensitivity = 4.0

        # Swipe gestures
        hyprgrass-bind = , swipe:3:u, exec, rofi -show drun
        hyprgrass-bind = , swipe:3:d, killactive
        hyprgrass-bind = , swipe:3:l, workspace, e+1
        hyprgrass-bind = , swipe:3:r, workspace, e-1
        hyprgrass-bind = , swipe:4:u, fullscreen, 0
        hyprgrass-bind = , swipe:4:d, togglefloating

        # Long press for right-click
        hyprgrass-bindm = , longpress:2, movewindow
    }
}
TOUCHEOF
        echo "  Generated $TOUCH_CONF"

        # Source touch.conf from hyprland.conf if not already
        if ! grep -q "touch.conf" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
            echo "source = ~/.config/hypr/touch.conf" >> "$HYPR_DIR/hyprland.conf"
        fi

        # Install squeekboard (on-screen keyboard) from official repos
        if ! pacman -Qi squeekboard &>/dev/null; then
            echo "  Installing squeekboard (on-screen keyboard)..."
            sudo -n pacman -S --noconfirm squeekboard 2>&1 | tail -1 || true
        fi

        # Add squeekboard autostart if not present
        if ! grep -q "squeekboard" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
            sed -i '/^exec-once.*ags/a exec-once = squeekboard' "$HYPR_DIR/hyprland.conf"
        fi

        # Install hyprgrass (touch gesture plugin) via AUR
        if command -v yay &>/dev/null; then
            if ! yay -Qi hyprgrass &>/dev/null 2>&1; then
                echo "  Installing hyprgrass (touch gestures)..."
                yay -S --noconfirm --answerdiff=None --answerclean=None --removemake hyprgrass 2>&1 | tail -3 || true
            fi
        fi

        echo "  ✓ Touchscreen configured (squeekboard + hyprgrass)"
    fi
fi

# ─── Install voice assistant dependencies ─────────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    AI_TIER=$(jq -r '.ai_tier // "CLOUD_ONLY"' "$COSTA_DIR/config.json")
    if [ "$AI_TIER" = "VOICE_AND_LLM" ] || [ "$AI_TIER" = "FULL_WORKSTATION" ]; then
        echo "→ Setting up voice assistant dependencies..."
        if command -v uv &>/dev/null; then
            uv pip install --system --break-system-packages torch numpy torchaudio 2>&1 | tail -1 || true
        else
            pip install --user --break-system-packages torch numpy torchaudio 2>&1 | tail -1 || true
        fi
        # whisper.cpp must be built from source — documented in voice-assistant/README.md
        echo "  Note: whisper.cpp requires manual build — see ~/.config/costa/voice-assistant/README.md"
    fi
fi

# ─── AI Navigation setup ─────────────────────────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    ENABLE_NAV=$(jq -r '.enable_ai_navigation // false' "$COSTA_DIR/config.json")
    if [ "$ENABLE_NAV" = "true" ]; then
        echo "→ Setting up AI Navigation..."

        # 1. Enable accessibility (required for AT-SPI screen reading)
        echo "  Enabling AT-SPI accessibility..."
        mkdir -p "$HOME/.config/environment.d"
        cat >> "$HOME/.config/environment.d/costa.conf" << 'ENVEOF'
MOZ_ENABLE_A11Y=1
GTK_A11Y=atspi
ENVEOF

        # Add a11y env to hyprland
        if ! grep -q "MOZ_ENABLE_A11Y" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
            # Insert after QT env vars
            sed -i '/QT_WAYLAND_DISABLE_WINDOWDECORATION/a\\n# Accessibility — lets Claude read app content without screenshots\nenv = GTK_A11Y,atspi\nenv = MOZ_ENABLE_A11Y,1' "$HYPR_DIR/hyprland.conf"
        fi

        # 2. Create headless virtual monitor for Claude
        echo "  Creating virtual headless monitor..."
        if ! grep -q "output create headless" "$HYPR_DIR/hyprland.conf" 2>/dev/null; then
            # Add after last exec-once line
            sed -i '/^exec-once.*$/a\\n# Claude'"'"'s virtual monitor — headless display for AI navigation\nexec-once = hyprctl output create headless' "$HYPR_DIR/hyprland.conf"
        fi

        # Create it now for current session
        hyprctl output create headless 2>/dev/null || true

        # Figure out which headless monitor was created and write config
        sleep 0.5
        HEADLESS_NAME=$(hyprctl monitors -j 2>/dev/null | jq -r '.[] | select(.name | startswith("HEADLESS")) | .name' | tail -1)
        HEADLESS_WS=$(hyprctl monitors -j 2>/dev/null | jq -r ".[] | select(.name == \"$HEADLESS_NAME\") | .activeWorkspace.name" 2>/dev/null)

        if [ -n "$HEADLESS_NAME" ]; then
            echo "  Virtual monitor: $HEADLESS_NAME (workspace $HEADLESS_WS)"

            # Write nav config so costa-nav picks it up
            cat > "$COSTA_DIR/nav.conf" << NAVEOF
# Costa AI Navigation — auto-generated by first-boot
COSTA_NAV_MONITOR=$HEADLESS_NAME
COSTA_NAV_WORKSPACE=$HEADLESS_WS
NAVEOF
            echo "  Saved nav config to $COSTA_DIR/nav.conf"

            # Add env vars to costa environment
            echo "COSTA_NAV_MONITOR=$HEADLESS_NAME" >> "$HOME/.config/environment.d/costa.conf"
            echo "COSTA_NAV_WORKSPACE=$HEADLESS_WS" >> "$HOME/.config/environment.d/costa.conf"
        else
            echo "  Warning: could not detect headless monitor name"
        fi

        # 3. Create Claude's browser profile directory
        echo "  Creating Claude browser profile..."
        CLAUDE_PROFILE="$COSTA_DIR/claude-browser-profile"
        mkdir -p "$CLAUDE_PROFILE"
        cat > "$CLAUDE_PROFILE/user.js" << 'JSEOF'
user_pref("accessibility.force_disabled", 0);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("datareporting.policy.dataSubmissionEnabled", false);
JSEOF

        # 4. Ensure Firefox user.js has a11y enabled for the user's profile too
        echo "  Enabling Firefox accessibility..."
        for profile_dir in "$HOME"/.config/mozilla/firefox/*.default* "$HOME"/.mozilla/firefox/*.default*; do
            if [ -d "$profile_dir" ]; then
                if ! grep -q "accessibility.force_disabled" "$profile_dir/user.js" 2>/dev/null; then
                    echo 'user_pref("accessibility.force_disabled", 0);' >> "$profile_dir/user.js"
                fi
            fi
        done

        # 5. Create nav-sites and nav-routines dirs
        mkdir -p "$COSTA_DIR/nav-sites" "$COSTA_DIR/nav-routines"

        # 6. Ensure at-spi2-core and python-gobject are installed
        if ! pacman -Qi at-spi2-core &>/dev/null; then
            echo "  Installing AT-SPI2..."
            sudo -n pacman -S --noconfirm at-spi2-core 2>&1 | tail -1
        fi
        if ! pacman -Qi python-gobject &>/dev/null; then
            echo "  Installing python-gobject..."
            sudo -n pacman -S --noconfirm python-gobject 2>&1 | tail -1
        fi

        # Enable accessibility service
        gsettings set org.gnome.desktop.interface toolkit-accessibility true 2>/dev/null || true

        echo "  ✓ AI Navigation configured — Claude has virtual monitor $HEADLESS_NAME"
    fi
fi

# ─── Laptop power management ─────────────────────────────────
if ls /sys/class/power_supply/BAT* &>/dev/null; then
    echo "→ Laptop detected — enabling power management..."
    if pacman -Qi power-profiles-daemon &>/dev/null; then
        sudo -n systemctl enable --now power-profiles-daemon 2>/dev/null || true
        echo "  Enabled power-profiles-daemon"
    fi
fi

# ─── GitHub setup ─────────────────────────────────────────────
if [ -f "$COSTA_DIR/config.json" ]; then
    SETUP_GH=$(jq -r '.setup_github // false' "$COSTA_DIR/config.json")
    if [ "$SETUP_GH" = "true" ] && command -v gh &>/dev/null; then
        echo "→ GitHub authentication..."
        echo "  Run 'gh auth login' when you're ready to authenticate with GitHub."
        echo "  (Skipping interactive login during first-boot to avoid blocking)"
    fi
fi

# ─── Restore password-required sudo ─────────────────────────
# NOPASSWD was left on by costa-install so first-boot.sh (which runs with no TTY)
# could call sudo without hanging. Now that setup is complete, require password.
echo "→ Restoring secure sudo configuration..."
sudo -n bash -c "echo '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/wheel"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Costa OS setup complete!           ║"
echo "║                                      ║"
echo "║   Voice AI:    SUPER+ALT+V           ║"
echo "║   Keybinds:    costa-keybinds         ║"
echo "║   Ask AI:      costa-ai \"question\"    ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Log saved to $FIRST_BOOT_LOG"
echo "Press Enter to close..."
read
