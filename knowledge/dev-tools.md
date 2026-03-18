---
l0: "Development tools: pyenv, nvm, SDKMAN, Rust, Docker, git, zellij, CLI utilities"
l1_sections: ["Language Managers", "Containers", "Git", "Terminal Multiplexer", "Useful CLI Tools"]
tags: [python, pyenv, node, nvm, rust, cargo, java, sdk, docker, git, lazygit, zellij, kubectl, k9s]
---

# Development Tools Reference

## Language Managers
- Python: `pyenv install 3.x`, `pyenv global 3.x`, `pyenv shell 3.x`
- Node: `nvm install 24`, `nvm use 24`, `nvm alias default 24`
- Java: `sdk install java 21-open`, `sdk use java 21-open`
- Rust: `rustup update`, `rustup default stable`

## Containers
- Docker: `docker compose up -d`, `docker compose down`, `docker ps`
- Lazy docker: `lazydocker` (TUI)
- k8s: `kubectl get pods`, `k9s` (TUI)

## Git
- Status: `lazygit` (TUI) or `git status`
- Delta pager: side-by-side diffs enabled
- SSH key: `~/.ssh/id_ed25519`
- GitHub CLI: `gh pr create`, `gh issue list`

## Terminal Multiplexer
- zellij: `zellij`, new tab: `Ctrl+t`, new pane: `Ctrl+n`

## Useful CLI Tools
- `tokei` — code line counter
- `dust` — disk usage (better du)
- `procs` — process viewer (better ps)
- `bottom`/`btm` — system monitor (better htop)
- `xh` — HTTP requests (better curl for APIs)
- `sd` — find & replace (better sed)
- `dog` — DNS lookup (better dig)
- `bandwhich` — network bandwidth monitor
