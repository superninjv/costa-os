#!/bin/bash
# Claude Code usage monitor for waybar
# Parses local session JSONL files for today's token usage

CACHE="/tmp/waybar-claude-usage"
CACHE_AGE=120  # seconds

# Use cache if fresh enough
if [ -f "$CACHE" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$CACHE") ))
  if [ "$age" -lt "$CACHE_AGE" ]; then
    cat "$CACHE"
    exit 0
  fi
fi

(
/usr/bin/python3 << 'PYEOF'
import json, os, glob
from datetime import datetime, date

claude_dir = os.path.expanduser("~/.claude/projects")
today_str = date.today().isoformat()

totals = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "sessions": 0, "messages": 0}
model_breakdown = {}

for jsonl in glob.glob(os.path.join(claude_dir, "**", "*.jsonl"), recursive=True):
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(jsonl)).date()
        if mtime != date.today():
            continue
    except:
        continue

    session_had_today = False
    try:
        with open(jsonl) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except:
                    continue
                if d.get("type") != "assistant":
                    continue
                msg = d.get("message", {})
                usage = msg.get("usage")
                if not usage:
                    continue

                ts = d.get("timestamp", "")
                if ts and not ts.startswith(today_str):
                    continue

                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cw = usage.get("cache_creation_input_tokens", 0)
                cr = usage.get("cache_read_input_tokens", 0)

                totals["input"] += inp
                totals["output"] += out
                totals["cache_write"] += cw
                totals["cache_read"] += cr
                totals["messages"] += 1

                model = msg.get("model", "unknown")
                short = "opus" if "opus" in model.lower() else "haiku" if "haiku" in model.lower() else "sonnet"
                if short not in model_breakdown:
                    model_breakdown[short] = {"input": 0, "output": 0, "cache": 0, "msgs": 0}
                model_breakdown[short]["input"] += inp
                model_breakdown[short]["output"] += out
                model_breakdown[short]["cache"] += cw + cr
                model_breakdown[short]["msgs"] += 1

                session_had_today = True
    except:
        continue

    if session_had_today:
        totals["sessions"] += 1

def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)

total_tokens = totals["input"] + totals["output"] + totals["cache_write"] + totals["cache_read"]
# For display, show output tokens (what Claude actually generated)
out_tokens = totals["output"]

if total_tokens == 0:
    text = "󰚩 —"
    css_class = "idle"
else:
    text = f"󰚩 {fmt(out_tokens)} out"
    if out_tokens < 50_000:
        css_class = "low"
    elif out_tokens < 200_000:
        css_class = "medium"
    else:
        css_class = "high"

lines = [f"Claude Usage Today"]
lines.append(f"")
lines.append(f"Output: {fmt(out_tokens)}  Input: {fmt(totals['input'])}")
lines.append(f"Cache write: {fmt(totals['cache_write'])}  Cache read: {fmt(totals['cache_read'])}")
lines.append(f"Total: {fmt(total_tokens)}")
lines.append(f"Messages: {totals['messages']}  Sessions: {totals['sessions']}")

if model_breakdown:
    lines.append("")
    for m in sorted(model_breakdown, key=lambda k: model_breakdown[k]["output"], reverse=True):
        b = model_breakdown[m]
        lines.append(f"  {m}: {fmt(b['output'])} out, {fmt(b['input'])} in, {fmt(b['cache'])} cache ({b['msgs']} msgs)")

tooltip = "\\n".join(lines)
print(json.dumps({"text": text, "tooltip": tooltip, "class": css_class}))
PYEOF
) | tee "$CACHE"
