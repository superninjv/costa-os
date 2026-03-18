---
l0: "Notification management: dunst commands, do-not-disturb, history, configuration"
l1_sections: ["Commands", "Config", "Common Settings"]
tags: [notification, dunst, dnd, do-not-disturb, dismiss, alert, toast, history]
---

# Notifications (Dunst)

## Commands
- Send notification: `notify-send "Title" "Message body"`
- With icon: `notify-send -i firefox "Title" "Body"`
- Urgent: `notify-send -u critical "Title" "Body"`
- With timeout: `notify-send -t 5000 "Title" "5 second notification"`
- Show notification history: `dunstctl history-pop`
- Dismiss current: `dunstctl close`
- Dismiss all: `dunstctl close-all`
- Toggle Do Not Disturb: `dunstctl set-paused toggle`
- Check if paused: `dunstctl is-paused`

## Config
- File: `~/.config/dunst/dunstrc`
- Reload: `killall dunst; dunst &disown` (auto-restarts on next notification)

## Common Settings
- Change position: edit `origin` in dunstrc (top-right, top-left, bottom-right, etc.)
- Change max notifications shown: `notification_limit`
- Change timeout: `timeout` in urgency sections
- Change font: `font`
