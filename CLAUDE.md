# Costa OS

AI-native Linux distribution built on Arch Linux + Hyprland. The AI is the OS interface.

## Build & Test
```bash
# Build ISO (requires archiso)
sudo ./scripts/build-iso.sh

# Test in VM
./scripts/test-vm.sh

# Run installer wizard standalone (for development)
python3 installer/wizard.py
```

## Project Structure
- `installer/` — First-run setup wizard (Python/GTK4)
- `packages/` — Package lists by category (base, dev, creative, gaming)
- `configs/` — Default config templates (Costa theme applied)
- `voice-assistant/` — PTT voice assistant source (future: standalone app)
- `scripts/` — ISO build scripts, CI/CD
- `branding/` — Logo, wallpapers, boot splash
- `docs/` — User guide, architecture docs

## Architecture
- Base: Arch Linux (archiso)
- Compositor: Hyprland
- Theme: Costa (Mediterranean coastal palette)
- AI Layer: Whisper STT + Ollama (local) + Claude API (cloud) + smart routing
- Package manager: pacman + yay (AUR)
