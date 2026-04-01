---
l0: "VRAM manager: automatic Ollama model selection based on available GPU memory"
l1_sections: ["What It Does", "Model Tiers", "GPU Backend", "Checking Current State", "How It Decides", "Gaming Mode", "Manual Override", "Configuration"]
tags: [vram, gpu, ollama, model, memory, gaming, manager, vulkan]
---
# Costa OS VRAM Manager

## What It Does

Automatically picks the best Ollama model that fits in available GPU memory. Runs as a background daemon — you never need to think about model loading.

## Model Tiers

Quality scores from LLM-judge evaluation (Claude Haiku, 80 prompts, num_predict=2048, num_ctx=8192):

| Tier | Model | VRAM | Speed | Quality | When |
|------|-------|------|-------|---------|------|
| Full | qwen3:14b | ~9.7GB | 24 t/s | 0.594 | When 14b fits in VRAM budget |
| Default | qwen3.5:9b | ~6.5GB | 22 t/s | 0.571 | Default for 16GB GPUs |
| Reduced | qwen3.5:4b | ~3GB | 18 t/s | 0.525 | When VRAM is tight |
| Gaming | (none loaded) | 0GB | — | — | GPU needed for games |

At 2048-token budgets, 14B leads across most categories (especially code and reasoning). The 9B model is the best default: 96% of 14B quality at 60% of the VRAM. The 4B model dropped from its previous apparent parity with 9B (0.581 vs 0.606 at 512 tokens) to a clearer gap (0.525 vs 0.571) once models had room to generate complete answers.

Note: qwen3.5:0.8b (0.236 quality) and qwen3.5:2b (0.372) are not loaded as defaults — too unreliable for general answers.

## GPU Backend

Ollama uses **Vulkan** (mesa RADV) on AMD GPUs. ROCm/HIP has a known bug on RDNA4 (gfx1200) that pegs the GPU at 100% idle and never releases — even after unloading models. Vulkan avoids this entirely while delivering comparable performance.

The Vulkan backend is configured via systemd override:
```
/etc/systemd/system/ollama.service.d/vulkan.conf
```

## Checking Current State

```sh
cat ${XDG_RUNTIME_DIR}/costa/ollama-smart-model  # currently loaded model name
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
ollama run qwen3:14b       # force load 14B
ollama stop qwen3:14b      # unload a model
```

## Configuration

The manager script:
```
~/.config/hypr/ollama-manager.sh
```

PTT reads the current model from `$XDG_RUNTIME_DIR/costa/ollama-smart-model` on every query, so it always uses whatever the manager selected.
