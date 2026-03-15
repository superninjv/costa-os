# Costa OS Smart Command Suggestions — zsh plugin
#
# Shows intelligent command suggestions in RPROMPT based on
# shell history patterns, per-directory frequencies, and workflows.
#
# Usage: source this file in .zshrc
#   source /path/to/costa-suggest.zsh
#
# Features:
#   - After each command, shows top suggestion as dim text in RPROMPT
#   - TAB-TAB (double tab) to accept the suggestion
#   - Learns from your command patterns over time
#   - Stores patterns in ~/.config/costa/command_patterns.json

# Path to the smart commands script
COSTA_SUGGEST_SCRIPT="${COSTA_SUGGEST_SCRIPT:-$(dirname "${(%):-%x}")/../../ai-router/smart_commands.py}"

# State
typeset -g _costa_suggestion=""
typeset -g _costa_last_exit=0
typeset -g _costa_last_tab_time=0
typeset -g _costa_suggest_enabled=1

# Record exit code after each command
_costa_precmd() {
    _costa_last_exit=$?

    # Don't run if disabled
    [[ "$_costa_suggest_enabled" -eq 0 ]] && return

    # Get the last few commands from fc (zsh builtin)
    local -a recent_cmds
    recent_cmds=("${(@f)$(fc -ln -3 -1 2>/dev/null)}")

    # Skip if no recent commands
    [[ ${#recent_cmds} -eq 0 ]] && return

    # Call smart_commands.py asynchronously to avoid blocking the prompt
    _costa_suggestion=""

    local result
    result=$(COSTA_LAST_EXIT="$_costa_last_exit" python3 "$COSTA_SUGGEST_SCRIPT" "${recent_cmds[@]}" 2>/dev/null | head -1)

    if [[ -n "$result" ]]; then
        # Extract just the suggestion (before the tab-separated confidence)
        _costa_suggestion="${result%%	*}"
    fi

    # Update RPROMPT with suggestion
    if [[ -n "$_costa_suggestion" ]]; then
        RPROMPT="%F{8}${_costa_suggestion}%f"
    else
        RPROMPT=""
    fi
}

# Accept suggestion on double-TAB
_costa_accept_suggestion() {
    local now=$(date +%s)

    # Check for double-tab (within 0.8 seconds)
    if (( now - _costa_last_tab_time <= 1 )); then
        if [[ -n "$_costa_suggestion" && -z "$BUFFER" ]]; then
            # Accept the suggestion
            BUFFER="$_costa_suggestion"
            CURSOR=${#BUFFER}
            _costa_suggestion=""
            RPROMPT=""
            zle reset-prompt
            return
        fi
    fi

    _costa_last_tab_time=$now

    # Fall through to normal tab completion if buffer is non-empty
    # or if this isn't a double-tap
    if [[ -n "$BUFFER" ]]; then
        zle expand-or-complete
    fi
}

# Toggle suggestions on/off
costa-suggest-toggle() {
    if [[ "$_costa_suggest_enabled" -eq 1 ]]; then
        _costa_suggest_enabled=0
        _costa_suggestion=""
        RPROMPT=""
        echo "Costa suggestions disabled"
    else
        _costa_suggest_enabled=1
        echo "Costa suggestions enabled"
    fi
}

# Initialize
_costa_setup() {
    # Ensure config directory exists
    mkdir -p ~/.config/costa

    # Register precmd hook
    autoload -Uz add-zsh-hook
    add-zsh-hook precmd _costa_precmd

    # Create the widget for double-tab acceptance
    zle -N _costa_accept_suggestion

    # Bind TAB to our handler — we call expand-or-complete internally
    # when the buffer has content, so normal completion still works
    bindkey '^I' _costa_accept_suggestion
}

_costa_setup
