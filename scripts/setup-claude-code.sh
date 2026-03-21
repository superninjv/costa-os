#!/bin/bash
# Costa OS — Claude Code Auto-Configure
# Sets up Claude Code with Costa OS MCP server, commands, hardware-aware CLAUDE.md,
# and project scoping headers. Idempotent — safe to run multiple times.

set -euo pipefail

COSTA_DIR="$HOME/.config/costa"
COSTA_SHARE="/usr/share/costa-os"
CLAUDE_DIR="$HOME/.claude"

echo "→ Setting up Claude Code with Costa OS integration..."

# ─── 1. Install Claude Code if missing ───────────────────────
if ! command -v claude &>/dev/null; then
    echo "  Claude Code CLI not found — installing..."
    if command -v npm &>/dev/null; then
        npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
        if command -v claude &>/dev/null; then
            echo "  ✓ Claude Code installed"
        else
            echo "  ✗ Claude Code installation failed"
            echo "    Try manually: npm install -g @anthropic-ai/claude-code"
            exit 1
        fi
    else
        echo "  ✗ npm not found — install nodejs and npm first"
        echo "    sudo pacman -S nodejs npm && npm install -g @anthropic-ai/claude-code"
        exit 1
    fi
else
    echo "  ✓ Claude Code CLI found"
fi

# ─── 1b. Authenticate Claude Code ────────────────────────────
# Check if already authenticated (has API key in env or active session)
if command -v claude &>/dev/null; then
    echo ""
    echo "  Claude Code needs authentication for AI features."
    echo "  You have two options:"
    echo ""
    echo "    1. Anthropic Plan (recommended) — free with Pro/Team/Enterprise subscription"
    echo "       Uses OAuth login, no API key needed."
    echo ""
    echo "    2. API Key — pay-per-use via console.anthropic.com"
    echo "       Set ANTHROPIC_API_KEY in ~/.config/costa/env"
    echo ""
    echo -n "  Log in to Claude now? (Y/n): "
    read -r LOGIN_CHOICE
    if [ "${LOGIN_CHOICE:-y}" != "n" ] && [ "${LOGIN_CHOICE:-y}" != "N" ]; then
        echo "  Launching Claude login (follow the browser prompts)..."
        claude /login || echo "  ⚠ Login failed or skipped — you can run 'claude /login' later"
    else
        echo "  Skipped — run 'claude /login' anytime to authenticate"
    fi
    echo ""
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
