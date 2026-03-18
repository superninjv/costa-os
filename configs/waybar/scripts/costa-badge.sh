#!/bin/bash
# Costa OS badge — shows a small "Costa" watermark in the waybar.
# Hidden when a valid license is present at ~/.config/costa/license

LICENSE="$HOME/.config/costa/license"

if [ -f "$LICENSE" ]; then
    # Licensed — check validity
    KEY=$(jq -r '.key // ""' "$LICENSE" 2>/dev/null)
    if [ -n "$KEY" ] && [[ "$KEY" == COSTA-* ]]; then
        # Valid license — show nothing
        echo '{"text": "", "alt": "pro", "class": "licensed"}'
        exit 0
    fi
fi

# Free version — show small watermark
echo '{"text": "Costa", "tooltip": "Costa OS Free — click to support the project ($9.99)", "alt": "free", "class": "free"}'
