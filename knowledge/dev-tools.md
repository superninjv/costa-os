---
l0: "Development tools: pyenv, nvm, SDKMAN, Rust, Docker, git, zellij, Firecrawl, CLI utilities"
l1_sections: ["Language Managers", "Containers", "Git", "Terminal Multiplexer", "Web Scraping", "Useful CLI Tools"]
tags: [python, pyenv, node, nvm, rust, cargo, java, sdk, docker, git, lazygit, zellij, kubectl, k9s, firecrawl, scraping]
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

## Web Scraping (Firecrawl)
Self-hosted web scraping API — converts any web page to clean markdown/structured data.

### Setup & Management
```bash
costa-firecrawl setup     # clone repo + build Docker images (first time, ~5 min)
costa-firecrawl start     # start all services (API + Playwright + Redis + RabbitMQ + Postgres)
costa-firecrawl stop      # stop all services
costa-firecrawl status    # container status + API health
costa-firecrawl update    # pull latest + rebuild
costa-firecrawl scrape URL  # quick test scrape (returns markdown)
```

### How It Works
- Firecrawl runs locally via Docker Compose at `http://localhost:3002`
- Uses Playwright (headless Chromium) for JavaScript rendering
- AI extraction features use local Ollama (qwen3.5:4b) — no cloud API needed
- Port 3002 bound to localhost only (firewall allows local access)
- Data dir: `~/.local/share/costa/firecrawl/`

### Claude Code Integration
When Firecrawl is set up, `setup-claude-code.sh` registers the `firecrawl-mcp` MCP server automatically. Claude Code gets scrape/crawl/map/extract tools.

### Python SDK
```python
from firecrawl import Firecrawl
app = Firecrawl(api_url="http://localhost:3002")
result = app.scrape("https://example.com")
print(result["markdown"])
```

### Node.js SDK
```javascript
import Firecrawl from '@mendable/firecrawl-js';
const app = new Firecrawl({ apiUrl: "http://localhost:3002" });
const result = await app.scrape("https://example.com");
```

### Resource Usage
- ~14GB RAM when running (API 8GB + Playwright 4GB + supporting services)
- Not auto-started — use `costa-firecrawl start` when needed
- Stop when done to reclaim memory: `costa-firecrawl stop`

## Code Intelligence (costa-ast)
- System-wide tree-sitter daemon: `org.costa.AST` on D-Bus session bus
- Auto-watches `~/projects/` — incremental AST parsing on file changes
- 30+ languages: Python, TypeScript, Rust, Go, C/C++, Java, Bash, JSON, YAML...
- MCP tools: `ast_symbols`, `ast_scope`, `ast_complexity`, `ast_dependents`, `ast_file_summary`
- AGS widget client: `shell/widget/ast/ASTService.ts` (reactive state via bus watching)
