---
l0: "AI query routing: local Ollama models, Claude API escalation, VRAM management, CLI usage, tool use, workflows, RAG, ML routing, SQLite persistence"
l1_sections: ["Query Flow", "CLI Usage", "Routing Patterns", "Context Injection", "VRAM Management", "Knowledge System", "System Prompts", "Report to Claude (Feedback Loop)", "Claude Tool Use", "Workflow Engine", "ML Router", "Document RAG", "Request Queue", "SQLite Persistence", "Cancel Mechanism", "Customization"]
tags: [ai, router, ollama, claude, vram, model-selection, escalation, context-injection, query, tools, workflow, rag, ml, sqlite, budget, queue]
---
# Costa AI Router — How It Works

The AI router is the intelligence layer that connects user intent to system execution.

## Query Flow
1. User asks a question (voice, CLI, or rofi)
2. Router classifies the query (window management? file search? general knowledge?)
3. Gathers relevant system context (running processes, GPU state, packages, etc.)
4. Selects the best model based on query type and available VRAM
5. Queries the model with injected system context
6. If local model can't answer, auto-escalates to Claude API
7. If the response contains a safe command, auto-executes it

## CLI Usage
```bash
costa-ai "what's using my GPU"              # local model with GPU context
costa-ai "write me a Python HTTP server"     # routes to Claude Sonnet
costa-ai --json "is docker running"          # JSON output with metadata
costa-ai --no-escalate "quick question"      # stay local, don't use cloud
costa-ai --model opus "architecture review"  # force specific model
costa-ai --history                           # browse past queries and responses
costa-ai --search "docker"                   # full-text search query history
costa-ai --usage                             # usage stats by model, time, cost
costa-ai --budget 5.00                       # set daily spending limit
costa-ai --stop                              # cancel running query (SIGTERM via /tmp/costa-ai.pid)
costa-ai --train-router                      # retrain ML classifier from usage data
costa-ai --index ~/projects/docs             # index directory for RAG search
costa-ai --preset code                       # routing preset (code/research/fast)
```

## Routing Patterns
- **Window management**: "move firefox to workspace 2", "tile editor and terminal side by side"
- **File search**: "find the AGS config", "where's the router script"
- **Project switch**: "switch to my-app", "open the website project"
- **Local model**: general questions, system queries, package info
- **Claude Haiku + web**: news, scores, trending, real-time data
- **Claude Sonnet**: code generation, debugging, implementation
- **Claude Opus**: architecture, research, security audit

## Context Injection
The router automatically gathers relevant system data based on the query:
- Package questions → runs pacman -Q queries
- Service questions → checks systemctl status
- GPU questions → reads sysfs GPU stats
- Audio questions → runs wpctl status
- Network questions → checks ip/nmcli
- Docker questions → lists containers

## VRAM Management
The ollama-manager daemon automatically loads the best model for available GPU memory (LLM-judge quality scores):
- 10GB+ free → qwen3.5:9b (quality 0.606, best for architecture/code_debug/code_test)
- 6GB+ free → qwen3.5:9b or qwen3.5:4b (quality 0.581, wins 5/6 categories vs 9b at 512-token budgets)
- 4GB+ free → qwen3.5:4b (best speed/quality ratio at 28 t/s)
- 2GB+ free → qwen3.5:2b (speed-only, 53 t/s, unreliable for general use)
- <2GB free → cloud only (gaming mode)

Category-aware routing can swap models per query type: qwen3:14b for code_write/general_knowledge, qwen3.5:9b for architecture/debugging.

## Knowledge System
Knowledge files in `~/.config/costa/knowledge/` are auto-discovered and loaded based on query relevance.
Each file has YAML frontmatter with:
- `l0` — one-line summary (used for quick matching and low-tier models)
- `l1_sections` — list of H2 sections (loaded selectively for medium-tier models)
- `tags` — semantic keywords for matching beyond regex patterns

Knowledge loading is tiered by model size:
- **0.8B-1B models**: top 1 at L1, rest at L0. ~400 token budget.
- **2B-3B models**: top 2 matched files at L1 (section summaries), rest at L0. ~800 token budget.
- **4B models**: top 2 at L1, rest at L0. ~1,200 token budget.
- **7B models**: top 3 at L1, rest at L0. ~1,500 token budget.
- **9B models**: top 3 at L1 + top 1 full content, rest at L0. ~2,000 token budget.
- **14B models**: top 3 at L1 + top 1 full content, rest at L0. ~3,000 token budget.

Prompts use XML delimiters (`<context>`, `<knowledge>`, `<query>`) for clear section boundaries.
Query goes last in the prompt (highest attention position for Qwen models).

## System Prompts
Tiered system prompts in `~/.config/costa/system-prompts/`:
- `system-ai-3b.md` — ~20 lines, identity + core rules + 2 examples
- `system-ai-7b.md` — ~40 lines, + hardware + keybinds + 3 examples
- `system-ai-14b.md` — ~80 lines, full prompt + Costa features + 5 examples

## Report to Claude (Feedback Loop)
When the local model gives a wrong answer, click the 󰚑 icon in the shell bar to report it.
This sends the query + response to Claude Haiku, which:
1. Identifies the correct answer
2. Generates a patch for the relevant knowledge file
3. Applies the patch to `~/.config/costa/knowledge/`
4. Shows corrected answer via notification
Corrections are logged in `~/.config/costa/knowledge/.corrections.json`.
Review with: `costa-ai-report corrections`

## Claude Tool Use
When queries escalate to Claude, the router provides 30+ structured tools via the Anthropic tool_use API:
- **System queries** — read processes, services, packages, disk, network, GPU, audio state
- **Safe actions** — adjust volume, switch workspace, control media, toggle settings
- **Ask-first actions** — install packages, restart services, modify configs (requires confirmation)
Tool definitions are in `ai-router/tools.py`.

## Workflow Engine (costa-flow)
YAML workflow automation in `~/.config/costa/workflows/`:
- `costa-flow run <name>` — execute a workflow
- `costa-flow list` — list available workflows
- `costa-flow enable <name>` — activate on systemd timer schedule
- 10 built-in templates: morning-briefing, system-health, backup-check, smart-update, docker-watch, log-digest, project-standup, security-scan, cleanup, ollama-model-update
- Workflows support steps, conditions, schedules, and AI-powered decision nodes
- Engine code: `ai-router/workflow.py`

## ML Router
PyTorch MLP classifier for smart query routing, trained from logged usage data:
- `costa-ai --train-router` — retrain from SQLite query history
- Classifies queries into local/cloud/code/research tiers
- Falls back to regex patterns if untrained or low confidence
- Model code: `ai-router/ml_router.py`

## Document RAG
FTS5-based retrieval-augmented generation for user documents:
- `costa-ai --index <dir>` — index a directory (recursively)
- Indexed content is injected as context when relevant to queries
- Uses SQLite FTS5 full-text search with relevance ranking
- Code: `ai-router/rag.py`

## Request Queue
Unix socket priority queue daemon for concurrent request handling:
- Voice queries get highest priority
- Background workflows queue behind interactive queries
- Prevents model contention from simultaneous sources
- Code: `ai-router/queue.py`

## SQLite Persistence
All queries are logged to `~/.config/costa/costa.db`:
- Query text, model used, latency, token counts, cost estimates
- `costa-ai --history` — browse past queries
- `costa-ai --search "term"` — full-text search history
- `costa-ai --usage` — usage analytics
- `costa-ai --budget <amount>` — spending limits with automatic cloud blocking
- Code: `ai-router/db.py`

## Cancel Mechanism
Long-running queries can be stopped:
- `costa-ai --stop` — sends SIGTERM via PID file at `/tmp/costa-ai.pid`
- Shell bar costa-ai widget has a stop button during processing
- Clean teardown of model inference and API calls

## Customization
- Add knowledge: create .md files in ~/.config/costa/knowledge/ (auto-discovered, no code changes needed)
- Change system prompt: edit files in ~/.config/costa/system-prompts/
- Add routing patterns: edit ai-router/router.py ROUTE_PATTERNS
- Change safe commands list: edit router.py SAFE_COMMAND_PATTERNS
- Add workflows: create YAML files in ~/.config/costa/workflows/
- Index documents: `costa-ai --index <dir>` for RAG search
- Train router: `costa-ai --train-router` after accumulating usage data
