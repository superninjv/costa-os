#!/bin/bash
# Costa OS — Claude Code Auto-Configure
# Sets up Claude Code with Costa OS MCP server, commands, hardware-aware CLAUDE.md,
# and project scoping headers. Idempotent — safe to run multiple times.

set -o pipefail

COSTA_DIR="$HOME/.config/costa"
COSTA_SHARE="/usr/share/costa-os"
CLAUDE_DIR="$HOME/.claude"

echo "→ Setting up Claude Code with Costa OS integration..."

# ─── 1. Install Claude Code if missing ───────────────────────
if ! command -v claude &>/dev/null; then
    echo "  Claude Code CLI not found — installing..."
    if command -v npm &>/dev/null; then
        # Try global install with sudo (non-interactive; -n fails fast if password needed)
        if sudo -n npm install -g @anthropic-ai/claude-code 2>/dev/null; then
            echo "  ✓ Claude Code installed globally"
        else
            echo "  sudo not available, installing to user prefix..."
            mkdir -p "$HOME/.local/lib/npm"
            npm config set prefix "$HOME/.local"
            npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
            export PATH="$HOME/.local/bin:$PATH"
        fi
        if command -v claude &>/dev/null; then
            echo "  ✓ Claude Code installed"
        else
            echo "  ✗ Claude Code installation failed"
            echo "    Try manually: npm install -g @anthropic-ai/claude-code"
        fi
    else
        echo "  ✗ npm not found — install nodejs and npm first"
        echo "    sudo pacman -S nodejs npm && npm install -g @anthropic-ai/claude-code"
    fi
else
    echo "  ✓ Claude Code CLI found"
fi

# ─── 1b. Schedule Claude Code authentication ─────────────────
# Claude login needs a proper TTY (not piped through tee/logging).
# Instead of trying to auth here, create a login launcher that runs
# in its own terminal on next login.
if command -v claude &>/dev/null; then
    # Ensure Firefox is set as default browser for OAuth to work
    if command -v firefox &>/dev/null; then
        xdg-settings set default-web-browser firefox.desktop 2>/dev/null || true
    fi

    # Create a one-shot login script that launches in its own terminal
    CLAUDE_LOGIN="$HOME/.config/costa/scripts/claude-login.sh"
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
    echo "Starting Claude Code authentication..."
    echo ""
    claude auth login
fi
# Clear the autostart trigger (leave empty file so hyprland source= doesn't error)
: > ~/.config/hypr/costa-claude-login.conf
echo ""
echo "You can always log in later by running: claude"
echo "Press Enter to close..."
read
LOGINEOF
    chmod +x "$CLAUDE_LOGIN"

    # Find a working terminal emulator
    # Skip ghostty in VMs — it requires GPU acceleration and crashes on QXL/virtio-vga
    IN_VM=""
    if systemd-detect-virt -q 2>/dev/null || grep -qi "hypervisor\|qemu\|kvm\|virtualbox\|vmware" /proc/cpuinfo 2>/dev/null; then
        IN_VM="1"
    fi

    TERM_CMD=""
    for term in ghostty foot kitty alacritty; do
        [ "$IN_VM" = "1" ] && [ "$term" = "ghostty" ] && continue
        if command -v "$term" &>/dev/null; then
            TERM_CMD="$term"
            break
        fi
    done
    if [ -z "$TERM_CMD" ]; then
        if [ "$IN_VM" = "1" ]; then
            echo "  ⚠ No suitable terminal found for login prompt (VM detected)"
            echo "  ✓ Run 'claude' from any terminal to log in"
            SKIP_LOGIN_TERMINAL=1
        else
            TERM_CMD="ghostty"  # default to ghostty on real hardware
        fi
    fi

    if [ "${SKIP_LOGIN_TERMINAL:-}" = "1" ]; then
        echo "  Skipping login terminal setup"
    else

    # Build exec command based on terminal
    case "$TERM_CMD" in
        ghostty)    TERM_EXEC="ghostty -e $CLAUDE_LOGIN" ;;
        foot)       TERM_EXEC="foot $CLAUDE_LOGIN" ;;
        kitty)      TERM_EXEC="kitty $CLAUDE_LOGIN" ;;
        alacritty)  TERM_EXEC="alacritty -e $CLAUDE_LOGIN" ;;
    esac

    # Add a one-shot autostart to hyprland.conf (separate file, sourced once)
    # This is a fallback for next boot in case the immediate launch below doesn't work
    CLAUDE_AUTOSTART="$HOME/.config/hypr/costa-claude-login.conf"
    echo "exec-once = $TERM_EXEC" > "$CLAUDE_AUTOSTART"

    # Source it from hyprland.conf if not already present
    if ! grep -q "costa-claude-login.conf" "$HOME/.config/hypr/hyprland.conf" 2>/dev/null; then
        echo "" >> "$HOME/.config/hypr/hyprland.conf"
        echo "# Claude Code first-login (auto-removes after use)" >> "$HOME/.config/hypr/hyprland.conf"
        echo "source = ~/.config/hypr/costa-claude-login.conf" >> "$HOME/.config/hypr/hyprland.conf"
    fi

    # If early_claude_login() already launched the terminal (first-boot flow),
    # skip the immediate launch — the autostart is still a fallback for next boot
    if [ -f /tmp/costa-claude-login-launched ]; then
        echo "  ✓ Claude login terminal already launched (early boot)"
        rm -f /tmp/costa-claude-login-launched
    elif command -v hyprctl &>/dev/null && hyprctl monitors &>/dev/null 2>&1; then
        echo "  → Launching Claude Code login terminal..."
        hyprctl dispatch exec "$TERM_EXEC" 2>/dev/null || true
        # Remove the autostart since we just launched it
        rm -f "$CLAUDE_AUTOSTART"
    else
        echo "  ✓ Claude login will prompt on next Hyprland session"
    fi

    fi  # end SKIP_LOGIN_TERMINAL check

fi

# ─── 2. Create ~/.claude/ directory ──────────────────────────
mkdir -p "$CLAUDE_DIR"

# ─── 3. Write/merge ~/.claude.json with MCP server config ────
CLAUDE_JSON="$HOME/.claude.json"

NOTES_DIR="$HOME/notes"

COSTA_MCP_CONFIG=$(cat << MCPEOF
{
  "mcpServers": {
    "costa-system": {
      "command": "python3",
      "args": ["/usr/share/costa-os/mcp-server/costa_system.py"]
    },
    "obsidian": {
      "command": "npx",
      "args": ["-y", "obsidian-mcp", "$NOTES_DIR"]
    }
  },
  "projects": {}
}
MCPEOF
)

# Add the current user's home directory to projects with trust accepted
COSTA_MCP_CONFIG=$(echo "$COSTA_MCP_CONFIG" | jq --arg home "/home/$USER" '.projects[$home] = {"hasTrustDialogAccepted": true}')

if [ -f "$CLAUDE_JSON" ]; then
    # Merge: keep existing servers, add costa-system; keep existing projects, add home
    MERGED=$(jq -s '
        .[0] as $existing |
        .[1] as $new |
        $existing * {
            mcpServers: (($existing.mcpServers // {}) * $new.mcpServers),
            projects: (($existing.projects // {}) * $new.projects)
        }
    ' "$CLAUDE_JSON" <(echo "$COSTA_MCP_CONFIG"))
    echo "$MERGED" > "$CLAUDE_JSON"
    echo "  ✓ Merged costa-system MCP server into existing ~/.claude.json"
else
    echo "$COSTA_MCP_CONFIG" > "$CLAUDE_JSON"
    echo "  ✓ Created ~/.claude.json with costa-system MCP server"
fi

# ─── 4. Copy commands from Costa OS templates ────────────────
COMMANDS_SRC="$COSTA_SHARE/configs/claude/commands"
COMMANDS_DST="$CLAUDE_DIR/commands"

if [ -d "$COMMANDS_SRC" ]; then
    mkdir -p "$COMMANDS_DST"
    cp -r "$COMMANDS_SRC"/. "$COMMANDS_DST"/
    echo "  ✓ Installed Claude Code commands to $COMMANDS_DST"
else
    echo "  Commands template directory not found, skipping"
fi

# ─── 5. Generate hardware-aware CLAUDE.md ─────────────────────
CLAUDE_MD="$HOME/CLAUDE.md"
CLAUDE_TEMPLATE="$COSTA_SHARE/configs/claude/CLAUDE.md"

if [ ! -f "$CLAUDE_MD" ]; then
    if [ -f "$CLAUDE_TEMPLATE" ]; then
        cp "$CLAUDE_TEMPLATE" "$CLAUDE_MD"

        # Gather hardware info
        CPU_MODEL=$(grep "model name" /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs || echo "unknown")
        RAM_GB=$(free -g 2>/dev/null | awk '/Mem:/ {print $2}' || echo "?")

        GPU_NAME="unknown"
        VRAM_GB="0"
        GPU_VENDOR="unknown"
        if [ -f "$COSTA_DIR/gpu.conf" ]; then
            source "$COSTA_DIR/gpu.conf" 2>/dev/null || true
        fi

        MON_COUNT=$(hyprctl monitors -j 2>/dev/null | jq 'length' 2>/dev/null || echo "0")

        AI_TIER="unknown"
        if [ -f "$COSTA_DIR/config.json" ]; then
            AI_TIER=$(jq -r '.ai_tier // "unknown"' "$COSTA_DIR/config.json" 2>/dev/null || echo "unknown")
        fi

        # Append hardware section
        cat >> "$CLAUDE_MD" << HWEOF

## This Machine

- **CPU**: ${CPU_MODEL}
- **RAM**: ${RAM_GB}GB
- **GPU**: ${GPU_NAME} (${VRAM_GB}GB VRAM, ${GPU_VENDOR})
- **Monitors**: ${MON_COUNT} connected
- **AI Tier**: ${AI_TIER}
HWEOF

        echo "  ✓ Installed ~/CLAUDE.md with hardware info"
    else
        echo "  CLAUDE.md template not found at $CLAUDE_TEMPLATE, skipping"
    fi
else
    echo "  ~/CLAUDE.md already exists, skipping"
fi

# ─── 6. Add scoping header to project CLAUDE.md files ────────
SCOPE_HEADER='> **SCOPE:** This file contains project-specific instructions only.
> Your global Costa OS system knowledge, MCP tools, and knowledge base
> still apply. Use them. This file adds project context on top — it does
> not replace your system awareness.'

if [ -d "$HOME/projects" ]; then
    for project_md in "$HOME"/projects/*/CLAUDE.md; do
        [ -f "$project_md" ] || continue

        # Check if SCOPE: already present in first 5 lines
        if head -5 "$project_md" | grep -q "SCOPE:"; then
            continue
        fi

        # Prepend the scoping header
        TEMP_FILE=$(mktemp)
        {
            echo "$SCOPE_HEADER"
            echo ""
            cat "$project_md"
        } > "$TEMP_FILE"
        mv "$TEMP_FILE" "$project_md"
        echo "  ✓ Added scoping header to $project_md"
    done
fi

# ─── 7. Install Claude Code hooks (memory flush, session context) ──
echo "→ Configuring Claude Code hooks..."

SETTINGS_DIR="$CLAUDE_DIR"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

# Build hooks config — merge with existing settings if present
HOOKS_CONFIG=$(cat << 'HOOKSEOF'
{
  "permissions": {
    "allow": [
      "Bash(*)","Read(*)","Write(*)","Edit(*)","Glob(*)","Grep(*)","WebFetch(*)","WebSearch(*)",
      "mcp__costa-system__*"
    ]
  },
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/share/costa-os/scripts/costa-memory-flush.sh"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/share/costa-os/scripts/costa-session-start.sh"
          }
        ]
      }
    ]
  }
}
HOOKSEOF
)

if [ -f "$SETTINGS_FILE" ]; then
    # Merge hooks into existing settings
    MERGED=$(jq -s '.[0] * .[1]' "$SETTINGS_FILE" <(echo "$HOOKS_CONFIG"))
    echo "$MERGED" > "$SETTINGS_FILE"
    echo "  ✓ Merged hooks into existing settings.json"
else
    echo "$HOOKS_CONFIG" | jq '.' > "$SETTINGS_FILE"
    echo "  ✓ Created settings.json with memory hooks"
fi

# ─── 8. Initial RAG index of Obsidian vault ────────────────────
echo "→ Indexing Obsidian vault for search..."
COSTA_SHARE="/usr/share/costa-os"
if [ -f "$COSTA_SHARE/ai-router/rag.py" ] && [ -d "$HOME/notes" ]; then
    python3 "$COSTA_SHARE/ai-router/rag.py" index-defaults 2>&1 | tail -1 || true
    echo "  ✓ Vault indexed for RAG search"
fi

# ─── 9. Install vault-reindex workflow (hourly re-indexing) ────
if [ -f "$COSTA_SHARE/configs/costa/workflows/vault-reindex.yaml" ]; then
    mkdir -p "$HOME/.config/costa/workflows"
    cp -n "$COSTA_SHARE/configs/costa/workflows/vault-reindex.yaml" "$HOME/.config/costa/workflows/" 2>/dev/null
    # Install as systemd timer if costa-flow is available
    if command -v costa-flow &>/dev/null; then
        costa-flow install vault-reindex 2>/dev/null || true
        echo "  ✓ Vault reindex workflow installed (hourly)"
    fi
fi

echo "  ✓ Claude Code setup complete"
