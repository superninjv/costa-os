#!/usr/bin/env bash
# Costa OS Demo Query Pre-Test
# Tests every costa-ai query used in the demo video and reports timing/model info

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

PASS=0
SLOW=0
FAIL=0

echo "═══════════════════════════════════════"
echo "  Costa OS Demo Query Pre-Test"
echo "═══════════════════════════════════════"
echo ""

test_query() {
    local desc="$1"
    local query="$2"
    local max_time="${3:-3}"

    printf "${CYAN}%-45s${NC} " "$desc"

    local start=$(date +%s%N)
    local output
    output=$(costa-ai --json "$query" 2>/dev/null) || output=""
    local end=$(date +%s%N)

    local elapsed_ms=$(( (end - start) / 1000000 ))
    local elapsed_s=$(echo "scale=1; $elapsed_ms / 1000" | bc)

    # Parse JSON output for model info
    local model=$(echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model','?'))" 2>/dev/null || echo "?")
    local escalated=$(echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('escalated') else 'no')" 2>/dev/null || echo "?")
    local preview=$(echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('response',''); print(r[:60]+'...' if len(r)>60 else r)" 2>/dev/null || echo "(no response)")

    if [ -z "$output" ]; then
        printf "${RED}FAIL${NC} (no output)\n"
        ((FAIL++))
    elif [ "$elapsed_ms" -gt $((max_time * 1000)) ]; then
        printf "${YELLOW}SLOW${NC} ${elapsed_s}s | model: $model | escalated: $escalated\n"
        printf "  ${DIM}%s${NC}\n" "$preview"
        ((SLOW++))
    else
        printf "${GREEN}OK${NC}   ${elapsed_s}s | model: $model | escalated: $escalated\n"
        printf "  ${DIM}%s${NC}\n" "$preview"
        ((PASS++))
    fi
}

# Act 1: First Impression
echo "--- Act 1: First Impression ---"
test_query "System status query" "what's running on my system"
test_query "Window management" "put firefox on workspace 5" 5
echo ""

# Act 2: AI Layer
echo "--- Act 2: AI Layer ---"
test_query "GPU info (local)" "what GPU do I have"
test_query "Tech news (cloud)" "what's trending in tech news" 8
test_query "Volume control" "turn the volume up" 5
echo ""

# Act 3: Developer Experience
echo "--- Act 3: Developer Experience ---"
test_query "Project switch" "switch to my-webapp project" 5
test_query "Package install" "install redis" 5
echo ""

# Act 4: General
echo "--- General queries ---"
test_query "Weather" "what's the weather" 5
test_query "Quick math (local)" "what is 2+2"
test_query "Docker status" "is docker running"
echo ""

# Summary
echo "═══════════════════════════════════════"
echo "  Results: ${GREEN}${PASS} passed${NC}, ${YELLOW}${SLOW} slow${NC}, ${RED}${FAIL} failed${NC}"
echo "═══════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Fix failed queries before recording!"
    exit 1
fi
