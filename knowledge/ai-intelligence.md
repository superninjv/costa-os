---
l0: "AI layer: costa-ai CLI, model routing, auto-escalation, usage tracking, budget management"
l1_sections: ["Asking the AI", "Model Routing", "Auto-Escalation", "Usage & History", "Training the Router", "Reporting Bad Answers", "Budget Management"]
tags: [ai, costa-ai, model, routing, ollama, claude, escalation, budget, usage]
---
# Costa OS AI Intelligence

## Asking the AI

Three ways to interact:

```sh
# CLI
costa-ai "what services are using the most memory"

# Voice (hold key, speak, release)
SUPER+ALT+V    # Claude mode — AI processes and responds
SUPER+ALT+B    # Type mode — transcribes and types into focused window

# Shell bar
# Left-click the Costa icon → text input box
# Right-click → view last response
```

## Model Routing

Queries are automatically routed to the best model:

| Query Type | Model | Latency |
|-----------|-------|---------|
| General knowledge, system help | Local qwen2.5:14b | ~2s |
| Quick classification, summaries | Local qwen2.5:3b | ~0.3s |
| Weather | Local model + wttr.in fetch | ~2s |
| News, scores, trending | Claude Haiku + web search | ~3s |
| Code generation, debugging | Claude Sonnet | ~5s |
| Architecture, research, security | Claude Opus | ~10s |

The router picks the model automatically based on query content. No manual selection needed.

## Auto-Escalation

If the local model responds with uncertainty ("I don't know", "I'm not sure"), Costa automatically re-sends the query to Claude Haiku with web search. You don't need to retry.

## Usage & History

```sh
costa-ai --usage              # show token/cost breakdown by model
costa-ai --history            # show recent queries and responses
costa-ai --search "docker"    # search past queries by keyword
```

## Training the Router

The ML router learns from your usage patterns. Retrain after accumulated feedback:

```sh
costa-ai --train-router
```

This uses your query history and feedback to improve local vs cloud routing accuracy.

## Reporting Bad Answers

If an answer was wrong or routed to the wrong model:

- Click the report button in the shell bar response widget
- Or from CLI:
```sh
costa-ai-report
```

Reports feed into router training data.

## Budget Management

Set monthly spending limits for cloud API calls:

```sh
costa-ai --budget 5.00 month    # $5/month cap
costa-ai --budget 0.50 day      # $0.50/day cap
costa-ai --usage                # check current spend
```

When budget is exhausted, all queries fall back to local models only.

## Code Intelligence (costa-ast)

A system-wide tree-sitter AST daemon runs in the background, giving the AI structural understanding of your code:

- **Automatic project watching** — parses all files in `~/projects/` on startup
- **Incremental parsing** — sub-millisecond updates when files change
- **30+ languages** — Python, TypeScript, JavaScript, Rust, Go, Bash, C/C++, Java, and more

The AI router uses this to:
- **Classify code queries better** — a 5-line helper refactor routes to the fast local model, a 200-line class with 40 dependents routes to Claude
- **Inject structural context** — the local model sees function names, class structure, and complexity scores instead of just raw text
- **Detect complexity** — cyclomatic complexity analysis identifies functions that need refactoring

```sh
# D-Bus interface (for scripts/tools)
busctl --user call org.costa.AST /org/costa/AST org.costa.AST GetSymbols s "/path/to/file.py"
busctl --user call org.costa.AST /org/costa/AST org.costa.AST GetComplexity s "/path/to/file.py"
busctl --user call org.costa.AST /org/costa/AST org.costa.AST GetStatus
```
