# Costa OS Voice Assistant

Push-to-talk voice assistant with AI-powered smart routing. Voice input is the primary interface for Costa OS.

## Pipeline

```
Microphone (pw-cat)
    |
    v
DeepFilterNet (LADSPA noise reduction)
    |  Crushes mic noise floor from ~0.2 RMS to ~0.004 RMS
    v
Silero VAD (voice activity detection)
    |  Auto-stops recording when speech ends (~1.5s silence)
    v
Whisper (speech-to-text, Vulkan GPU accelerated)
    |  tiny.en model, ~0.5s transcription
    v
costa-ai router (smart model selection)
    |  Local Ollama first, auto-escalates to Claude API if needed
    v
Response (notification, scrolling waybar text, or interactive terminal)
```

## Modes

- **Claude mode** (`SUPER+ALT+V`): Transcribed text is routed through costa-ai for an AI response.
- **Type mode** (`SUPER+ALT+B`): Transcribed text is typed into the focused window via wtype.

Say "draft" or "hold" to prevent auto-submit. Say "send it" or "confirm" to explicitly submit.

## Components

| File | Description |
|------|-------------|
| `src/push-to-talk.sh` | Main PTT script. Handles recording, transcription, routing, and response display. |
| `src/vad_daemon.py` | Persistent daemon that keeps Silero VAD loaded in memory for fast speech detection. |
| `src/vad_record.py` | Standalone VAD recorder (loads model per invocation, used as fallback or for testing). |

## Configuration

All components support configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COSTA_WHISPER_BIN` | `whisper-cli` (from PATH) or `$HOME/.local/bin/whisper-cli` | Path to whisper-cli binary |
| `COSTA_WHISPER_MODEL` | `$HOME/.local/share/costa/whisper/ggml-tiny.en.bin` | Path to Whisper GGML model |
| `COSTA_AI_ROUTER` | `/usr/local/bin/costa-ai` | Path to costa-ai router script |
| `COSTA_DEEPFILTER_LADSPA` | `/usr/lib/ladspa/libdeep_filter_ladspa.so` | Path to DeepFilterNet LADSPA plugin |
| `COSTA_TERMINAL` | `ghostty` | Terminal emulator for interactive sessions |
| `COSTA_OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `COSTA_OLLAMA_FAST` | `qwen2.5:3b` | Fast model for summaries |
| `COSTA_OLLAMA_DEFAULT` | `qwen2.5:14b` | Default model (overridden by VRAM manager) |
| `COSTA_VAD_SAMPLE_RATE` | `16000` | Audio sample rate |
| `COSTA_VAD_THRESHOLD` | `0.25` | VAD speech probability threshold |
| `COSTA_VAD_MAX_DURATION` | `15.0` | Maximum recording duration in seconds |
| `COSTA_SYSTEM_PROMPT` | `$HOME/.config/costa/system-ai.md` | System prompt file for AI context |

## Dependencies

- **PipeWire** (pw-cat for recording, wpctl for volume control)
- **sox** with LADSPA support
- **DeepFilterNet** LADSPA plugin
- **whisper.cpp** built with Vulkan support
- **Python 3** with torch, numpy
- **Silero VAD** (downloaded automatically via torch.hub)
- **jq**, **wl-copy**, **wtype**, **notify-send**
- **Ollama** (local LLM inference)
