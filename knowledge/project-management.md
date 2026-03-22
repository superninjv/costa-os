---
l0: "Project management: switch projects, configure workspaces, auto-launch apps, project configs"
l1_sections: ["Switching Projects", "Project Config Format", "Creating a Project Config", "Shell Bar Project Switcher", "Fuzzy Matching"]
tags: [project, workspace, switch, config, management, apps, layout, shell-bar]
---
# Costa OS Project Management

## Switching Projects

Switch to a project context (opens workspace, launches apps, sets env):

```sh
costa-ai "switch to myproject"
```

Or by voice: hold `SUPER+ALT+V` and say "switch to myproject"

## Project Config Format

Project configs live in `~/.config/costa/projects/<name>.yaml`:

```yaml
name: my-webapp
directory: ~/projects/my-webapp
workspace: 2

apps:
  - command: code ~/projects/my-webapp
    position: left      # optional: left, right, top, bottom, center
  - command: ghostty -e "cd ~/projects/my-webapp && zsh"
    position: right
  - command: firefox --new-window "http://localhost:3000"
    position: floating

env:
  DATABASE_URL: "postgresql://localhost/myapp"
  NODE_ENV: "development"

setup:
  - docker compose up -d
  - npm run dev &disown
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Display name |
| `directory` | yes | Project root directory |
| `workspace` | no | Workspace number to switch to (1-6) |
| `apps` | no | Apps to launch with optional positions |
| `env` | no | Environment variables to set |
| `setup` | no | Shell commands to run on switch |

## Creating a Project Config

```sh
# Create manually
$EDITOR ~/.config/costa/projects/myproject.yaml

# Or ask the AI to create one
costa-ai "create a project config for ~/projects/myapp with VS Code and a terminal"
```

## Shell Bar Project Switcher

- **Left-click** the folder icon in the shell bar → opens project list
- **Scroll** on the folder icon → cycle through recent projects
- Active project name shows in the shell bar

## Fuzzy Matching

Project switching uses fuzzy matching on the project name:

```sh
costa-ai "switch to web"       # matches "my-webapp"
costa-ai "switch to api"       # matches "api-server"
costa-ai "switch to front"     # matches "frontend"
```
