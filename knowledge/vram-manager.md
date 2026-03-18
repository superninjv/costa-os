---
l0: "VRAM manager: automatic Ollama model selection based on available GPU memory"
l1_sections: ["What It Does", "Model Tiers", "Checking Current State", "How It Decides", "Gaming Mode", "Manual Override", "Configuration"]
tags: [vram, gpu, ollama, model, memory, gaming, manager]
---
# Costa OS VRAM Manager

## What It Does

Automatically picks the best Ollama model that fits in available GPU memory. Runs as a background daemon — you never need to think about model loading.

## Model Tiers

| Tier | Model | VRAM Needed | When |
|------|-------|-------------|------|
| Full | qwen2.5:14b | ~11GB | Plenty of VRAM free |
| Medium | qwen2.5:7b | ~6.5GB | Moderate VRAM pressure |
| Reduced | qwen2.5:3b | ~4GB | Heavy VRAM usage |
| Gaming | (none loaded) | 0GB | GPU needed for games |

## Checking Current State

```sh
cat /tmp/ollama-smart-model    # currently loaded model name
cat /tmp/ollama-tier           # current tier (full/medium/reduced/gaming)
ollama ps                      # show all loaded models and VRAM usage
```

## How It Decides

1. Checks total GPU VRAM (e.g., 8GB, 12GB, 16GB depending on your GPU)
2. Subtracts VRAM used by other apps (games, browsers, etc.)
3. Subtracts 2GB headroom buffer (prevents thrashing)
4. Picks the largest model that fits in remaining space

The daemon re-checks periodically and when VRAM usage changes significantly.

## Gaming Mode

When a game launches and claims VRAM:
- Models auto-unload to free GPU memory
- Tier drops to "gaming" (no local models)
- All AI queries automatically route to cloud (Claude Haiku/Sonnet)
- When the game exits, the best-fit model reloads

No manual intervention needed.

## Manual Override

Temporarily load a specific model (overridden on next daemon cycle):
```sh
ollama run qwen2.5:14b     # force load 14B
ollama stop qwen2.5:14b    # unload a model
```

## Configuration

The manager script:
```
~/.config/hypr/ollama-manager.sh
```

PTT reads the current model from `/tmp/ollama-smart-model` on every query, so it always uses whatever the manager selected.
