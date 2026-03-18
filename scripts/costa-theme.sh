#!/bin/bash
# ════════════════════════════════════════════
# Costa OS Theme Switcher
# Usage: costa-theme.sh [light|dark|toggle|status]
# Switches all Costa OS components between light and dark mode
# ════════════════════════════════════════════

set -euo pipefail

COSTA_DIR="${HOME}/.config/costa"
COSTA_CONFIG="${COSTA_DIR}/config.json"
COSTA_OS_DIR="$(dirname "$(dirname "$(realpath "$0")")")"

# ── Read current theme from config ──
get_current_theme() {
    if [[ -f "$COSTA_CONFIG" ]]; then
        theme=$(python3 -c "import json; print(json.load(open('$COSTA_CONFIG')).get('theme', 'dark'))" 2>/dev/null || echo "dark")
        echo "$theme"
    else
        echo "dark"
    fi
}

# ── Save theme preference to config.json ──
save_theme() {
    local theme="$1"
    mkdir -p "$COSTA_DIR"
    if [[ -f "$COSTA_CONFIG" ]]; then
        python3 -c "
import json
cfg = json.load(open('$COSTA_CONFIG'))
cfg['theme'] = '$theme'
json.dump(cfg, open('$COSTA_CONFIG', 'w'), indent=2)
"
    else
        echo "{\"theme\": \"$theme\"}" > "$COSTA_CONFIG"
    fi
}

# ── Apply theme to all components ──
apply_theme() {
    local theme="$1"
    local suffix=""
    [[ "$theme" == "light" ]] && suffix="-light"

    echo "Switching to ${theme} mode..."

    # Waybar style
    local waybar_src="${COSTA_OS_DIR}/configs/waybar/style${suffix}.css"
    local waybar_dst="${HOME}/.config/waybar/style.css"
    if [[ -f "$waybar_src" ]]; then
        cp "$waybar_src" "$waybar_dst"
        echo "  Waybar style updated"
    fi

    # Ghostty config
    local ghostty_src="${COSTA_OS_DIR}/configs/ghostty/config${suffix}"
    local ghostty_dst="${HOME}/.config/ghostty/config"
    if [[ -f "$ghostty_src" ]]; then
        cp "$ghostty_src" "$ghostty_dst"
        echo "  Ghostty config updated"
    fi

    # Rofi config
    local rofi_src="${COSTA_OS_DIR}/configs/rofi/config${suffix}.rasi"
    local rofi_dst="${HOME}/.config/rofi/config.rasi"
    if [[ -f "$rofi_src" ]]; then
        cp "$rofi_src" "$rofi_dst"
        echo "  Rofi config updated"
    fi

    # Dunst config
    local dunst_src="${COSTA_OS_DIR}/configs/dunst/dunstrc${suffix}"
    local dunst_dst="${HOME}/.config/dunst/dunstrc"
    if [[ -f "$dunst_src" ]]; then
        cp "$dunst_src" "$dunst_dst"
        echo "  Dunst config updated"
    fi

    # Hyprland color variables
    local hypr_src="${COSTA_OS_DIR}/configs/hypr/costa-colors-${theme}.conf"
    local hypr_dst="${HOME}/.config/hypr/costa-colors.conf"
    if [[ -f "$hypr_src" ]]; then
        cp "$hypr_src" "$hypr_dst"
        echo "  Hyprland colors updated"
    fi

    # GTK color scheme preference
    if command -v gsettings &>/dev/null; then
        if [[ "$theme" == "light" ]]; then
            gsettings set org.gnome.desktop.interface color-scheme prefer-light 2>/dev/null || true
        else
            gsettings set org.gnome.desktop.interface color-scheme prefer-dark 2>/dev/null || true
        fi
        echo "  GTK color scheme set to prefer-${theme}"
    fi

    # Save preference
    save_theme "$theme"

    # Restart services
    if pgrep -x waybar &>/dev/null; then
        killall waybar 2>/dev/null || true
        waybar &disown 2>/dev/null
        echo "  Waybar restarted"
    fi

    if pgrep -x dunst &>/dev/null; then
        killall dunst 2>/dev/null || true
        dunst &disown 2>/dev/null
        echo "  Dunst restarted"
    fi

    if command -v hyprctl &>/dev/null; then
        hyprctl reload 2>/dev/null || true
        echo "  Hyprland reloaded"
    fi

    echo ""
    echo "Costa OS theme: ${theme}"

    # Send notification (after dunst restarts)
    sleep 0.5
    if [[ "$theme" == "light" ]]; then
        notify-send "Costa OS" "Switched to light mode" 2>/dev/null || true
    else
        notify-send "Costa OS" "Switched to dark mode" 2>/dev/null || true
    fi
}

# ── Main ──
case "${1:-status}" in
    light)
        apply_theme light
        ;;
    dark)
        apply_theme dark
        ;;
    toggle)
        current=$(get_current_theme)
        if [[ "$current" == "dark" ]]; then
            apply_theme light
        else
            apply_theme dark
        fi
        ;;
    status)
        current=$(get_current_theme)
        echo "Costa OS theme: ${current}"
        ;;
    *)
        echo "Usage: costa-theme.sh [light|dark|toggle|status]"
        echo ""
        echo "Commands:"
        echo "  light   — Switch to light mode"
        echo "  dark    — Switch to dark mode"
        echo "  toggle  — Toggle between light and dark"
        echo "  status  — Show current theme"
        exit 1
        ;;
esac
