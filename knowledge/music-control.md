---
l0: "Music control: shell bar widget, player switching, queue management, search, playlists, keyboard shortcuts, playerctl"
l1_sections: ["Music Widget", "Cold Start", "Playback Controls", "Queue Management", "Search", "Playlists", "Player Switching", "Hide Player Window", "Keyboard Controls", "Shell Bar Integration", "Volume Control", "Switch Audio Output"]
tags: [music, play, pause, skip, volume, mute, playerctl, spotify, strawberry, widget, mpris, audio-output, queue, search, playlist, seek]
---

# Music Control

## Music Widget

### How do I open the music widget?
- Click the music icon (󰎆) in the shell bar
- Or click the now-playing text in the shell bar
- Or run: `costa-music-widget`

The widget shows album art, track info, progress bar, and playback controls.

## Cold Start

### How do I start playing music when nothing is running?
1. Open the music widget (click 󰎆 in the shell bar)
2. Click "Start Music" — this launches Strawberry and begins playback
3. If Strawberry has no library configured, it opens the library setup dialog

### How do I add music to Strawberry?
1. Open Strawberry: `strawberry`
2. Go to Tools → Preferences → Collection
3. Add your music folder (e.g., `~/Music/`)
4. Strawberry scans and indexes all tracks

## Playback Controls

### How do I play/pause?
- Music widget: click the play/pause button (center)
- Keyboard: media play/pause key, or `playerctl play-pause`
- Shell bar: middle-click the now-playing text

### How do I skip to next/previous track?
- Music widget: click the forward/back buttons
- Keyboard: media next/prev keys, or `playerctl next` / `playerctl previous`
- Shell bar: right-click the now-playing text (next track)

### How do I seek within a track?
- Music widget: click anywhere on the progress bar to jump
- Shell bar: scroll up/down on the now-playing text (±5 seconds)
- CLI: `playerctl position 10+` (forward 10s), `playerctl position 10-` (back 10s)
- Jump to position: `playerctl position 30` (30 seconds in)

### How do I toggle shuffle and repeat?
- Music widget: click the shuffle icon (🔀) or repeat icon (🔁)
- Repeat modes: off → repeat all → repeat one (cycles on click)
- CLI: `playerctl shuffle toggle` / `playerctl loop Track` / `playerctl loop Playlist` / `playerctl loop None`

## Queue Management

### How do I see the play queue?
Click the **Queue** tab in the music widget. Shows the current playlist with:
- Track name, artist, duration
- Currently playing track highlighted
- Click any track to jump to it
- Drag tracks to reorder

### How do I add a track to the queue?
In the Search tab, right-click a track → "Add to Queue"

## Search

### How do I search my music library?
1. Open the music widget
2. Click the **Search** tab
3. Type to search across artist, album, and track name
4. Click a result to play it immediately
5. Right-click a result for options (add to queue, add to playlist)

## Playlists

### How do I switch playlists?
1. Open the music widget
2. Click the **Playlists** tab
3. Click a playlist name to load and play it

### How do I create a playlist?
Use Strawberry directly — playlists created there appear in the widget:
1. Open Strawberry
2. Right-click in the playlist area → "New Playlist"
3. Drag tracks from your library into the playlist

## Player Switching

### How do I switch between music players?
The music widget has a dropdown in the header showing the active player. Click it to switch between:
- **Strawberry** — local music library
- **Spotify** — streaming (via spotify-launcher)
- **Firefox** — browser audio/video
- Any other MPRIS-compatible player

### How do I control a specific player from the CLI?
```bash
# List all active players
playerctl --list-all

# Control a specific player
playerctl -p strawberry play-pause
playerctl -p spotify next
playerctl -p firefox play-pause
```

## Hide Player Window

### How do I hide the Strawberry window?
Click the **eye icon** in the music widget header. This minimizes Strawberry to the system tray — the widget still controls it.

To bring it back, click the eye icon again or click the Strawberry tray icon.

## Keyboard Controls
These work globally regardless of focused window:

| Key | Action |
|-----|--------|
| Media Play/Pause | Play/pause current player |
| Media Next | Next track |
| Media Previous | Previous track |
| Media Stop | Stop playback |
| `playerctl play-pause` | Play/pause (CLI) |
| `playerctl next` | Next track (CLI) |
| `playerctl previous` | Previous track (CLI) |

## Shell Bar Integration

### What do the shell bar music controls do?
The now-playing text in the shell bar responds to mouse actions:
- **Left-click** — opens the music widget
- **Middle-click** — play/pause
- **Right-click** — next track
- **Scroll up** — seek forward 5 seconds
- **Scroll down** — seek backward 5 seconds

### What does the shell bar display show?
- Artist — Track Name (scrolling if too long)
- Play/pause icon changes based on state
- Empty/hidden when no player is active

## Volume Control

### How do I change the volume?
```bash
# Set to 50%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.5

# Increase by 5%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+

# Decrease by 5%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-

# Mute/unmute (wpctl takes 1, 0, or toggle — NOT true/false)
wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
wpctl set-mute @DEFAULT_AUDIO_SINK@ 0   # unmute
wpctl set-mute @DEFAULT_AUDIO_SINK@ 1   # mute
```

### How do I mute the microphone?
```bash
wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle
```

## Switch Audio Output

### How do I switch speakers/headphones?
```bash
# List outputs
pactl list sinks short

# Switch default output
pactl set-default-sink SINK_NAME

# GUI: use qpwgraph or pavucontrol
qpwgraph    # visual audio routing
pavucontrol # traditional mixer
```
