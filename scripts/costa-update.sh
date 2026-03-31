#!/bin/bash
# Costa OS Update — AI-assisted system update
# Updates the Costa layer (git pull) and base system (pacman), with Claude
# reviewing changes and fixing breakage.
#
# Usage:
#   costa-update              Full update (Costa layer + system packages)
#   costa-update --costa-only Update Costa OS layer only (skip pacman)
#   costa-update --system-only Update system packages only (skip Costa layer)
#   costa-update --check      Check for updates without applying
#   costa-update --version    Print current version

set -euo pipefail

COSTA_DIR="/usr/share/costa-os"
VERSION_FILE="$COSTA_DIR/VERSION"
REMOTE_LATEST="https://costa-os.nyc3.digitaloceanspaces.com/LATEST"
LOG_FILE="/var/log/costa-update.log"
COSTA_CONFIG="$HOME/.config/costa"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}→${NC} $1"; }
ok()  { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1"; }

get_version() {
    if [ -f "$VERSION_FILE" ]; then
        cat "$VERSION_FILE" | tr -d '[:space:]'
    else
        echo "unknown"
    fi
}

check_remote_version() {
    curl -sf --connect-timeout 5 "$REMOTE_LATEST" 2>/dev/null | tr -d '[:space:]' || echo ""
}

version_gt() {
    # Returns 0 if $1 > $2 (semver comparison)
    [ "$(printf '%s\n' "$1" "$2" | sort -V | head -1)" != "$1" ]
}

# ─── Parse args ──────────────────────────────────────────────

MODE="full"
case "${1:-}" in
    --version|-v)
        echo "Costa OS $(get_version)"
        exit 0
        ;;
    --check|-c)
        MODE="check"
        ;;
    --costa-only)
        MODE="costa"
        ;;
    --system-only)
        MODE="system"
        ;;
    --help|-h)
        echo "Costa OS Update"
        echo ""
        echo "Usage: costa-update [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --check, -c        Check for updates without applying"
        echo "  --costa-only       Update Costa OS layer only"
        echo "  --system-only      Update system packages only"
        echo "  --version, -v      Print current version"
        echo "  --help, -h         Show this help"
        exit 0
        ;;
esac

# ─── Header ──────────────────────────────────────────────────

CURRENT=$(get_version)
echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Costa OS Update — v${CURRENT}$(printf '%*s' $((10 - ${#CURRENT})) '')║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ─── Check for updates ──────────────────────────────────────

log "Checking for updates..."
REMOTE=$(check_remote_version)

if [ -z "$REMOTE" ]; then
    warn "Could not reach update server — continuing with local update"
    REMOTE="$CURRENT"
fi

if [ "$REMOTE" = "$CURRENT" ]; then
    ok "Costa OS is up to date (v$CURRENT)"
    HAS_COSTA_UPDATE=false
elif version_gt "$REMOTE" "$CURRENT"; then
    log "Update available: v$CURRENT → v$REMOTE"
    HAS_COSTA_UPDATE=true
else
    ok "Local version (v$CURRENT) is ahead of remote (v$REMOTE)"
    HAS_COSTA_UPDATE=false
fi

if [ "$MODE" = "check" ]; then
    # Also check pacman
    echo ""
    log "Checking system package updates..."
    UPDATES=$(checkupdates 2>/dev/null | wc -l || echo "0")
    AUR_UPDATES=$(yay -Qua 2>/dev/null | wc -l || echo "0")
    echo "  System packages: $UPDATES updates available"
    echo "  AUR packages: $AUR_UPDATES updates available"
    exit 0
fi

# ─── Costa layer update ─────────────────────────────────────

UPDATE_LOG=""
COSTA_UPDATED=false

if [ "$MODE" = "full" ] || [ "$MODE" = "costa" ]; then
    echo ""
    log "Updating Costa OS layer..."

    if [ ! -d "$COSTA_DIR/.git" ]; then
        warn "Costa OS not installed as git repo at $COSTA_DIR"
        warn "Skipping Costa layer update (ISO install — re-download for latest)"
    else
        cd "$COSTA_DIR"

        # Stash local changes
        LOCAL_CHANGES=$(git status --porcelain 2>/dev/null | wc -l)
        if [ "$LOCAL_CHANGES" -gt 0 ]; then
            log "Stashing $LOCAL_CHANGES local changes..."
            git stash push -m "costa-update $(date +%Y-%m-%d_%H:%M)" 2>/dev/null
        fi

        # Record current position
        OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)

        # Pull latest
        if git pull --ff-only origin master 2>/dev/null; then
            NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)

            if [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
                COSTA_UPDATED=true
                DIFF_STAT=$(git diff --stat "$OLD_HEAD".."$NEW_HEAD" 2>/dev/null)
                COMMIT_LOG=$(git log --oneline "$OLD_HEAD".."$NEW_HEAD" 2>/dev/null)
                UPDATE_LOG="Changes pulled:\n$COMMIT_LOG\n\nFiles changed:\n$DIFF_STAT"

                ok "Costa layer updated"
                echo ""
                echo "  Commits:"
                echo "$COMMIT_LOG" | sed 's/^/    /'
                echo ""

                # Update VERSION from repo
                if [ -f "$COSTA_DIR/VERSION" ]; then
                    NEW_VERSION=$(cat "$COSTA_DIR/VERSION" | tr -d '[:space:]')
                    ok "Version: v$CURRENT → v$NEW_VERSION"
                fi
            else
                ok "Costa layer already up to date"
            fi
        else
            warn "Fast-forward pull failed — trying merge..."
            if ! git pull origin master 2>/dev/null; then
                err "Pull failed — manual intervention needed"
                err "Run: cd $COSTA_DIR && git status"
            fi
        fi

        # Restore local changes
        if [ "$LOCAL_CHANGES" -gt 0 ]; then
            log "Restoring local changes..."
            if git stash pop 2>/dev/null; then
                ok "Local changes restored"
            else
                warn "Merge conflict restoring local changes"
                warn "Your changes are in: git stash list"
            fi
        fi
    fi
fi

# ─── Deploy configs ─────────────────────────────────────────

deploy_configs() {
    local src="$COSTA_DIR"
    local home_config="$HOME/.config"
    local costa_config="$home_config/costa"

    # Validate HOME is sane (not empty, owned by us, is a real directory)
    if [ -z "$HOME" ] || [ ! -d "$HOME" ] || [ -L "$HOME" ]; then
        err "HOME is unset, missing, or a symlink — skipping config deploy"
        return 1
    fi
    if [ "$(stat -c %u "$HOME")" != "$(id -u)" ]; then
        err "HOME ($HOME) is not owned by current user — skipping config deploy"
        return 1
    fi

    echo ""
    log "Deploying updated configs..."

    # Safe install: reject symlink destinations, write atomically via install(1)
    safe_install() {
        local src_file="$1" dest="$2" mode="${3:-0644}"
        if [ -L "$dest" ]; then
            warn "Skipping $dest (is a symlink)"
            return 1
        fi
        mkdir -p "$(dirname "$dest")"
        install -m "$mode" "$src_file" "$dest"
    }

    # ── Tier 1: Scripts (always overwrite — these are code, not preferences) ──
    local scripts_deployed=0

    local tier1_files=(
        "configs/hypr/wallpaper.sh:$home_config/hypr/wallpaper.sh"
        "configs/hypr/ollama-manager.sh:$home_config/hypr/ollama-manager.sh"
        "configs/hypr/session-init.sh:$home_config/hypr/session-init.sh"
        "configs/hypr/session-cleanup.sh:$home_config/hypr/session-cleanup.sh"
    )

    for entry in "${tier1_files[@]}"; do
        local rel="${entry%%:*}"
        local dest="${entry##*:}"
        local src_file="$src/$rel"

        [ ! -f "$src_file" ] && continue

        if [ ! -f "$dest" ] || ! diff -q "$src_file" "$dest" &>/dev/null; then
            if safe_install "$src_file" "$dest" 0755; then
                scripts_deployed=$((scripts_deployed + 1))
            fi
        fi
    done
    [ "$scripts_deployed" -gt 0 ] && ok "Deployed $scripts_deployed script(s)"

    # ── Tier 2: Costa internals (always update, except workflows — see below) ──
    local internals_deployed=0

    # Agents
    if [ -d "$src/configs/costa/agents" ]; then
        mkdir -p "$costa_config/agents"
        for f in "$src"/configs/costa/agents/*.yaml; do
            [ ! -f "$f" ] && continue
            local base=$(basename "$f")
            if [ ! -f "$costa_config/agents/$base" ] || ! diff -q "$f" "$costa_config/agents/$base" &>/dev/null; then
                if safe_install "$f" "$costa_config/agents/$base"; then
                    internals_deployed=$((internals_deployed + 1))
                fi
            fi
        done
    fi

    # Knowledge files
    if [ -d "$src/knowledge" ]; then
        mkdir -p "$costa_config/knowledge"
        for f in "$src"/knowledge/*.md; do
            [ ! -f "$f" ] && continue
            local base=$(basename "$f")
            if [ ! -f "$costa_config/knowledge/$base" ] || ! diff -q "$f" "$costa_config/knowledge/$base" &>/dev/null; then
                if safe_install "$f" "$costa_config/knowledge/$base"; then
                    internals_deployed=$((internals_deployed + 1))
                fi
            fi
        done
    fi

    # System prompts
    if [ -d "$src/configs/costa/prompts" ]; then
        mkdir -p "$costa_config/prompts"
        for f in "$src"/configs/costa/prompts/*; do
            [ ! -f "$f" ] && continue
            local base=$(basename "$f")
            if [ ! -f "$costa_config/prompts/$base" ] || ! diff -q "$f" "$costa_config/prompts/$base" &>/dev/null; then
                if safe_install "$f" "$costa_config/prompts/$base"; then
                    internals_deployed=$((internals_deployed + 1))
                fi
            fi
        done
    fi

    # CLI registry
    if [ -f "$src/configs/costa/cli-registry.json" ]; then
        mkdir -p "$costa_config"
        if [ ! -f "$costa_config/cli-registry.json" ] || ! diff -q "$src/configs/costa/cli-registry.json" "$costa_config/cli-registry.json" &>/dev/null; then
            if safe_install "$src/configs/costa/cli-registry.json" "$costa_config/cli-registry.json"; then
                internals_deployed=$((internals_deployed + 1))
            fi
        fi
    fi

    # Workflows (add new only — user may customize existing ones)
    if [ -d "$src/configs/costa/workflows" ]; then
        mkdir -p "$costa_config/workflows"
        for f in "$src"/configs/costa/workflows/*.yaml; do
            [ ! -f "$f" ] && continue
            local base=$(basename "$f")
            if [ ! -f "$costa_config/workflows/$base" ]; then
                if safe_install "$f" "$costa_config/workflows/$base"; then
                    internals_deployed=$((internals_deployed + 1))
                fi
            fi
        done
    fi

    [ "$internals_deployed" -gt 0 ] && ok "Updated $internals_deployed internal config(s)"

    # ── Tier 3: Personal configs (never touch — warn if diverged) ──
    local diverged=0

    local tier3_files=(
        "configs/hypr/hyprland.conf:$home_config/hypr/hyprland.conf"
        "configs/ghostty/config:$home_config/ghostty/config"
        "configs/dunst/dunstrc:$home_config/dunst/dunstrc"
        "configs/rofi/config.rasi:$home_config/rofi/config.rasi"
    )

    for entry in "${tier3_files[@]}"; do
        local rel="${entry%%:*}"
        local dest="${entry##*:}"
        local src_file="$src/$rel"

        [ ! -f "$src_file" ] || [ ! -f "$dest" ] && continue

        if ! diff -q "$src_file" "$dest" &>/dev/null; then
            diverged=$((diverged + 1))
        fi
    done

    if [ "$diverged" -gt 0 ]; then
        warn "$diverged personal config(s) differ from shipped version"
        warn "Review with: diff ~/.config/<app>/config $COSTA_DIR/configs/<app>/config"
    fi

    local total=$((scripts_deployed + internals_deployed))
    if [ "$total" -eq 0 ]; then
        ok "All configs already up to date"
    fi
}

if [ "$COSTA_UPDATED" = true ]; then
    deploy_configs
fi

# ─── AI review of changes ───────────────────────────────────

if [ "$COSTA_UPDATED" = true ]; then
    echo ""
    log "Running AI health check on changes..."

    REVIEW_PROMPT="You just updated Costa OS from $OLD_HEAD to $NEW_HEAD. Here are the changes:

$UPDATE_LOG

Please:
1. Check if any config files need migration (compare old vs new schemas)
2. Verify the ai-router is functional: run 'costa-ai --no-context --no-escalate \"hello\"'
3. Check if any CLI wrappers were added/updated and need reinstalling
4. Check if any new knowledge files were added
5. Report what changed in plain language

Be brief. Fix anything broken. If everything looks good, just say so."

    # Try Claude first, fall back to local model
    if command -v claude &>/dev/null && [ -f "$COSTA_CONFIG/env" ] && grep -q "ANTHROPIC_API_KEY" "$COSTA_CONFIG/env" 2>/dev/null; then
        log "Using Claude for update review..."
        source "$COSTA_CONFIG/env" 2>/dev/null
        claude -p --model haiku "$REVIEW_PROMPT" 2>/dev/null && AI_REVIEWED=true || AI_REVIEWED=false
    elif command -v ollama &>/dev/null && ollama list 2>/dev/null | grep -q "qwen"; then
        log "Using local model for update review..."
        echo "$REVIEW_PROMPT" | ollama run qwen2.5:7b 2>/dev/null && AI_REVIEWED=true || AI_REVIEWED=false
    else
        AI_REVIEWED=false
    fi

    if [ "$AI_REVIEWED" = false ]; then
        warn "No AI available for review — manual checklist:"
        echo "  [ ] Check ai-router: costa-ai 'hello'"
        echo "  [ ] Check voice assistant: press SUPER+ALT+V"
        echo "  [ ] Check waybar modules are showing"
        echo "  [ ] Review changes: cd $COSTA_DIR && git log --oneline -5"
    fi
fi

# ─── System package update ───────────────────────────────────

if [ "$MODE" = "full" ] || [ "$MODE" = "system" ]; then
    echo ""
    log "Updating system packages..."

    # Show what will be updated
    UPDATES=$(checkupdates 2>/dev/null || true)
    AUR_UPDATES=$(yay -Qua 2>/dev/null || true)

    if [ -z "$UPDATES" ] && [ -z "$AUR_UPDATES" ]; then
        ok "All system packages are up to date"
    else
        if [ -n "$UPDATES" ]; then
            PKG_COUNT=$(echo "$UPDATES" | wc -l)
            log "$PKG_COUNT system packages to update"
        fi
        if [ -n "$AUR_UPDATES" ]; then
            AUR_COUNT=$(echo "$AUR_UPDATES" | wc -l)
            log "$AUR_COUNT AUR packages to update"
        fi

        echo ""
        yay -Syu --noconfirm 2>&1 | tail -20

        echo ""
        ok "System packages updated"

        # Check if key components were updated
        if echo "$UPDATES" | grep -qi "hyprland\|waybar\|ollama\|pipewire"; then
            warn "Core components updated — you may want to restart your session"
        fi
    fi
fi

# ─── Summary ─────────────────────────────────────────────────

echo ""
echo -e "${BLUE}────────────────────────────────────────${NC}"
FINAL_VERSION=$(get_version)
echo -e "  Costa OS v${GREEN}$FINAL_VERSION${NC}"
if [ "$COSTA_UPDATED" = true ]; then
    echo -e "  Costa layer: ${GREEN}updated${NC}"
else
    echo -e "  Costa layer: up to date"
fi
if [ "$MODE" = "full" ] || [ "$MODE" = "system" ]; then
    echo -e "  System packages: ${GREEN}updated${NC}"
fi
echo -e "${BLUE}────────────────────────────────────────${NC}"
echo ""

# Log the update
{
    echo "=== costa-update $(date) ==="
    echo "Version: $CURRENT → $FINAL_VERSION"
    echo "Mode: $MODE"
    [ -n "$UPDATE_LOG" ] && echo -e "$UPDATE_LOG"
    echo ""
} >> "$LOG_FILE" 2>/dev/null || true
