#!/bin/bash
# Upload Costa OS ISO to DigitalOcean Spaces and remove old versions
# Requires: s3cmd configured for DO Spaces
# Usage: ./scripts/upload-iso.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$PROJECT_DIR/out"
VERSION=$(cat "$PROJECT_DIR/VERSION" | tr -d '[:space:]')
BUCKET="s3://costa-os"
ISO_NAME="costa-os-${VERSION}-x86_64.iso"

# Find the built ISO
ISO_FILE=$(ls -t "$OUT_DIR"/costa-os-*.iso 2>/dev/null | head -1)

if [ -z "$ISO_FILE" ]; then
    echo "ERROR: No ISO found in $OUT_DIR"
    echo "Run: sudo ./scripts/build-iso.sh"
    exit 1
fi

echo "╔══════════════════════════════════════╗"
echo "║     Costa OS — ISO Upload            ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "ISO:     $ISO_FILE"
echo "Version: $VERSION"
echo "Target:  $BUCKET/$ISO_NAME"
echo ""

# Check s3cmd config
if ! command -v s3cmd &>/dev/null; then
    echo "ERROR: s3cmd not installed. Install with: sudo pacman -S s3cmd"
    echo "Configure with: s3cmd --configure"
    echo "  Host: nyc3.digitaloceanspaces.com"
    echo "  Access/Secret: from DO Spaces settings"
    exit 1
fi

# Rename ISO to versioned name if needed
if [ "$(basename "$ISO_FILE")" != "$ISO_NAME" ]; then
    VERSIONED="$OUT_DIR/$ISO_NAME"
    cp "$ISO_FILE" "$VERSIONED"
    ISO_FILE="$VERSIONED"
    echo "Renamed to: $ISO_NAME"
fi

# Generate SHA256 checksum
echo "→ Generating checksum..."
sha256sum "$ISO_FILE" > "$ISO_FILE.sha256"
echo "  $(cat "$ISO_FILE.sha256")"

# List and remove old ISOs
echo ""
echo "→ Checking for old ISOs in Spaces..."
OLD_ISOS=$(s3cmd ls "$BUCKET/" 2>/dev/null | grep "costa-os-.*\.iso" | awk '{print $4}' || true)
if [ -n "$OLD_ISOS" ]; then
    echo "  Removing old versions:"
    for old in $OLD_ISOS; do
        echo "    - $(basename "$old")"
        s3cmd del "$old" 2>/dev/null || true
        s3cmd del "${old}.sha256" 2>/dev/null || true
    done
fi

# Upload new ISO
echo ""
echo "→ Uploading $ISO_NAME ($(du -h "$ISO_FILE" | cut -f1))..."
s3cmd put "$ISO_FILE" "$BUCKET/$ISO_NAME" \
    --acl-public \
    --mime-type="application/x-iso9660-image" \
    --progress

echo "→ Uploading checksum..."
s3cmd put "$ISO_FILE.sha256" "$BUCKET/$ISO_NAME.sha256" \
    --acl-public \
    --mime-type="text/plain"

# Upload latest version marker
echo "$VERSION" > /tmp/costa-latest
s3cmd put /tmp/costa-latest "$BUCKET/LATEST" --acl-public --mime-type="text/plain"
rm -f /tmp/costa-latest

echo ""
echo "→ Upload complete!"
echo "  ISO: https://costa-os.nyc3.digitaloceanspaces.com/$ISO_NAME"
echo "  SHA: https://costa-os.nyc3.digitaloceanspaces.com/$ISO_NAME.sha256"
echo "  Latest: https://costa-os.nyc3.digitaloceanspaces.com/LATEST"
