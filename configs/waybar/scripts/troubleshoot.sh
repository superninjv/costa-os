#!/bin/bash
# System troubleshooter for Arch Linux + Hyprland desktop
# Checks all critical components and reports issues
# Usage: troubleshoot.sh [--fix] [--notify] [--json]

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

FIX_MODE=false
NOTIFY_MODE=false
JSON_MODE=false
ISSUES=()
WARNINGS=()

for arg in "$@"; do
  case "$arg" in
    --fix)    FIX_MODE=true ;;
    --notify) NOTIFY_MODE=true ;;
    --json)   JSON_MODE=true ;;
  esac
done

# ─── Read Costa config for feature-aware checks ───
COSTA_CONFIG="$HOME/.config/costa/config.json"
AI_TIER=$(jq -r '.ai_tier // "VOICE_AND_LLM"' "$COSTA_CONFIG" 2>/dev/null || echo "VOICE_AND_LLM")
HAS_MIC=$(jq -r '.has_microphone // true' "$COSTA_CONFIG" 2>/dev/null || echo "true")

pass() { $JSON_MODE || echo -e "  ${GREEN}✓${NC} $1"; }
fail() { $JSON_MODE || echo -e "  ${RED}✗${NC} $1"; ISSUES+=("$1"); }
warn() { $JSON_MODE || echo -e "  ${YELLOW}!${NC} $1"; WARNINGS+=("$1"); }
header() { $JSON_MODE || echo -e "\n${CYAN}${BOLD}[$1]${NC}"; }
fix_msg() { $JSON_MODE || echo -e "    ${YELLOW}→ fix:${NC} $1"; }

# ── Hyprland ──────────────────────────────────────────────

check_hyprland() {
  header "Hyprland"

  if ! pgrep -x Hyprland &>/dev/null; then
    fail "Hyprland not running"
    return
  fi
  pass "Hyprland running"

  errors=$(hyprctl configerrors 2>/dev/null)
  if [ -n "$errors" ] && [ "$errors" != "no errors" ]; then
    fail "Config errors: $errors"
  else
    pass "Config clean"
  fi

  monitor_count=$(hyprctl monitors -j 2>/dev/null | jq length 2>/dev/null)
  if [ -n "$monitor_count" ] && [ "$monitor_count" -gt 0 ] 2>/dev/null; then
    pass "$monitor_count monitor(s) detected"
  elif [ -n "$monitor_count" ]; then
    warn "No monitors detected"
  else
    fail "Could not query monitors"
  fi
}

# ── Waybar ────────────────────────────────────────────────

check_waybar() {
  header "Waybar"

  if pgrep -x waybar &>/dev/null; then
    pass "Waybar running"
  else
    fail "Waybar not running"
    if $FIX_MODE; then
      fix_msg "Starting waybar..."
      waybar &disown 2>/dev/null
      sleep 1
      pgrep -x waybar &>/dev/null && pass "Waybar started" || fail "Waybar failed to start"
    fi
  fi
}

# ── Audio (PipeWire) ──────────────────────────────────────

check_audio() {
  header "Audio"

  if systemctl --user is-active pipewire.service &>/dev/null; then
    pass "PipeWire running"
  else
    fail "PipeWire not running"
    if $FIX_MODE; then
      fix_msg "Starting PipeWire..."
      systemctl --user start pipewire pipewire-pulse wireplumber
    fi
  fi

  if systemctl --user is-active wireplumber.service &>/dev/null; then
    pass "WirePlumber running"
  else
    fail "WirePlumber not running"
    if $FIX_MODE; then
      fix_msg "Starting WirePlumber..."
      systemctl --user start wireplumber
    fi
  fi

  default_source=$(pactl get-default-source 2>/dev/null)
  if [ -n "$default_source" ]; then
    pass "Default mic: $default_source"
  else
    if [ "$HAS_MIC" = "true" ]; then
      fail "No audio sources available"
    else
      pass "No microphone configured"
    fi
  fi
}

# ── Background Daemons ────────────────────────────────────

check_daemons() {
  header "Background Daemons"

  if pgrep -f "wallpaper-pause" &>/dev/null; then
    pass "Wallpaper pause daemon running"
  else
    warn "Wallpaper pause daemon not running"
    if $FIX_MODE; then
      fix_msg "Starting wallpaper pause daemon..."
      ~/.config/hypr/wallpaper-pause.sh &disown 2>/dev/null
    fi
  fi

  if [ "$AI_TIER" != "CLOUD_ONLY" ] && [ "$AI_TIER" != "VOICE_ONLY" ]; then
    if pgrep -f "ollama-manager" &>/dev/null; then
      pass "Ollama VRAM manager running"
    else
      warn "Ollama VRAM manager not running"
      if $FIX_MODE; then
        fix_msg "Starting Ollama VRAM manager..."
        ~/.config/hypr/ollama-manager.sh &disown 2>/dev/null
      fi
    fi
  fi

  if pgrep -f "mpvpaper|wallpaper.sh" &>/dev/null; then
    pass "Wallpaper (mpvpaper) running"
  else
    warn "Wallpaper not running"
    if $FIX_MODE; then
      fix_msg "Starting wallpaper..."
      ~/.config/hypr/wallpaper.sh &disown 2>/dev/null
    fi
  fi

  if pgrep -x dunst &>/dev/null; then
    pass "Dunst running"
  else
    warn "Dunst not running (starts on first notification)"
  fi
}

# ── Ollama / AI Stack ─────────────────────────────────────

check_ollama() {
  if [ "$AI_TIER" = "CLOUD_ONLY" ]; then
    header "AI (Cloud Only)"
    pass "Cloud-only mode — local models not required"
    return
  fi

  header "Ollama / AI"

  if pgrep -x ollama &>/dev/null; then
    pass "Ollama running"
  else
    fail "Ollama not running"
    if $FIX_MODE; then
      fix_msg "Starting Ollama..."
      ollama serve &disown 2>/dev/null
      sleep 2
    fi
  fi

  if command -v ollama &>/dev/null; then
    models=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ', ' | sed 's/,$//')
    if [ -n "$models" ]; then
      pass "Models available: $models"
    else
      warn "No models loaded"
    fi
  fi

  if [ "$AI_TIER" != "VOICE_ONLY" ]; then
    if command -v whisper-cli &>/dev/null || [ -f "$HOME/.voicemode/services/whisper/build/bin/whisper-cli" ]; then
      pass "Whisper.cpp available"
    else
      warn "Whisper.cpp not found"
    fi

    VAD_STATUS=$(cat /tmp/vad-status 2>/dev/null)
    if [ "$VAD_STATUS" = "ready" ] || [ "$VAD_STATUS" = "listening" ] || [ "$VAD_STATUS" = "speech" ]; then
      pass "VAD daemon running ($VAD_STATUS)"
    elif [ -f "$HOME/.config/costa/vad/vad_daemon.py" ]; then
      warn "VAD daemon not running"
      if $FIX_MODE; then
        fix_msg "Starting VAD daemon..."
        python3 "$HOME/.config/costa/vad/vad_daemon.py" &disown 2>/dev/null
      fi
    else
      warn "VAD daemon not installed"
    fi

    if [ -f "/usr/lib/ladspa/libdeep_filter_ladspa.so" ]; then
      pass "DeepFilterNet available"
    else
      warn "DeepFilterNet LADSPA not found"
    fi
  fi
}

# ── Dev Tools / PATH ──────────────────────────────────────

check_devtools() {
  header "Dev Tools & PATH"

  local tools=("claude" "node" "python" "rustc" "java" "docker" "git" "gh" "ghostty" "rofi" "zellij")
  for tool in "${tools[@]}"; do
    if command -v "$tool" &>/dev/null; then
      pass "$tool → $(command -v "$tool")"
    else
      fail "$tool not found on PATH"
    fi
  done

  # Check nvm specifically since it's the common culprit
  if [ -d "$HOME/.nvm" ]; then
    if echo "$PATH" | grep -q "\.nvm"; then
      pass "nvm PATH loaded"
    else
      warn "nvm installed but PATH not loaded (source nvm.sh)"
    fi
  fi
}

# ── Systemd Services ─────────────────────────────────────

check_services() {
  header "Systemd Services"

  failed_user=$(systemctl --user --failed --no-legend 2>/dev/null)
  if [ -z "$failed_user" ]; then
    pass "No failed user services"
  else
    fail "Failed user services: $failed_user"
  fi

  failed_system=$(systemctl --failed --no-legend 2>/dev/null)
  if [ -z "$failed_system" ]; then
    pass "No failed system services"
  else
    warn "Failed system services: $failed_system"
  fi

  # Check specific services we care about
  for svc in postgresql docker; do
    if systemctl is-enabled "$svc" &>/dev/null; then
      if systemctl is-active "$svc" &>/dev/null; then
        pass "$svc active"
      else
        warn "$svc enabled but not active"
        if $FIX_MODE; then
          fix_msg "Starting $svc..."
          sudo systemctl start "$svc" 2>/dev/null
        fi
      fi
    fi
  done
}

# ── GPU ───────────────────────────────────────────────────

check_gpu() {
  gpu_label=$(lspci 2>/dev/null | grep -i 'vga\|3d\|display' | head -1 | sed 's/.*: //' | cut -c1-40)
  header "GPU${gpu_label:+ ($gpu_label)}"

  if lsmod | grep -q amdgpu; then
    pass "amdgpu kernel module loaded"
  else
    fail "amdgpu kernel module not loaded"
  fi

  if command -v vulkaninfo &>/dev/null; then
    gpu_name=$(vulkaninfo --summary 2>/dev/null | grep "deviceName" | head -1 | sed 's/.*= //')
    if [ -n "$gpu_name" ]; then
      pass "Vulkan: $gpu_name"
    else
      warn "Vulkan available but no GPU detected"
    fi
  else
    warn "vulkaninfo not installed"
  fi

  vram=$(cat /sys/class/drm/card*/device/mem_info_vram_used 2>/dev/null | head -1)
  vram_total=$(cat /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null | head -1)
  if [ -n "$vram" ] && [ -n "$vram_total" ]; then
    vram_mb=$((vram / 1024 / 1024))
    vram_total_mb=$((vram_total / 1024 / 1024))
    pass "VRAM: ${vram_mb}MB / ${vram_total_mb}MB"
  fi
}

# ── Journal Errors ────────────────────────────────────────

check_journal() {
  header "Recent Errors (this boot)"

  err_count=$(journalctl -b --priority=err --no-pager -q 2>/dev/null | wc -l)
  if [ "$err_count" -eq 0 ]; then
    pass "No errors in journal"
  elif [ "$err_count" -lt 10 ]; then
    warn "$err_count errors in journal"
  else
    warn "$err_count errors in journal (run 'journalctl -b -p err' for details)"
  fi

  user_err_count=$(journalctl --user -b --priority=err --no-pager -q 2>/dev/null | wc -l)
  if [ "$user_err_count" -eq 0 ]; then
    pass "No user session errors"
  else
    warn "$user_err_count user session errors"
  fi
}

# ── Voice PTT ─────────────────────────────────────────────

check_voice() {
  if [ "$HAS_MIC" = "false" ] || [ "$AI_TIER" = "CLOUD_ONLY" ]; then
    return
  fi

  header "Voice Assistant (PTT)"

  if [ -f "$HOME/.config/hypr/push-to-talk.sh" ]; then
    pass "PTT script exists"
  else
    warn "PTT script not found"
  fi

  # Check keybinds are registered
  binds=$(hyprctl binds -j 2>/dev/null)
  if echo "$binds" | jq -e '.[] | select((.key == "V" or .key == "v") and .modmask != 0)' &>/dev/null; then
    pass "PTT keybinds registered"
  else
    warn "PTT keybinds may not be registered"
  fi
}

# ── Run all checks ────────────────────────────────────────

$JSON_MODE || echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
$JSON_MODE || echo -e "${BOLD}║   System Troubleshooter  v1.0       ║${NC}"
$JSON_MODE || echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
$JSON_MODE || echo -e "  $(date '+%Y-%m-%d %H:%M:%S')  |  $(uname -r)"
$FIX_MODE && { $JSON_MODE || echo -e "  ${YELLOW}Auto-fix mode enabled${NC}"; }

check_hyprland
check_waybar
check_audio
check_daemons
check_ollama
check_devtools
check_services
check_gpu
check_journal
check_voice

# ── Summary ───────────────────────────────────────────────

$JSON_MODE || echo ""

if $JSON_MODE; then
  printf '{"issues":%s,"warnings":%s}\n' \
    "$(printf '%s\n' "${ISSUES[@]}" | jq -R . | jq -s .)" \
    "$(printf '%s\n' "${WARNINGS[@]}" | jq -R . | jq -s .)"
elif [ ${#ISSUES[@]} -eq 0 ] && [ ${#WARNINGS[@]} -eq 0 ]; then
  echo -e "${GREEN}${BOLD}All clear — system healthy.${NC}"
elif [ ${#ISSUES[@]} -eq 0 ]; then
  echo -e "${YELLOW}${BOLD}${#WARNINGS[@]} warning(s), no critical issues.${NC}"
else
  echo -e "${RED}${BOLD}${#ISSUES[@]} issue(s), ${#WARNINGS[@]} warning(s).${NC}"
  if ! $FIX_MODE; then
    echo -e "  Run with ${CYAN}--fix${NC} to auto-repair what's possible."
  fi
fi

if $NOTIFY_MODE; then
  if [ ${#ISSUES[@]} -gt 0 ]; then
    notify-send -u critical "System Issues" "${#ISSUES[@]} issues found\n${ISSUES[0]}"
  elif [ ${#WARNINGS[@]} -gt 0 ]; then
    notify-send -u normal "System Check" "${#WARNINGS[@]} warnings\nNo critical issues"
  else
    notify-send -u low "System Check" "All systems healthy"
  fi
fi
