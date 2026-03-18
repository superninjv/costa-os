#!/bin/bash
# Project switcher — open terminal or VS Code in a project dir

action="${1:-terminal}"

project=$(find ~/projects -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort | \
  rofi -dmenu -p "Project" -i -theme-str 'window {width: 300px;}')

[ -z "$project" ] && exit 0

dir="$HOME/projects/$project"

case "$action" in
  terminal)
    ghostty -e bash -c "cd '$dir' && exec zsh"
    ;;
  code)
    code "$dir"
    ;;
esac
