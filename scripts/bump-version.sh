#!/bin/bash
# Bump Costa OS version by 0.0.1, update VERSION file, create git tag
# Usage: ./scripts/bump-version.sh [--no-tag]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_DIR/VERSION"

if [ ! -f "$VERSION_FILE" ]; then
    echo "ERROR: VERSION file not found at $VERSION_FILE"
    exit 1
fi

CURRENT=$(cat "$VERSION_FILE" | tr -d '[:space:]')
echo "Current version: $CURRENT"

# Split into major.minor.patch and increment patch
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"
PATCH=$((PATCH + 1))
NEW="$MAJOR.$MINOR.$PATCH"

echo "$NEW" > "$VERSION_FILE"
echo "Bumped to: $NEW"

if [ "$1" != "--no-tag" ]; then
    git add "$VERSION_FILE"
    git commit -m "Release v$NEW"
    git tag -a "v$NEW" -m "Costa OS v$NEW"
    echo "Created git tag: v$NEW"
    echo ""
    echo "To push: git push && git push --tags"
fi
