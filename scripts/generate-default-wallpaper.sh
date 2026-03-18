#!/bin/bash
# Generate Costa OS default wallpaper — dark navy to deep sea gradient
# Output: branding/costa-default.png (3840x2160)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT="$PROJECT_DIR/branding/costa-default.png"
WIDTH=3840
HEIGHT=2160
COLOR_BASE="#1b1d2b"
COLOR_SEA="#4a7d8f"

mkdir -p "$(dirname "$OUTPUT")"

# Try PIL first, fall back to ImageMagick
if python3 -c "from PIL import Image" 2>/dev/null; then
    echo "Using Python PIL..."
    python3 - "$OUTPUT" "$WIDTH" "$HEIGHT" <<'PYEOF'
import sys
from PIL import Image

output, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

# Colors: dark navy base -> deep sea
r1, g1, b1 = 0x1b, 0x1d, 0x2b  # #1b1d2b
r2, g2, b2 = 0x4a, 0x7d, 0x8f  # #4a7d8f

img = Image.new("RGB", (w, h))
pixels = img.load()

for y in range(h):
    for x in range(w):
        # Gradient from bottom-left to top-right
        t = ((x / w) + (1.0 - y / h)) / 2.0
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        pixels[x, y] = (r, g, b)

img.save(output, "PNG")
print(f"Saved {output} ({w}x{h})")
PYEOF

elif command -v magick &>/dev/null || command -v convert &>/dev/null; then
    echo "Using ImageMagick..."
    # ImageMagick 7 uses 'magick', older versions use 'convert'
    CMD="magick"
    command -v magick &>/dev/null || CMD="convert"

    # Gradient from bottom-left (#1b1d2b) to top-right (#4a7d8f)
    # Create two gradients and composite for diagonal effect
    $CMD -size "${WIDTH}x${HEIGHT}" \
        \( gradient:"${COLOR_SEA}-${COLOR_BASE}" -rotate 90 \) \
        \( gradient:"${COLOR_BASE}-${COLOR_SEA}" \) \
        -compose Blend -define compose:args=50,50 -composite \
        "$OUTPUT"
    echo "Saved $OUTPUT (${WIDTH}x${HEIGHT})"
else
    echo "Error: Neither PIL (python3 + Pillow) nor ImageMagick found."
    echo "Install one of:"
    echo "  pip install Pillow"
    echo "  sudo pacman -S imagemagick"
    exit 1
fi
