---
l0: "AI navigation system: AT-SPI accessibility tree reading, query/plan/routine levels, headless monitor"
l1_sections: ["Architecture", "Query Best Practices", "Plan Patterns", "Dedicated Monitor & Focus Protection", "Common Pitfalls", "Failure Handling", "Site Knowledge", "Routines"]
tags: [navigation, at-spi, accessibility, screen-read, headless, virtual-monitor, plan, routine, ollama]
---

# costa-nav — AI Navigation Tool Knowledge

How to use costa-nav effectively for screen reading and interaction.
This file is read by Claude before building navigation plans.
Update it when you discover new patterns or anti-patterns.

## Architecture

costa-nav has 4 levels:
- **Level 0** `read <app>` — raw AT-SPI accessibility dump, no Ollama, for debugging
- **Level 1** `query '{json}'` — batch questions answered by local Ollama
- **Level 2** `plan '{json}'` — conditional plan with actions, executed locally
- **Level 3** `routine <name>` — saved plans triggered by name

## Query Best Practices

### Keep content under 6K chars
Ollama's accuracy drops sharply above 6K chars of screen content. Always set `max_text: 4000-6000` and target a specific `page` when querying Firefox.

### Ask specific questions, not broad ones
Bad: `"find": "describe everything on the page"`
Good: `"find": "credit balance amount as shown in sidebar"`

### Use page targeting for Firefox
Firefox reads ALL tabs by default. Always include `"page": "partial-tab-name"` to focus on one.

### Batch related queries together
One Ollama call with 6 queries is faster than 6 separate calls. Group everything you need from one screen read.

## Plan Patterns

### Read → Decide → Act → Verify
The most common pattern. Read the screen, check a condition, perform an action, then read again to verify.
```json
{"steps": [
  {"type": "query", "id": "state", "find": "current page state"},
  {"type": "condition", "check": "user is logged in",
    "then": [{"type": "query", "id": "data", "find": "the target data"}],
    "else": [{"type": "query", "id": "err", "find": "describe the login page or error"}]
  }
]}
```

### Fallback chains
When an element might not be where expected:
```json
{"type": "fallback",
  "try": [{"type": "query", "id": "x", "find": "credit balance in sidebar"}],
  "catch": [
    {"type": "action", "action": "scroll", "target": "firefox", "direction": "down", "amount": 3},
    {"type": "wait", "ms": 300},
    {"type": "query", "id": "x", "find": "credit balance anywhere on page"}
  ]
}
```

### Scroll-and-collect loops
For gathering lists that may extend beyond the viewport:
```json
{"type": "loop", "id": "items", "find": "list item text",
  "scroll": "down", "max_iterations": 5, "until": "no new items found"}
```

### Cross-app sequences
Switch workspaces between reads:
```json
{"steps": [
  {"type": "action", "action": "workspace", "workspace": "5"},
  {"type": "wait", "ms": 200},
  {"type": "query", "id": "browser_state", "find": "..."},
  {"type": "action", "action": "workspace", "workspace": "1"},
  {"type": "query", "id": "terminal_state", "find": "..."}
]}
```

## Dedicated Monitor & Focus Protection

Claude has a dedicated **virtual headless monitor** (HEADLESS-2, workspace 7, 1920x1080).
This is invisible — it takes zero physical screen space. Created at boot via `hyprctl output create headless`.

The user can see what's on the headless monitor by clicking the 󰍹 icon in waybar, which toggles a live preview window (auto-refreshes every 2s via `grim -o HEADLESS-X`).

### Rules
- **NEVER** click, type, or send keys to windows on the user's active workspace
- AT-SPI reads are always safe — they don't require focus or affect the user
- When you need to interact with a window, use Claude's workspace
- Focus-stealing actions on user's workspace return an error with guidance

### Claude's Browser
Claude has its own Firefox instance with a separate profile (`firefox-claude` class).

Actions:
- `{"action": "open_browser", "url": "https://example.com"}` — opens Firefox on Claude's monitor
- `{"action": "navigate", "url": "https://..."}` — navigates Claude's existing browser
- `{"action": "close_browser"}` — closes Claude's browser

### Reading vs Acting
- **Read user's browser**: use AT-SPI queries (safe, no focus change, reads any tab)
- **Need to browse yourself**: open_browser on Claude's monitor, then interact freely
- **Need to interact with user's app**: ask the user, or read-only via AT-SPI

### Example: Check a URL the user has open, then research something yourself
```json
{"steps": [
  {"type": "query", "id": "user_page", "find": "content of the current page in user's Firefox"},
  {"type": "action", "action": "open_browser", "url": "https://docs.example.com/api"},
  {"type": "wait", "ms": 2000},
  {"type": "query", "id": "docs", "find": "API documentation content", "app": "firefox-claude"}
]}
```

## Common Pitfalls

### SPA loading delays
Single-page apps (React, Vue) update the DOM after navigation. The AT-SPI tree may be stale for 300-1000ms after a click. Always include a wait step:
```json
{"type": "action", "action": "click", ...},
{"type": "wait", "ms": 800},
{"type": "query", ...}
```

### AT-SPI text split across children
Some apps split visible text across multiple section/paragraph nodes. If Ollama returns null for text you know is there, try a broader query: "any mention of X" rather than "the X element's text".

### Nested modals and dialogs
When a dialog opens, the page content is still in the AT-SPI tree behind it. The dialog content appears as new nodes. Query specifically for "dialog" or "modal" after clicking a button that opens one.

### Firefox tab content ordering
AT-SPI returns tab content in DOM order, not visual order. The "first" page in the data may not be the active tab. Use page targeting to be explicit.

### Ollama temperature
costa-nav uses temperature 0.1 by default. This keeps answers consistent. Don't change it unless you need creative interpretation (you almost never do for navigation).

### Max nesting depth
Conditional plans nest up to 5 levels deep. If you need deeper nesting, flatten into sequential steps with early-exit conditions instead. The 14b model handles flat sequences better than deep branching.

## Failure Handling

When Ollama returns `null` or `"confidence": "low"`:
1. Check if the page is still loading (add a wait, re-read)
2. Try a broader search term
3. Check site knowledge for known element locations
4. Only fall back to screenshot as last resort — it costs 10-50x more tokens

When an action fails (click, type):
1. The window may have lost focus — try focusing first
2. Coordinates may have shifted — re-read and recalculate
3. XWayland apps need xdotool, Wayland-native apps need wtype

## Site Knowledge

costa-nav auto-learns site-specific patterns during plan execution:
- Element locations that differ from expectations
- Fallback paths that were triggered
- Assertion failures and what was actually found

These are stored in `~/.config/costa/nav-sites/<domain>.md` and loaded automatically on future queries to the same site.

Claude can also manually add knowledge:
```bash
costa-nav learn firefox "Vast.ai credit balance is in a [section] element in the left sidebar"
costa-nav learn firefox "Gmail inbox loads lazily, retry after 1s if content is empty"
```

## Routines

Save proven plans as routines for one-word triggers:
```bash
costa-nav routine-save vast-status '{"app":"firefox","page":"vast","steps":[...]}' "Check Vast.ai balance and instances"
costa-nav routine vast-status
```

Routines track run count and last run time. Use `routine-list` to see all available.
