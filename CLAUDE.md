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
- `ai-router/` — Core intelligence layer (context gathering, model routing, auto-escalation)
- `installer/` — First-run setup wizard (Python/GTK4)
- `packages/` — Package lists by category (base, dev, creative, gaming)
- `configs/` — Default config templates (Costa theme applied)
- `voice-assistant/` — PTT voice assistant source (future: standalone app)
- `scripts/` — ISO build scripts, CI/CD
- `branding/` — Logo, wallpapers, boot splash
- `docs/` — User guide, architecture docs

## AI Router
```bash
# Query from CLI (any input modality feeds into this)
costa-ai "what packages do I have for python"
costa-ai --json "is docker running"   # includes metadata (model used, escalation, timing)

# Skip context gathering or escalation
costa-ai --no-context "what is 2+2"
costa-ai --no-escalate "what GPU do I have"
```
The router: gathers live system context → queries local Ollama → detects "I don't know" → escalates to Claude API.

## Architecture
- Base: Arch Linux (archiso)
- Compositor: Hyprland
- Theme: Costa (Mediterranean coastal palette)
- AI Layer: Whisper STT + Ollama (local) + Claude API (cloud) + smart routing
- Package manager: pacman + yay (AUR)
