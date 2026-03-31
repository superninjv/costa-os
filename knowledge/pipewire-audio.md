---
l0: "PipeWire audio management: volume, mute, sink/source selection, debugging, LADSPA plugins"
l1_sections: ["Quick Commands", "Status / Debug", "Services", "Common Fixes"]
tags: [audio, sound, volume, pipewire, wireplumber, wpctl, pactl, speaker, microphone, sink, source, crackling]
---
# PipeWire / Audio Management

## Quick Commands
- Volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.5` (0.0-1.0+)
- Mute toggle: `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle`
- Mute on: `wpctl set-mute @DEFAULT_AUDIO_SINK@ 1`
- Unmute: `wpctl set-mute @DEFAULT_AUDIO_SINK@ 0`
- NOTE: wpctl set-mute takes `1`, `0`, or `toggle` — NOT `true`/`false`/`on`/`off`
- Mic volume: `wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 1.0`
- Current volume: `wpctl get-volume @DEFAULT_AUDIO_SINK@`
- Default source: `pactl get-default-source`
- Default sink: `pactl get-default-sink`
- Set default: `pactl set-default-source "device_name"`
- List sources: `pactl list sources short`
- List sinks: `pactl list sinks short`

## Status / Debug
- `wpctl status` — full audio graph
- `pw-top` — real-time audio activity
- `pw-cli ls Node` — list all nodes
- `qpwgraph` — GUI audio routing

## Services
- `systemctl --user restart pipewire pipewire-pulse wireplumber`
- Config: `~/.config/pipewire/`, `/etc/pipewire/`
- WirePlumber config: `~/.config/wireplumber/`

## Common Fixes
- No sound: check `wpctl status`, verify default sink is correct
- Wrong device: `pactl set-default-sink "device_name"`
- Crackling: increase quantum in pipewire.conf (`default.clock.quantum = 512`)
- App not showing: restart PipeWire (`systemctl --user restart pipewire`)
- LADSPA plugins: `/usr/lib/ladspa/`, use via `pw-filter` or EasyEffects
- `pw-cat --target` flag is unreliable — always use the default source
- PipeWire filter chains can silently intercept the default source — verify with `pactl get-default-source` after changes
- `pw-cat` stdout pipe prepends a SPA header — use file recording mode for reliable audio capture
