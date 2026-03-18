---
l0: "Automated workflows: run multi-step tasks with costa-flow, YAML definitions, scheduling"
l1_sections: ["What Workflows Are", "Running Workflows", "Built-in Workflows", "YAML Format", "Creating a Custom Workflow", "Scheduling"]
tags: [workflows, automation, costa-flow, yaml, cron, tasks, scheduled]
---
# Costa OS Workflows

## What Workflows Are

Workflows are automated multi-step tasks defined in YAML. Each step can run shell commands, ask the AI, or branch on conditions. Steps can depend on each other.

## Running Workflows

```sh
costa-flow list                    # list all available workflows
costa-flow run system-health       # run a workflow by name
costa-flow run morning-briefing    # another example
costa-flow status                  # check running/recent workflows
```

## Built-in Workflows

| Workflow | What It Does |
|----------|-------------|
| `system-health` | Check disk, memory, failed services, journal errors |
| `smart-update` | Update system packages, rebuild AUR, check for issues |
| `backup-check` | Verify chezmoi state, check recent commits, diff dotfiles |
| `cleanup` | Remove orphan packages, old cache, tmp files, docker prune |
| `docker-watch` | Check container health, restart unhealthy, report status |
| `morning-briefing` | Weather, calendar, system status, unread notifications |
| `security-scan` | Check failed logins, open ports, outdated packages, permissions |
| `log-digest` | AI-summarize recent journal errors and warnings |
| `ollama-model-update` | Check for updated Ollama model versions, pull if available |
| `project-standup` | Git status across all projects, uncommitted changes, PR status |

## YAML Format

Workflows live in `~/.config/costa/workflows/`. Example:

```yaml
name: system-health
description: Check overall system health
schedule: "0 9 * * *"    # cron: daily at 9am (optional)

steps:
  - id: disk
    type: shell
    command: df -h / /home | tail -n +2

  - id: memory
    type: shell
    command: free -h | grep Mem

  - id: failed-services
    type: shell
    command: systemctl --failed --no-legend

  - id: analyze
    type: ai
    prompt: "Summarize this system health data and flag anything concerning"
    input_from: [disk, memory, failed-services]

  - id: alert
    type: condition
    if: "{{ analyze.contains('WARNING') or analyze.contains('CRITICAL') }}"
    then:
      type: shell
      command: notify-send "System Health" "{{ analyze.output }}"
```

### Step Types
- **shell** — run a command, capture output
- **ai** — send prompt to costa-ai (can include output from previous steps)
- **condition** — branch based on previous step output

### Dependencies
Use `input_from: [step_id]` to pass output between steps. Steps without dependencies run in parallel.

## Creating a Custom Workflow

```sh
# Create a new workflow file
$EDITOR ~/.config/costa/workflows/my-workflow.yaml

# Test it
costa-flow run my-workflow

# Enable scheduling (if schedule: field is set)
costa-flow enable my-workflow
```

## Scheduling

Workflows with a `schedule:` field use cron syntax:

```yaml
schedule: "0 9 * * *"      # daily at 9am
schedule: "*/30 * * * *"   # every 30 minutes
schedule: "0 */4 * * *"    # every 4 hours
```

Enable/disable scheduled workflows:
```sh
costa-flow enable my-workflow
costa-flow disable my-workflow
costa-flow schedule          # list all scheduled workflows
```
