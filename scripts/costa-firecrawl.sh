#!/bin/bash
# Costa OS — Firecrawl Management
# Self-hosted web scraping API (Docker Compose)
#
# Usage:
#   costa-firecrawl setup    — clone repo + build images (first time)
#   costa-firecrawl start    — start Firecrawl services
#   costa-firecrawl stop     — stop Firecrawl services
#   costa-firecrawl status   — show service status + API health
#   costa-firecrawl update   — pull latest + rebuild
#   costa-firecrawl logs     — tail service logs
#   costa-firecrawl scrape URL — quick scrape test

set -euo pipefail

FIRECRAWL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/costa/firecrawl"
FIRECRAWL_REPO="https://github.com/mendableai/firecrawl.git"
COSTA_COMPOSE="/usr/share/costa-os/configs/costa/firecrawl/docker-compose.yaml"
API_URL="http://localhost:3002"

# Fall back to repo copy if not installed system-wide
if [ ! -f "$COSTA_COMPOSE" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
    COSTA_COMPOSE="$SCRIPT_DIR/configs/costa/firecrawl/docker-compose.yaml"
fi

_check_docker() {
    if ! command -v docker &>/dev/null; then
        echo "✗ Docker not installed. Install with: sudo pacman -S docker docker-compose"
        exit 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        echo "✗ Docker daemon not running. Start with: sudo systemctl start docker"
        exit 1
    fi
}

_check_setup() {
    if [ ! -d "$FIRECRAWL_DIR" ]; then
        echo "✗ Firecrawl not set up. Run: costa-firecrawl setup"
        exit 1
    fi
}

cmd_setup() {
    _check_docker
    echo "→ Setting up self-hosted Firecrawl..."

    if [ -d "$FIRECRAWL_DIR" ]; then
        echo "  Firecrawl directory already exists at $FIRECRAWL_DIR"
        read -rp "  Re-clone and rebuild? (y/N): " choice
        if [ "${choice:-n}" != "y" ] && [ "${choice:-n}" != "Y" ]; then
            echo "  Skipped. Use 'costa-firecrawl update' to pull latest."
            return
        fi
        # Stop services before re-cloning
        cmd_stop 2>/dev/null || true
        rm -rf "$FIRECRAWL_DIR"
    fi

    mkdir -p "$(dirname "$FIRECRAWL_DIR")"

    echo "  Cloning Firecrawl repository..."
    git clone --depth 1 "$FIRECRAWL_REPO" "$FIRECRAWL_DIR"

    # Copy Costa OS docker-compose overlay (localhost binding, Ollama integration)
    if [ -f "$COSTA_COMPOSE" ]; then
        cp "$COSTA_COMPOSE" "$FIRECRAWL_DIR/docker-compose.yaml"
        echo "  ✓ Applied Costa OS compose config (localhost-only, Ollama AI extraction)"
    fi

    echo "  Building Docker images (this takes a few minutes on first run)..."
    cd "$FIRECRAWL_DIR"
    docker compose build 2>&1 | tail -5

    echo ""
    echo "✓ Firecrawl ready. Start with: costa-firecrawl start"
    echo "  API will be at $API_URL"
    echo "  AI extraction uses local Ollama (qwen3.5:4b)"
}

cmd_start() {
    _check_docker
    _check_setup

    # Check if already running
    if curl -sf "$API_URL" &>/dev/null; then
        echo "✓ Firecrawl already running at $API_URL"
        return
    fi

    echo "→ Starting Firecrawl..."
    cd "$FIRECRAWL_DIR"
    docker compose up -d 2>&1 | tail -3

    # Wait for API to be ready
    echo -n "  Waiting for API..."
    for i in $(seq 1 30); do
        if curl -sf "$API_URL" &>/dev/null; then
            echo " ready"
            echo "✓ Firecrawl running at $API_URL"
            return
        fi
        echo -n "."
        sleep 2
    done
    echo " timeout"
    echo "⚠ API not responding — check logs: costa-firecrawl logs"
}

cmd_stop() {
    _check_setup
    echo "→ Stopping Firecrawl..."
    cd "$FIRECRAWL_DIR"
    docker compose down 2>&1 | tail -3
    echo "✓ Firecrawl stopped"
}

cmd_status() {
    if [ ! -d "$FIRECRAWL_DIR" ]; then
        echo "Firecrawl: not set up (run costa-firecrawl setup)"
        return
    fi

    cd "$FIRECRAWL_DIR"

    # Container status
    echo "=== Containers ==="
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  (not running)"

    # API health
    echo ""
    echo "=== API ==="
    if curl -sf "$API_URL" &>/dev/null; then
        echo "  Status: running at $API_URL"
    else
        echo "  Status: not responding"
    fi

    # Disk usage
    echo ""
    echo "=== Disk ==="
    du -sh "$FIRECRAWL_DIR" 2>/dev/null | awk '{print "  Repo: " $1}'
    docker system df --format "table {{.Type}}\t{{.Size}}\t{{.Reclaimable}}" 2>/dev/null | head -5
}

cmd_update() {
    _check_docker
    _check_setup

    echo "→ Updating Firecrawl..."
    cd "$FIRECRAWL_DIR"

    # Stop first
    docker compose down 2>&1 | tail -1

    # Pull latest
    git pull --rebase 2>&1 | tail -3

    # Re-apply Costa OS compose overlay
    if [ -f "$COSTA_COMPOSE" ]; then
        cp "$COSTA_COMPOSE" "$FIRECRAWL_DIR/docker-compose.yaml"
        echo "  ✓ Re-applied Costa OS compose config"
    fi

    # Rebuild
    echo "  Rebuilding images..."
    docker compose build 2>&1 | tail -5

    echo "✓ Updated. Start with: costa-firecrawl start"
}

cmd_logs() {
    _check_setup
    cd "$FIRECRAWL_DIR"
    docker compose logs --tail 50 -f
}

cmd_scrape() {
    local url="${1:-}"
    if [ -z "$url" ]; then
        echo "Usage: costa-firecrawl scrape <url>"
        exit 1
    fi

    if ! curl -sf "$API_URL" &>/dev/null; then
        echo "✗ Firecrawl not running. Start with: costa-firecrawl start"
        exit 1
    fi

    echo "→ Scraping: $url"
    curl -s "$API_URL/v1/scrape" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"$url\", \"formats\": [\"markdown\"]}" | \
        python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if d.get('success'):
        md = d.get('data', {}).get('markdown', '')
        print(md[:2000] if len(md) > 2000 else md)
        if len(md) > 2000:
            print(f'\n... ({len(md)} chars total, truncated)')
    else:
        print(f'Error: {d.get(\"error\", \"unknown\")}')
except Exception as e:
    print(f'Parse error: {e}')
"
}

# ─── Main ───────────────────────────────────────

case "${1:-help}" in
    setup)  cmd_setup ;;
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    update) cmd_update ;;
    logs)   cmd_logs ;;
    scrape) cmd_scrape "${2:-}" ;;
    help|--help|-h)
        echo "costa-firecrawl — self-hosted web scraping API"
        echo ""
        echo "Commands:"
        echo "  setup    Clone repo + build Docker images (first time)"
        echo "  start    Start Firecrawl services"
        echo "  stop     Stop Firecrawl services"
        echo "  status   Show service status + API health"
        echo "  update   Pull latest + rebuild"
        echo "  logs     Tail service logs"
        echo "  scrape URL  Quick scrape test (returns markdown)"
        echo ""
        echo "Data dir: $FIRECRAWL_DIR"
        echo "API: $API_URL"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run 'costa-firecrawl help' for usage"
        exit 1
        ;;
esac
