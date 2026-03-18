#!/bin/bash
# Git status for active project based on focused window

# Get active window title
title=$(hyprctl activewindow -j 2>/dev/null | jq -r '.title // ""')
class=$(hyprctl activewindow -j 2>/dev/null | jq -r '.class // ""')

dir=""

# Try to extract project dir from VS Code title
if [[ "$class" == *"code"* ]] || [[ "$class" == *"Code"* ]]; then
  # VS Code title format: "filename - projectname - Visual Studio Code"
  project=$(echo "$title" | sed -n 's/.* - \(.*\) - Visual Studio Code/\1/p')
  if [ -d "$HOME/projects/$project" ]; then
    dir="$HOME/projects/$project"
  fi
fi

# Try to extract from terminal title / ghostty
if [ -z "$dir" ] && [[ "$class" == *"ghostty"* ]] || [[ "$class" == *"terminal"* ]]; then
  for d in ~/projects/*/; do
    name=$(basename "$d")
    if echo "$title" | grep -qi "$name"; then
      dir="$d"
      break
    fi
  done
fi

# Fallback: check most recently modified project
if [ -z "$dir" ]; then
  dir=$(find ~/projects -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | awk '{print $2}')
fi

if [ -z "$dir" ] || [ ! -d "$dir/.git" ]; then
  jq -nc '{text: "", tooltip: "No git project active", class: "inactive"}'
  exit 0
fi

cd "$dir" || exit 1

branch=$(git symbolic-ref --short HEAD 2>/dev/null || git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD 2>/dev/null)
project=$(basename "$dir")

# Count changes
staged=$(git diff --cached --numstat 2>/dev/null | wc -l)
unstaged=$(git diff --numstat 2>/dev/null | wc -l)
untracked=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l)

dirty=""
[ "$staged" -gt 0 ] && dirty+=" +$staged"
[ "$unstaged" -gt 0 ] && dirty+=" ~$unstaged"
[ "$untracked" -gt 0 ] && dirty+=" ?$untracked"

if [ -z "$dirty" ]; then
  icon=""
  cls="clean"
else
  icon=""
  cls="dirty"
fi

jq -nc --arg text "$icon $branch" --arg tooltip "$project ($branch)$dirty" --arg class "$cls" \
  '{text: $text, tooltip: $tooltip, class: $class}'
