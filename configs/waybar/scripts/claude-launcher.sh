#!/bin/bash
# Claude Code launcher with model selection via rofi
# Uses login shell to ensure nvm/pyenv/etc PATH is available

CLAUDE_CMD="claude"
SHELL_WRAPPER="zsh -lc"

action="${1:-launch}"

launch_claude() {
  local dir="$1"
  local args="$2"
  local TERM=""
  for t in ghostty foot kitty alacritty; do
    command -v "$t" &>/dev/null && TERM="$t" && break
  done
  case "$TERM" in
    ghostty)   ghostty -e $SHELL_WRAPPER "cd '${dir:-$HOME}' && $CLAUDE_CMD $args" ;;
    foot)      foot $SHELL_WRAPPER "cd '${dir:-$HOME}' && $CLAUDE_CMD $args" ;;
    kitty)     kitty $SHELL_WRAPPER "cd '${dir:-$HOME}' && $CLAUDE_CMD $args" ;;
    alacritty) alacritty -e $SHELL_WRAPPER "cd '${dir:-$HOME}' && $CLAUDE_CMD $args" ;;
    *)         echo "No terminal found" ;;
  esac
}

case "$action" in
  menu)
    # Rofi model picker
    choice=$(printf "󰚩 Opus (claude-opus-4-6)\n Sonnet (claude-sonnet-4-6)\n Haiku (claude-haiku-4-5)" | \
      rofi -dmenu -p "Claude Model" -i -theme-str 'window {width: 350px;}')

    case "$choice" in
      *Opus*)   model="claude-opus-4-6" ;;
      *Sonnet*) model="claude-sonnet-4-6" ;;
      *Haiku*)  model="claude-haiku-4-5" ;;
      *)        exit 0 ;;
    esac

    # Pick project directory
    project=$(find ~/projects -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort | \
      rofi -dmenu -p "Project" -i -theme-str 'window {width: 300px;}')

    if [ -n "$project" ]; then
      dir="$HOME/projects/$project"
    else
      dir="$HOME"
    fi

    launch_claude "$dir" "--model '$model'"
    ;;

  launch)
    # Quick launch in home dir
    launch_claude "$HOME" ""
    ;;

  dangerous)
    # Launch with all permissions (no confirmation prompts)
    # Rofi confirmation first
    confirm=$(printf "Yes, launch dangerously\nNo, cancel" | \
      rofi -dmenu -p "⚠ Skip all permission prompts?" -i -theme-str 'window {width: 450px;}')

    if [[ "$confirm" == *"Yes"* ]]; then
      # Pick project directory
      project=$(find ~/projects -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort | \
        rofi -dmenu -p "Project" -i -theme-str 'window {width: 300px;}')

      if [ -n "$project" ]; then
        dir="$HOME/projects/$project"
      else
        dir="$HOME"
      fi

      launch_claude "$dir" "--dangerously-skip-permissions"
    fi
    ;;

  project)
    # Scroll action: pick project, launch with default model
    project=$(find ~/projects -maxdepth 1 -mindepth 1 -type d -printf "%f\n" | sort | \
      rofi -dmenu -p "Project" -i -theme-str 'window {width: 300px;}')

    if [ -n "$project" ]; then
      launch_claude "$HOME/projects/$project" ""
    fi
    ;;
esac
