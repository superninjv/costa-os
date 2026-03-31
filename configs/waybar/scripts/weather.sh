#!/bin/bash
# Weather for waybar via wttr.in

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/costa"
LOCATION_FILE="$CONFIG_DIR/weather-location"
cache="/tmp/waybar-weather"
cache_age=1800  # 30 min

# Set location interactively (called with --set)
if [ "$1" = "--set" ]; then
  mkdir -p "$CONFIG_DIR"
  current=""
  [ -f "$LOCATION_FILE" ] && current=$(cat "$LOCATION_FILE")
  new_loc=$(rofi -dmenu -p "Weather location (city name)" -theme-str 'window {width: 450px;} listview {lines: 0;}' \
    -filter "$current" <<< "")
  if [ -n "$new_loc" ]; then
    echo "$new_loc" > "$LOCATION_FILE"
    rm -f "$cache"
    notify-send -a "Costa Weather" "Location set" "$new_loc — refreshing weather..."
    # Force refresh by continuing to the fetch below
  else
    exit 0
  fi
fi

# Read configured location (empty = auto-detect by IP)
LOCATION=""
if [ -f "$LOCATION_FILE" ]; then
  LOCATION=$(cat "$LOCATION_FILE")
fi

# Use cache if fresh enough (skip if --set just cleared it)
if [ -f "$cache" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$cache") ))
  if [ "$age" -lt "$cache_age" ]; then
    cat "$cache"
    exit 0
  fi
fi

# URL-encode location for wttr.in (percent-encode non-alphanumeric chars)
ENCODED_LOC=$(printf '%s' "$LOCATION" | python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))" 2>/dev/null || printf '%s' "$LOCATION" | sed 's/ /+/g')

# Fetch weather
data=$(curl -sf "wttr.in/${ENCODED_LOC}?format=j1" 2>/dev/null)
if [ -z "$data" ]; then
  jq -nc '{text: "N/A", tooltip: "Weather unavailable — right-click to set location"}'
  exit 0
fi

# Handle both wrapped (.data.) and unwrapped formats from wttr.in
# Extract fields individually (no eval — prevents injection from remote data)
_jq_base='(if .data then .data else . end).current_condition[0]'
temp=$(echo "$data" | jq -r "$_jq_base.temp_F // empty")
desc=$(echo "$data" | jq -r "$_jq_base.weatherDesc[0].value // empty")
feels=$(echo "$data" | jq -r "$_jq_base.FeelsLikeF // empty")
humidity=$(echo "$data" | jq -r "$_jq_base.humidity // empty")
code=$(echo "$data" | jq -r "$_jq_base.weatherCode // empty")
area=$(echo "$data" | jq -r '(if .data then .data else . end).nearest_area[0].areaName[0].value // (if .data then .data else . end).request[0].query // "Unknown"')
case "$code" in
  113) icon="" ;;          # Clear
  116) icon="" ;;          # Partly cloudy
  119|122) icon="" ;;      # Cloudy/Overcast
  176|266|293|296|299|302|305|308|311|314|317) icon="" ;; # Rain
  200|386|389|392|395) icon="" ;; # Thunder
  227|230|320|323|326|329|332|335|338|350|353|356|359|362|365|368|371|374|377) icon="" ;; # Snow
  143|248|260) icon="" ;;  # Fog
  *) icon="" ;;
esac

# Location hint in tooltip
loc_hint=""
if [ -z "$LOCATION" ]; then
  loc_hint="
(auto-detected — right-click to set location)"
fi

tooltip="$area: $desc
Feels like ${feels}°F
Humidity: ${humidity}%$loc_hint"

output=$(jq -nc --arg text "$icon ${temp}°" --arg tooltip "$tooltip" \
  '{text: $text, tooltip: $tooltip}')
echo "$output" | tee "$cache"
