---
l0: "Push-to-talk voice control: keybinds, audio pipeline, text input, model routing, troubleshooting"
l1_sections: ["Push-to-Talk Keybinds", "How It Works", "Auto-Submit Control", "Text Input Alternative", "Viewing Responses", "Audio Pipeline", "Troubleshooting", "Customization"]
tags: [voice, ptt, push-to-talk, whisper, speech, microphone, transcription, vad, deepfilternet]
---
# Costa OS Voice Assistant

## Push-to-Talk Keybinds

| Key | Mode | What Happens |
|-----|------|-------------|
| `SUPER+ALT+V` | Claude mode | AI processes your command and responds |
| `SUPER+ALT+B` | Type mode | Transcribes speech and types it into the focused window |

Hold the key while speaking. Release when done.

## How It Works

1. Hold `SUPER+ALT+V` (or B) and speak
2. Audio is captured and noise-reduced in real time
3. Silero VAD detects when you stop speaking (auto-stop)
4. Whisper transcribes your speech on GPU
5. Query routes to the best model (local or cloud)
6. Response appears in the shell bar notification area

## Auto-Submit Control

Commands auto-execute by default. To prevent this:
- Say **"draft"** or **"hold"** anywhere in your sentence
- The transcribed text will appear for review instead of executing

## Text Input Alternative

Don't want to talk? Use text input:
- **Left-click** the Costa icon (center of the shell bar) → type in the rofi text box
- Press Enter to submit

## Viewing Responses

- Responses scroll across the shell bar after processing
- **Right-click** the Costa icon to see the full last output
- Longer responses open in a notification popup (dunst)

## Audio Pipeline

```
Blue Snowball mic
  → DeepFilterNet (noise reduction, crushes noise floor from ~0.2 to ~0.004 RMS)
  → Silero VAD (auto-detects speech end)
  → Whisper tiny.en (GPU-accelerated via Vulkan)
  → costa-ai smart router
  → response
```

Audio ducks to 17% while recording to prevent echo feedback.

## Troubleshooting

Check current status:
```sh
cat /tmp/ptt-voice-status     # current PTT state
cat /tmp/ptt-voice-output     # last transcription/response
```

Restart the PTT system:
```sh
killall push-to-talk.sh
# It will restart automatically from hyprland, or manually:
~/.config/costa/push-to-talk.sh &disown
```

Common issues:

| Problem | Fix |
|---------|-----|
| No audio captured | `wpctl status` — check default source is Blue Snowball |
| Transcription garbage | Background noise too high — check DeepFilterNet is running |
| VAD won't stop recording | Silero needs DeepFilterNet preprocessing — check pipeline |
| Slow response | `ollama ps` — model may not be loaded, check VRAM tier |
| Nothing happens on keypress | Check `hyprctl binds | grep ALT+V` — keybind may be missing |

## Customization

```sh
# Change VAD sensitivity
~/.config/costa/vad/vad_daemon.py     # edit threshold values

# Change Whisper model (tiny.en = fastest, small.en = more accurate)
# Edit WHISPER_MODEL in push-to-talk.sh

# Change auto-submit default
# Edit push-to-talk.sh — look for AUTO_SUBMIT variable
```
