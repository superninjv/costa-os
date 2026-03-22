# Costa OS — Hardware Compatibility

## GPU Support Matrix

| Subsystem | AMD (Tested) | NVIDIA (Supported) | Intel (Basic) |
|-----------|-------------|-------------------|---------------|
| Hyprland compositor | mesa + vulkan-radeon | nvidia + nvidia-utils | mesa + vulkan-intel |
| Ollama LLM inference | ROCm HIP SDK | CUDA toolkit | CPU-only (slow) |
| Whisper STT | Vulkan (whisper.cpp) | CUDA (whisper.cpp) | CPU fallback (~5x slower) |
| VRAM Manager | sysfs (`mem_info_vram_*`) | nvidia-smi | Not applicable |
| GPU monitoring (shell bar) | amdgpu hwmon | nvidia-smi polling | Not applicable |
| DeepFilterNet (noise) | CPU (LADSPA plugin) | CPU (LADSPA plugin) | CPU (LADSPA plugin) |

### Tested Hardware
- **AMD RX 9060 XT 16GB** (RDNA 4) — full support, all features verified
- ROCm HIP SDK for Ollama, Vulkan for Whisper

### NVIDIA Notes
- Install `nvidia`, `nvidia-utils`, `lib32-nvidia-utils` (done by first-boot.sh)
- Ollama uses CUDA automatically when nvidia drivers present
- Whisper.cpp can be built with CUDA backend
- VRAM manager reads `nvidia-smi` for memory stats

### Intel Notes
- Integrated GPUs: compositor works, but no local LLM acceleration
- AI tier automatically set to CLOUD_ONLY
- All AI queries route to Claude API

## CPU Compatibility
- **Architecture**: x86_64 only
- **AMD**: Full support (k10temp/zenpower for monitoring)
- **Intel**: Full support (coretemp for monitoring)
- **ARM**: Not supported (Arch Linux ARM is a different distribution)

## Monitor Support
- **Any number of monitors** supported via Hyprland
- Auto-detection on first boot + AGS shell template generation
- Tested: 1-monitor, 2-monitor, 3-monitor + headless configurations
- Portrait rotation supported (transform in hyprland.conf)
- Virtual headless monitors for AI navigation

### Shell Bar Assignment
| Monitors | Primary | 1st Secondary | Additional | Headless |
|----------|---------|---------------|------------|----------|
| 1 | Main bar (all workspaces) | — | — | — |
| 2 | Main bar (WS 1-4) | Performance bar (WS 5-6) + taskbar | — | — |
| 3+ | Main bar (WS 1-4) | Performance bar (WS 5) + taskbar | Minimal bar (WS 6+) | Claude screen bar |

## Audio Hardware
- **PipeWire** handles all audio routing (ALSA, PulseAudio, JACK compat)
- **Tested**: Blue Snowball (mic), AudioBox USB 96 (DAC/interface)
- **Voice assistant** requires: any working microphone + PipeWire
- Low-latency config: 48kHz sample rate, quantum 256

## Laptop Support
- **Touchpad**: natural scroll, tap-to-click, disable-while-typing
- **Gestures**: 3-finger workspace swipe
- **Lid close**: auto-suspend
- **Battery**: Shell bar battery module (auto-detected)
- **Brightness**: `brightnessctl` keybinds (XF86MonBrightness keys)
- **Power management**: `power-profiles-daemon` (auto-enabled on laptops)
- **IR Camera (Face Auth)**: Auto-detected via `v4l2-ctl`. Enables howdy for face unlock at login, sudo, and screen lock. Enrollment via `sudo howdy add` or Settings → Security
- **Touchscreen**: Auto-detected via `libinput`. Enables touch input, squeekboard (on-screen keyboard), and hyprgrass (multi-touch gestures). Config at `~/.config/hypr/touch.conf`

## Wallpaper Engine (Optional)
- **Package**: `linux-wallpaperengine-git` (AUR)
- **Requires**: Steam with Wallpaper Engine purchased
- **Compatibility**:
  - Video wallpapers: Full support
  - 2D scene wallpapers: Full support
  - 3D scene wallpapers: Limited — complex scenes may crash or render incorrectly
  - Web wallpapers: Not supported
- **Known issues**: Some complex scenes cause GPU hangs on RDNA 4 (RX 9060 XT). Use video or 2D scenes for reliability.
- **Alternative**: mpvpaper for video wallpapers (ships by default, no Steam needed)

## Storage
- **Filesystem**: ext4, btrfs, ntfs-3g (read/write) supported
- **Boot**: UEFI only (no legacy BIOS)
- **Installer**: Works with NVMe, SATA, USB drives
- Note: NVMe device names may swap between boots — system uses UUIDs

## Network
- **NetworkManager** for WiFi/Ethernet
- **iwd** backend for WiFi
- Required for: Claude API, package updates, weather widget, news queries
- Local-first AI works offline (Ollama, Whisper, costa-nav)
