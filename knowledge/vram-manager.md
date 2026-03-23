---
l0: "VRAM manager: automatic Ollama model selection based on available GPU memory"
l1_sections: ["What It Does", "Model Tiers", "GPU Backend", "Checking Current State", "How It Decides", "Gaming Mode", "Manual Override", "Configuration"]
tags: [vram, gpu, ollama, model, memory, gaming, manager, vulkan]
---
# Costa OS VRAM Manager

## What It Does

Automatically picks the best Ollama model that fits in available GPU memory. Runs as a background daemon — you never need to think about model loading.

## Model Tiers

Quality scores from LLM-judge evaluation (Claude Haiku, 80+ prompts):

| Tier | Model | VRAM | Speed | Quality | When |
|------|-------|------|-------|---------|------|
| Full | qwen3.5:9b | ~8GB | 23 t/s | 0.606 | Default for 16GB GPUs |
| Value | qwen3.5:4b | ~5GB | 28 t/s | 0.581 | Best speed/quality ratio — wins 5/6 categories vs 9b at 512-token budgets |
| Speed | qwen3.5:2b | ~3GB | 53 t/s | 0.375 | Classification/routing only — unreliable for general answers |
| Gaming | (none loaded) | 0GB | — | — | GPU needed for games |

The 4B model outperforms 9B on most categories at short response budgets (512 tokens) because it produces more complete answers before hitting the token limit. Reserve 9B for extended reasoning tasks (1024+ tokens).

Note: qwen3.5:0.8b (0.231 quality) is not loaded as a default — it hallucinates too frequently.

## GPU Backend

Ollama uses **Vulkan** (mesa RADV) on AMD GPUs. ROCm/HIP has a known bug on RDNA4 (gfx1200) that pegs the GPU at 100% idle and never releases — even after unloading models. Vulkan avoids this entirely while delivering comparable performance.

The Vulkan backend is configured via systemd override:
```
/etc/systemd/system/ollama.service.d/vulkan.conf
```

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
