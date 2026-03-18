#!/usr/bin/env bash
# Costa OS Wallpaper Manager
# Starts mpvpaper with video wallpaper or swww with static image.
# Edit WALLPAPER below or pass a path as $1.

WALLPAPER="${1:-}"
COSTA_DIR="$HOME/.config/costa"

# Check for user-configured wallpaper
if [ -z "$WALLPAPER" ] && [ -f "$COSTA_DIR/config.json" ]; then
    WALLPAPER=$(jq -r '.wallpaper // ""' "$COSTA_DIR/config.json" 2>/dev/null)
fi

# Default: look for wallpapers in standard locations
if [ -z "$WALLPAPER" ] || [ ! -f "$WALLPAPER" ]; then
    for dir in "$HOME/Pictures/Wallpapers" "$HOME/.local/share/wallpapers" "/usr/share/costa-os/wallpapers"; do
        [ -d "$dir" ] || continue
        # Prefer costa-default.* if it exists
        for ext in jpg png mp4 webm; do
            if [ -f "$dir/costa-default.$ext" ]; then
                WALLPAPER="$dir/costa-default.$ext"
                break 2
            fi
        done
        FOUND=$(find "$dir" -maxdepth 1 -type f \( -name "*.mp4" -o -name "*.webm" -o -name "*.mkv" -o -name "*.jpg" -o -name "*.png" \) 2>/dev/null | head -1)
        if [ -n "$FOUND" ]; then
            WALLPAPER="$FOUND"
            break
        fi
    done
fi

if [ -z "$WALLPAPER" ] || [ ! -f "$WALLPAPER" ]; then
    echo "No wallpaper found. Place an image or video in ~/Pictures/Wallpapers/"
    exit 0
fi

# Kill existing wallpaper processes
killall mpvpaper swww-daemon 2>/dev/null
sleep 0.5

# Detect file type and launch appropriate backend
EXT="${WALLPAPER##*.}"
case "$EXT" in
    mp4|webm|mkv|avi|mov)
        # Video wallpaper via mpvpaper
        if command -v mpvpaper &>/dev/null; then
            mpvpaper '*' "$WALLPAPER" \
                --fork \
                -o "no-audio loop panscan=1.0" \
                2>/dev/null
        else
            echo "mpvpaper not installed. Install with: pacman -S mpvpaper"
        fi
        ;;
    jpg|jpeg|png|webp|bmp)
        # Static wallpaper via swww
        if command -v swww &>/dev/null; then
            swww-daemon &disown 2>/dev/null
            sleep 0.3
            swww img "$WALLPAPER" --transition-type grow --transition-duration 1
        elif command -v swaybg &>/dev/null; then
            swaybg -i "$WALLPAPER" -m fill &disown 2>/dev/null
        else
            echo "No wallpaper backend found. Install swww or swaybg."
        fi
        ;;
    pkg|json)
        # Wallpaper Engine scene (via linux-wallpaperengine)
        if command -v linux-wallpaperengine &>/dev/null; then
            # Get scene directory (parent of the json/pkg file)
            SCENE_DIR="$(dirname "$WALLPAPER")"
            linux-wallpaperengine --screen-root '*' "$SCENE_DIR" &disown 2>/dev/null
        else
            echo "linux-wallpaperengine not installed. Install with: yay -S linux-wallpaperengine-git"
        fi
        ;;
    *)
        echo "Unsupported wallpaper format: $EXT"
        ;;
esac
