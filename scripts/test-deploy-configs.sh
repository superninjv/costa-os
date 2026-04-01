#!/bin/bash
# Test suite for deploy_configs() in costa-update.sh
# Run: bash scripts/test-deploy-configs.sh

set -uo pipefail

# ─── Counters ────────────────────────────────────────────────

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$((PASS + 1)); echo "  PASS  $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo "  FAIL  $1"; }

assert_exists()    { [ -f "$1" ]  && pass "$2" || fail "$2: expected file $1"; }
assert_absent()    { [ ! -f "$1" ] && pass "$2" || fail "$2: expected no file at $1"; }
assert_dir()       { [ -d "$1" ]  && pass "$2" || fail "$2: expected dir $1"; }
assert_mode()      {
    local actual
    actual=$(stat -c '%a' "$1" 2>/dev/null)
    [ "$actual" = "$2" ] && pass "$3" || fail "$3: expected mode $2, got $actual on $1"
}
assert_content()   {
    local content
    content=$(cat "$1" 2>/dev/null)
    [ "$content" = "$2" ] && pass "$3" || fail "$3: expected '$2', got '$content' in $1"
}
assert_returns()   {
    local rc=$1; shift
    local label="$1"; shift
    "$@" &>/dev/null
    local got=$?
    [ "$got" -eq "$rc" ] && pass "$label" || fail "$label: expected rc $rc, got $got"
}

# ─── Temp env setup ──────────────────────────────────────────

TMPDIR_ROOT=$(mktemp -d /tmp/test-deploy-configs.XXXXXX)
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

FAKE_COSTA="$TMPDIR_ROOT/costa-os"
FAKE_HOME="$TMPDIR_ROOT/home"
mkdir -p "$FAKE_HOME"

# Export HOME so stat ownership check uses actual uid
export HOME="$FAKE_HOME"

# Scaffold source tree that deploy_configs expects
mkdir -p \
    "$FAKE_COSTA/configs/hypr" \
    "$FAKE_COSTA/configs/ghostty" \
    "$FAKE_COSTA/configs/dunst" \
    "$FAKE_COSTA/configs/rofi" \
    "$FAKE_COSTA/configs/costa/agents" \
    "$FAKE_COSTA/configs/costa/prompts" \
    "$FAKE_COSTA/configs/costa/workflows" \
    "$FAKE_COSTA/knowledge"

# Tier 1 source scripts
for f in wallpaper.sh ollama-manager.sh session-init.sh session-cleanup.sh; do
    printf '#!/bin/bash\n# %s v1\n' "$f" > "$FAKE_COSTA/configs/hypr/$f"
done

# Tier 2 source internals
echo "agent: deployer" > "$FAKE_COSTA/configs/costa/agents/deployer.yaml"
echo "agent: sysadmin" > "$FAKE_COSTA/configs/costa/agents/sysadmin.yaml"
echo "# knowledge file" > "$FAKE_COSTA/knowledge/costa-os.md"
echo "system prompt" > "$FAKE_COSTA/configs/costa/prompts/base.txt"
echo '{"registry": true}' > "$FAKE_COSTA/configs/costa/cli-registry.json"
echo "workflow: deploy" > "$FAKE_COSTA/configs/costa/workflows/deploy.yaml"

# Tier 3 source personal configs
echo "hyprland config v1" > "$FAKE_COSTA/configs/hypr/hyprland.conf"
echo "ghostty config v1" > "$FAKE_COSTA/configs/ghostty/config"
echo "dunstrc v1"        > "$FAKE_COSTA/configs/dunst/dunstrc"
echo "rofi config v1"    > "$FAKE_COSTA/configs/rofi/config.rasi"

# ─── Extract and patch deploy_configs ────────────────────────
# We source the function by extracting it with its helpers, then
# overriding the COSTA_DIR to point at our fake tree.

EXTRACTED="$TMPDIR_ROOT/deploy_configs.sh"

# Pull out safe_install + deploy_configs from the source file
python3 - <<'PYEOF' "$EXTRACTED"
import sys, re

out_path = sys.argv[1]
with open('/home/jack/projects/costa-os/scripts/costa-update.sh') as fh:
    src = fh.read()

# Grab the color vars and helper fns (log/ok/warn/err) so output works
header = []
for line in src.splitlines():
    if re.match(r"^(RED|GREEN|YELLOW|BLUE|CYAN|NC)=", line):
        header.append(line)
    if re.match(r"^(log|ok|warn|err)\(\)", line):
        header.append(line)
    if re.match(r"^(log|ok|warn|err)\(\) \{", line):
        header.append(line)

# Extract lines for log/ok/warn/err single-line functions
helpers = []
for line in src.splitlines():
    if re.match(r'^(log|ok|warn|err)\(\)', line):
        helpers.append(line)

# Extract the deploy_configs() function body
m = re.search(r'^deploy_configs\(\) \{.*?^\}', src, re.MULTILINE | re.DOTALL)
if not m:
    print("ERROR: could not find deploy_configs()", file=sys.stderr)
    sys.exit(1)

func_body = m.group(0)

with open(out_path, 'w') as fh:
    fh.write('#!/bin/bash\n')
    for line in src.splitlines():
        if re.match(r"^(RED|GREEN|YELLOW|BLUE|CYAN|NC)=", line):
            fh.write(line + '\n')
    for line in src.splitlines():
        if re.match(r'^(log|ok|warn|err)\(\)', line):
            fh.write(line + '\n')
    fh.write('\n')
    fh.write(func_body + '\n')
PYEOF

if [ ! -f "$EXTRACTED" ]; then
    echo "FATAL: could not extract deploy_configs from costa-update.sh"
    exit 1
fi

# Helper to invoke deploy_configs with our fake dirs
run_deploy() {
    bash -c "
        COSTA_DIR='$FAKE_COSTA'
        HOME='$FAKE_HOME'
        source '$EXTRACTED'
        deploy_configs
    "
}

run_deploy_capture() {
    bash -c "
        COSTA_DIR='$FAKE_COSTA'
        HOME='$FAKE_HOME'
        source '$EXTRACTED'
        deploy_configs
    " 2>&1
}

# ─── TEST 1: Fresh install (no existing configs) ─────────────

echo ""
echo "=== TEST 1: Fresh install ==="

run_deploy

# Tier 1 scripts should be installed
for f in wallpaper.sh ollama-manager.sh session-init.sh session-cleanup.sh; do
    assert_exists "$FAKE_HOME/.config/hypr/$f" "fresh: tier1 $f installed"
    assert_mode   "$FAKE_HOME/.config/hypr/$f" "755" "fresh: tier1 $f mode=0755"
done

# Tier 2 internals should be installed
assert_exists "$FAKE_HOME/.config/costa/agents/deployer.yaml" "fresh: agent deployer.yaml installed"
assert_exists "$FAKE_HOME/.config/costa/agents/sysadmin.yaml" "fresh: agent sysadmin.yaml installed"
assert_exists "$FAKE_HOME/.config/costa/knowledge/costa-os.md" "fresh: knowledge file installed"
assert_exists "$FAKE_HOME/.config/costa/prompts/base.txt" "fresh: prompt installed"
assert_exists "$FAKE_HOME/.config/costa/cli-registry.json" "fresh: cli-registry installed"
assert_exists "$FAKE_HOME/.config/costa/workflows/deploy.yaml" "fresh: workflow installed"

# Tier 3 personal configs must NOT be created (no existing dest)
assert_absent "$FAKE_HOME/.config/hypr/hyprland.conf" "fresh: tier3 hyprland.conf not touched"
assert_absent "$FAKE_HOME/.config/ghostty/config" "fresh: tier3 ghostty config not touched"

# ─── TEST 2: No-op (identical files already in place) ────────

echo ""
echo "=== TEST 2: No-op (identical files) ==="

# Record mtimes before second run
mtime_wallpaper_before=$(stat -c '%Y' "$FAKE_HOME/.config/hypr/wallpaper.sh")
mtime_agent_before=$(stat -c '%Y' "$FAKE_HOME/.config/costa/agents/deployer.yaml")

sleep 1  # ensure mtime would differ if files were rewritten

run_deploy

mtime_wallpaper_after=$(stat -c '%Y' "$FAKE_HOME/.config/hypr/wallpaper.sh")
mtime_agent_after=$(stat -c '%Y' "$FAKE_HOME/.config/costa/agents/deployer.yaml")

[ "$mtime_wallpaper_before" -eq "$mtime_wallpaper_after" ] \
    && pass "no-op: tier1 script not rewritten when identical" \
    || fail "no-op: tier1 script was unnecessarily rewritten"

[ "$mtime_agent_before" -eq "$mtime_agent_after" ] \
    && pass "no-op: tier2 agent not rewritten when identical" \
    || fail "no-op: tier2 agent was unnecessarily rewritten"

# ─── TEST 3: Update (changed source files) ───────────────────

echo ""
echo "=== TEST 3: Update (changed source files) ==="

printf '#!/bin/bash\n# wallpaper v2\n' > "$FAKE_COSTA/configs/hypr/wallpaper.sh"
echo "agent: deployer v2"          > "$FAKE_COSTA/configs/costa/agents/deployer.yaml"
echo '{"registry": "v2"}'          > "$FAKE_COSTA/configs/costa/cli-registry.json"

run_deploy

assert_content "$FAKE_HOME/.config/hypr/wallpaper.sh" \
    "$(printf '#!/bin/bash\n# wallpaper v2')" \
    "update: tier1 wallpaper.sh updated to v2"
# Note: assert_content uses cat which strips trailing newline — printf match is correct

assert_content "$FAKE_HOME/.config/costa/agents/deployer.yaml" \
    "agent: deployer v2" \
    "update: tier2 deployer.yaml updated to v2"

assert_content "$FAKE_HOME/.config/costa/cli-registry.json" \
    '{"registry": "v2"}' \
    "update: cli-registry.json updated to v2"

# Unchanged tier2 file should still have original content
assert_content "$FAKE_HOME/.config/costa/agents/sysadmin.yaml" \
    "agent: sysadmin" \
    "update: unchanged sysadmin.yaml not disturbed"

# ─── TEST 4: Workflow add-only (never overwrite existing) ────

echo ""
echo "=== TEST 4: Workflow add-only ==="

# Put a user-customised workflow in place
echo "workflow: deploy (user-customised)" > "$FAKE_HOME/.config/costa/workflows/deploy.yaml"
ORIG_CONTENT="workflow: deploy (user-customised)"

# Update source to a different version
echo "workflow: deploy v2" > "$FAKE_COSTA/configs/costa/workflows/deploy.yaml"

# Add a brand-new workflow that doesn't exist in dest yet
echo "workflow: monitor" > "$FAKE_COSTA/configs/costa/workflows/monitor.yaml"

run_deploy

# Existing workflow must NOT be overwritten
assert_content "$FAKE_HOME/.config/costa/workflows/deploy.yaml" \
    "$ORIG_CONTENT" \
    "workflow: existing deploy.yaml not overwritten"

# New workflow must be added
assert_exists "$FAKE_HOME/.config/costa/workflows/monitor.yaml" \
    "workflow: new monitor.yaml added"

assert_content "$FAKE_HOME/.config/costa/workflows/monitor.yaml" \
    "workflow: monitor" \
    "workflow: new monitor.yaml has correct content"

# ─── TEST 5: Symlink rejection by safe_install ───────────────

echo ""
echo "=== TEST 5: Symlink rejection ==="

# Make the tier1 wallpaper.sh a symlink at the destination
SYMLINK_TARGET="$FAKE_HOME/.config/hypr/wallpaper.sh"
rm -f "$SYMLINK_TARGET"
ln -s /dev/null "$SYMLINK_TARGET"

# Restore source to something different so diff triggers
printf '#!/bin/bash\n# wallpaper v3\n' > "$FAKE_COSTA/configs/hypr/wallpaper.sh"

run_deploy

# safe_install should refuse to overwrite a symlink; it must still be a symlink
[ -L "$SYMLINK_TARGET" ] \
    && pass "symlink: symlink destination not overwritten" \
    || fail "symlink: symlink was replaced (should have been rejected)"

# Restore for later tests
rm -f "$SYMLINK_TARGET"
printf '#!/bin/bash\n# wallpaper v3\n' > "$FAKE_COSTA/configs/hypr/wallpaper.sh"
run_deploy > /dev/null 2>&1
[ ! -L "$SYMLINK_TARGET" ] && [ -f "$SYMLINK_TARGET" ] \
    && pass "symlink: file reinstalled after symlink removed" \
    || fail "symlink: could not reinstall after symlink removed"

# ─── TEST 6: Tier 3 — warn on divergence, never overwrite ────

echo ""
echo "=== TEST 6: Tier 3 personal configs ==="

# Install a tier3 config that differs from source
mkdir -p "$FAKE_HOME/.config/hypr"
echo "hyprland user customisation" > "$FAKE_HOME/.config/hypr/hyprland.conf"

output=$(run_deploy_capture)

# File must not be overwritten
assert_content "$FAKE_HOME/.config/hypr/hyprland.conf" \
    "hyprland user customisation" \
    "tier3: hyprland.conf not overwritten"

# A warning must appear
echo "$output" | grep -qi "warn\|personal\|differ\|diverge\|⚠" \
    && pass "tier3: divergence warning emitted" \
    || fail "tier3: no divergence warning for modified hyprland.conf"

# ─── TEST 7: HOME validation ─────────────────────────────────

echo ""
echo "=== TEST 7: HOME validation ==="

# Empty HOME
result=$(bash -c "
    COSTA_DIR='$FAKE_COSTA'
    HOME=''
    source '$EXTRACTED'
    deploy_configs
    echo rc:\$?
" 2>&1)
echo "$result" | grep -q "rc:1" \
    && pass "home-validation: empty HOME returns 1" \
    || fail "home-validation: empty HOME did not return 1 (got: $result)"

# Non-existent HOME
result=$(bash -c "
    COSTA_DIR='$FAKE_COSTA'
    HOME='/tmp/nonexistent-home-XXXXXX'
    source '$EXTRACTED'
    deploy_configs
    echo rc:\$?
" 2>&1)
echo "$result" | grep -q "rc:1" \
    && pass "home-validation: missing HOME dir returns 1" \
    || fail "home-validation: missing HOME dir did not return 1 (got: $result)"

# Symlink HOME
SYMLINK_HOME="$TMPDIR_ROOT/symlink-home"
ln -s "$FAKE_HOME" "$SYMLINK_HOME"
result=$(bash -c "
    COSTA_DIR='$FAKE_COSTA'
    HOME='$SYMLINK_HOME'
    source '$EXTRACTED'
    deploy_configs
    echo rc:\$?
" 2>&1)
echo "$result" | grep -q "rc:1" \
    && pass "home-validation: symlink HOME returns 1" \
    || fail "home-validation: symlink HOME did not return 1 (got: $result)"

# ─── TEST 8: Missing source files are skipped gracefully ─────

echo ""
echo "=== TEST 8: Missing source files (graceful skip) ==="

EMPTY_COSTA="$TMPDIR_ROOT/empty-costa"
mkdir -p "$EMPTY_COSTA"

result=$(bash -c "
    COSTA_DIR='$EMPTY_COSTA'
    HOME='$FAKE_HOME'
    source '$EXTRACTED'
    deploy_configs
    echo rc:\$?
" 2>&1)
echo "$result" | grep -q "rc:0" \
    && pass "empty-source: deploy_configs exits 0 with no source files" \
    || fail "empty-source: deploy_configs failed with no source files (got: $result)"

# ─── Summary ─────────────────────────────────────────────────

echo ""
echo "────────────────────────────────────────"
echo "  Results: $PASS passed, $FAIL failed"
echo "────────────────────────────────────────"

if [ "${#ERRORS[@]}" -gt 0 ]; then
    echo ""
    echo "Failures:"
    for e in "${ERRORS[@]}"; do
        echo "  - $e"
    done
    echo ""
    exit 1
fi

echo ""
exit 0
