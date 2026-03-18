# Costa OS — System Requirements

## Hardware Tiers

### Minimum (Cloud-Only AI)
- x86_64 processor, 2+ cores
- 4GB RAM
- 20GB disk space
- Any GPU with Vulkan support (for compositor)
- UEFI boot (no legacy BIOS)
- Network connection required for AI (all queries go to Claude API)
- Voice assistant: not available (no local inference)

### Recommended (Voice + Local LLM)
- 4+ cores (AMD Ryzen 5 / Intel i5 or better)
- 16GB RAM
- 40GB disk space (OS + models)
- 8GB+ VRAM discrete GPU (AMD RX 6700 XT / NVIDIA RTX 3070 or better)
- Voice: Whisper tiny.en with GPU acceleration (~0.5s transcription)
- LLM: qwen2.5:7b resident in VRAM

### Full Workstation
- 8+ cores
- 32GB RAM
- 80GB disk space
- 12GB+ VRAM (AMD RX 7900 / NVIDIA RTX 4080 or better)
- LLM: qwen2.5:14b resident, gaming mode auto-unloads
- Voice + LLM + gaming simultaneously via VRAM manager

## GPU Compatibility

| Feature | AMD (tested) | NVIDIA (supported) | Intel (basic) |
|---------|-------------|-------------------|---------------|
| Compositor (Hyprland) | Full | Full | Full |
| Local LLM (Ollama) | ROCm | CUDA | CPU-only |
| Whisper (STT) | Vulkan GPU | CUDA GPU | CPU fallback |
| VRAM Manager | sysfs monitoring | nvidia-smi | N/A |
| GPU Waybar modules | amdgpu hwmon | nvidia-smi | N/A |

### GPU Driver Installation
GPU drivers are NOT included in the ISO — they're installed by `first-boot.sh` based on detected hardware:
- **AMD**: `vulkan-radeon`, `lib32-vulkan-radeon`
- **NVIDIA**: `nvidia`, `nvidia-utils`, `lib32-nvidia-utils`
- **Intel**: `vulkan-intel`

## Audio Requirements
- **Microphone**: Any USB or analog mic (Blue Snowball tested)
- **Speakers/DAC**: PipeWire handles all audio routing
- **Voice Assistant**: Requires working PipeWire + microphone
- DeepFilterNet pre-processing handles noisy environments

## Optional Hardware

### IR Camera (Face Authentication)
- Any USB or built-in IR camera supported by `v4l-utils`
- Detected automatically during first-boot via `v4l2-ctl`
- Enables Windows Hello-style face unlock via Howdy (AUR)
- Works with: greetd (login), sudo, hyprlock (screen lock)
- Password always available as fallback

### Touchscreen
- Any touchscreen supported by libinput
- Detected automatically during first-boot
- Enables: touch input, on-screen keyboard (squeekboard), multi-touch gestures (hyprgrass)
- Gestures: 3-finger swipe for workspace switching, long press to move windows

## Known Limitations
- **UEFI-only** — no legacy BIOS boot support
- **qwen3 models** idle RDNA4 GPUs at 100% — use qwen2.5 series instead
- **Intel iGPU** — cloud-only AI or CPU inference (very slow)
- **Whisper** — English-only (tiny.en model). Multilingual support planned
- **Echo cancellation** — uses audio ducking workaround, proper AEC planned
- **DaVinci Resolve** — not auto-installed (requires manual download from Blackmagic)
- **Wallpaper Engine** — optional, requires Steam purchase. 3D scenes may crash on some GPUs. Video/2D scenes work reliably.

## Software Dependencies
All dependencies are installed automatically. For reference:

### Core
- Arch Linux (base, base-devel, linux, linux-firmware)
- Hyprland (compositor), Waybar (bar), Ghostty (terminal)
- PipeWire + WirePlumber (audio)
- Python 3.12+ (AI router, settings, keybinds GUI)
- GTK4 + libadwaita (GUI apps)

### AI Layer
- Ollama (local LLM inference via ROCm/CUDA)
- whisper.cpp (speech-to-text, built from source during first-boot)
- DeepFilterNet LADSPA (noise reduction)
- Silero VAD (speech detection, PyTorch)

### Optional
- Docker + docker-compose (dev tools)
- Vesktop (Discord with Wayland support)
- Creative suite: GIMP, Inkscape, Krita, REAPER, OBS Studio
- Howdy (AUR) — face authentication (requires IR camera)
- squeekboard — on-screen keyboard (requires touchscreen)
- hyprgrass (AUR) — touch gestures (requires touchscreen)
