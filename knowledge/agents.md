---
l0: "AI agents: specialized task runners for sysadmin, architecture, building, deploying, cleanup, and monitoring"
l1_sections: ["What Are Agents", "Available Agents", "How to Use Agents", "Agent Details", "Queue Management", "Creating Custom Agents", "Agent Configuration", "Troubleshooting"]
tags: [agents, ai, sysadmin, architect, builder, deployer, janitor, monitor, automation, task, preset, yaml, ollama, claude]
---

# AI Agents

## What Are Agents
Agents are specialized AI personas with focused system prompts, specific tool access, and model assignments. Instead of a general "ask the AI anything" approach, agents know their domain deeply and have permission to act within it.

## Available Agents

| Agent | Model | Purpose |
|-------|-------|---------|
| **sysadmin** | qwen2.5:14b (local) | System health, packages, services, disk, logs |
| **architect** | Claude Sonnet | Design systems, plan features, review architecture |
| **builder** | Claude Sonnet | Write code, implement features, fix bugs |
| **deployer** | qwen2.5:14b (local) | Docker, CI/CD, server config, deployments |
| **janitor** | qwen2.5:3b (local) | Clean caches, remove orphan packages, free disk |
| **monitor** | qwen2.5:3b (local) | Watch logs, alert on errors, track resource usage |

## How to Use Agents

### How do I run an agent task?
```bash
# Basic usage
costa-agents run sysadmin "check disk usage"
costa-agents run janitor "clean up old docker images"
costa-agents run architect "review the database schema in ~/projects/myapp"

# Or use the costa-ai preset flag
costa-ai --preset sysadmin "why is my CPU usage high"
costa-ai --preset deployer "write a Dockerfile for this Node.js project"
```

### How do I run an agent from voice?
Say the agent name in your voice command:
- "Hey Costa, sysadmin check what's using all my RAM"
- "Hey Costa, architect how should I structure the auth module"
- "Hey Costa, janitor clean up my system"

The voice router detects agent keywords and routes to the correct preset.

### How do I list available agents?
```bash
costa-agents list
```
Shows all agents with their description, assigned model, and status.

## Agent Details

### sysadmin (local, qwen2.5:14b)
System health, troubleshooting, packages, services, disk, logs.
```bash
costa-agents run sysadmin "what services are failing"
costa-agents run sysadmin "why is the network slow"
```

### architect (cloud, Claude Sonnet)
System design, code review, technical planning, architecture decisions.
```bash
costa-agents run architect "review the API design in ~/projects/myapp/src/api"
costa-agents run architect "plan a microservices migration for this monolith"
```

### builder (cloud, Claude Sonnet)
Write code, implement features, fix bugs, run tests.
```bash
costa-agents run builder "add pagination to the users endpoint"
costa-agents run builder "fix the failing test in auth.test.js"
```

### deployer (local, qwen2.5:14b)
Docker, CI/CD, server config, nginx, deployment files.
```bash
costa-agents run deployer "create a docker-compose for postgres + redis"
costa-agents run deployer "set up GitHub Actions for this repo"
```

### janitor (local, qwen2.5:3b)
Clean caches, remove orphan packages, free disk space.
```bash
costa-agents run janitor "clean pacman cache"
costa-agents run janitor "remove unused docker images and volumes"
```

### monitor (local, qwen2.5:3b)
Watch logs, alert on errors, track resource usage.
```bash
costa-agents run monitor "watch journalctl for errors"
costa-agents run monitor "alert me if CPU goes above 90%"
```

## Queue Management

### How does task queuing work?
- **Local agent tasks** (sysadmin, deployer, janitor, monitor): unlimited parallel execution
- **Cloud agent tasks** (architect, builder): serial queue to manage API rate limits and costs
- Queue is per-agent — a builder task won't block a deployer task

### How do I see the task queue?
```bash
costa-agents queue
```
Shows running and queued tasks with estimated completion.

### How do I cancel a queued task?
```bash
costa-agents cancel <task-id>
```

## Creating Custom Agents

### How do I create my own agent?
Create a YAML file in `~/.config/costa/agents/`:

```yaml
# ~/.config/costa/agents/database.yaml
name: database
description: "Database administration and query optimization"
model: qwen2.5:14b
system_prompt: |
  You are a database administrator for PostgreSQL and SQLite.
  You help with query optimization, schema design, migrations,
  and troubleshooting connection issues.
  Always explain your reasoning before suggesting changes.
  Never drop tables or delete data without explicit confirmation.
tools:
  - read_file
  - execute_sql_readonly
  - list_tables
constraints:
  - never_execute_destructive_sql
  - require_confirmation_for_schema_changes
  - max_response_tokens: 2000
```

### What fields are available in agent YAML?
- `name` — unique identifier (used in CLI commands)
- `description` — human-readable summary
- `model` — which model to use (e.g., `qwen2.5:14b`, `claude-sonnet`, `claude-haiku`)
- `system_prompt` — instructions defining the agent's behavior and expertise
- `tools` — list of allowed tool names the agent can use
- `constraints` — safety rails and limits
- `escalate_to` — agent to hand off to if this one can't handle the task

### How do I test my custom agent?
```bash
# Validate the YAML
costa-agents validate ~/.config/costa/agents/database.yaml

# Run a test query
costa-agents run database "list all tables in the main database"
```

## Agent Configuration
- Agent definitions: `~/.config/costa/agents/*.yaml`
- Built-in agents are in `/usr/share/costa/agents/` (don't edit — overwritten on update)
- User agents in `~/.config/costa/agents/` override built-ins with the same name
- Global agent settings: `~/.config/costa/ai-config.yaml` (model defaults, queue limits)

## Troubleshooting

### Agent says "model not available"
The assigned model isn't running. Check:
```bash
ollama list                    # is the model pulled?
ollama ps                      # is it loaded in memory?
cat /tmp/ollama-smart-model    # what model is currently active?
```
For cloud agents, check your API key: `costa-settings` → AI → Claude API.

### Agent is slow
- Local agents: check VRAM usage with `radeontop`. The VRAM manager may have downgraded the model.
- Cloud agents: check internet connection and API status.
- Use `costa-agents run --verbose <agent> "query"` to see timing breakdown.

### Agent has wrong permissions
Edit the agent's `tools` and `constraints` lists in its YAML file. Remove tools it shouldn't access or add constraints to limit actions.
