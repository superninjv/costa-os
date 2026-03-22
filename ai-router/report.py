"""Report to Claude — feedback loop for correcting local LLM answers.

When the local model gives a bad answer, the user clicks the shell bar "report" button.
This script sends the failed query + response to Claude, which:
1. Identifies what went wrong
2. Generates the correct answer
3. Patches the relevant knowledge file
4. Shows the corrected answer via dunst notification
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime

from knowledge import discover_knowledge, get_matched_files

KNOWLEDGE_DIR = Path.home() / ".config" / "costa" / "knowledge"
CORRECTIONS_LOG = KNOWLEDGE_DIR / ".corrections.json"
CONVERSATION_FILE = Path("/tmp/costa-conversation.json")
LAST_REPORTED_FILE = Path("/tmp/costa-last-reported-query")


def get_last_conversation() -> dict | None:
    """Read the most recent query/response from conversation history."""
    try:
        data = json.loads(CONVERSATION_FILE.read_text())
        if data:
            return data[-1]
    except Exception:
        pass
    return None


def query_claude_for_correction(query: str, response: str, model: str,
                                 matched_files: list[str]) -> dict | None:
    """Ask Claude to diagnose and fix the bad answer.

    Returns dict with: correct_answer, file, section, action, content
    """
    from router import query_claude

    matched_str = ", ".join(matched_files) if matched_files else "none"

    prompt = f"""The local AI model ({model}) gave this answer to a Costa OS user.
The user reported it as incorrect or unhelpful.

Query: {query}
Response: {response}
Knowledge files that were injected: {matched_str}

Costa OS is an AI-native Linux distro on Arch Linux + Hyprland.
Knowledge files are in ~/.config/costa/knowledge/ and contain system reference docs.

Please provide:
1. The correct answer to the user's question (1-3 sentences, no markdown)
2. A JSON patch to fix the knowledge base so the local model answers correctly next time

Return ONLY valid JSON in this format:
{{
  "correct_answer": "The correct answer here",
  "patch": {{
    "file": "filename.md (without path)",
    "section": "H2 section name to add/update (or 'new' for new section)",
    "action": "add|update",
    "content": "The content to add or replace in that section"
  }}
}}

If no knowledge patch is needed (the knowledge is correct but the model misinterpreted it),
set patch to null and explain in correct_answer."""

    result = query_claude(
        prompt,
        model="haiku",
        system="You are a knowledge base maintenance assistant. Return ONLY valid JSON. No explanation outside the JSON.",
        timeout=30,
    )

    if not result:
        return None

    # Parse the JSON from Claude's response
    try:
        # Handle markdown code blocks
        if "```" in result:
            import re
            m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", result, re.DOTALL)
            if m:
                result = m.group(1)
        return json.loads(result)
    except json.JSONDecodeError:
        return {"correct_answer": result, "patch": None}


def apply_patch(patch: dict) -> bool:
    """Apply a knowledge file patch."""
    if not patch:
        return False

    filename = patch.get("file", "")
    section = patch.get("section", "")
    action = patch.get("action", "")
    content = patch.get("content", "")

    if not all([filename, section, content]):
        return False

    filepath = KNOWLEDGE_DIR / filename
    if not filepath.exists():
        return False

    text = filepath.read_text()

    if action == "add" and section == "new":
        # Add new section at the end
        text = text.rstrip() + f"\n\n## {content.split(chr(10))[0]}\n{chr(10).join(content.split(chr(10))[1:])}\n"
        filepath.write_text(text)
        return True

    if action == "add":
        # Add content to existing section
        header = f"## {section}"
        if header in text:
            # Find the end of this section (next ## or EOF)
            idx = text.index(header)
            next_section = text.find("\n## ", idx + len(header))
            if next_section == -1:
                # Last section — append
                text = text.rstrip() + f"\n{content}\n"
            else:
                # Insert before next section
                text = text[:next_section] + f"{content}\n\n" + text[next_section:]
            filepath.write_text(text)
            return True

    if action == "update":
        # Replace section content
        header = f"## {section}"
        if header in text:
            idx = text.index(header)
            next_section = text.find("\n## ", idx + len(header))
            if next_section == -1:
                text = text[:idx] + f"{header}\n{content}\n"
            else:
                text = text[:idx] + f"{header}\n{content}\n" + text[next_section:]
            filepath.write_text(text)
            return True

    return False


def log_correction(query: str, original_response: str, model: str,
                   correction: dict, patch_applied: bool):
    """Log the correction for review."""
    try:
        existing = json.loads(CORRECTIONS_LOG.read_text()) if CORRECTIONS_LOG.exists() else []
    except Exception:
        existing = []

    existing.append({
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "original_response": original_response,
        "model": model,
        "correct_answer": correction.get("correct_answer", ""),
        "patch": correction.get("patch"),
        "patch_applied": patch_applied,
    })

    # Keep last 100 corrections
    existing = existing[-100:]
    CORRECTIONS_LOG.write_text(json.dumps(existing, indent=2))


def notify(title: str, body: str):
    """Show a dunst notification."""
    subprocess.run(["notify-send", "-t", "10000", title, body],
                   capture_output=True, timeout=5)


def report_last_answer():
    """Main entry point — report the last AI answer as incorrect."""
    last = get_last_conversation()
    if not last:
        notify("Costa AI", "No recent conversation to report.")
        return

    query = last.get("q", "")
    response = last.get("a", "")
    model = last.get("m", "unknown")

    if not query:
        notify("Costa AI", "No query found in conversation history.")
        return

    # Spam guard: only allow one report per query
    try:
        if LAST_REPORTED_FILE.exists():
            last_reported = LAST_REPORTED_FILE.read_text().strip()
            if last_reported == query:
                notify("Costa AI", "Already reported this answer.")
                return
    except Exception:
        pass

    # Mark this query as reported
    try:
        LAST_REPORTED_FILE.write_text(query)
    except Exception:
        pass

    notify("Costa AI", "Reporting to Claude for correction...\nThis will help train your local model.")

    # Find which knowledge files were matched
    matched = get_matched_files(query)

    # Ask Claude for correction
    correction = query_claude_for_correction(query, response, model, matched)

    if not correction:
        notify("Costa AI", "Could not get correction from Claude. Check API key.")
        return

    correct_answer = correction.get("correct_answer", "No correction available.")

    # Apply patch if provided
    patch = correction.get("patch")
    patch_applied = False
    if patch:
        patch_applied = apply_patch(patch)

    # Log the correction
    log_correction(query, response, model, correction, patch_applied)

    # Mark the original query's routing as incorrect for ML training
    try:
        from db import find_recent_query, update_routing_feedback
        query_id = find_recent_query(query)
        if query_id:
            update_routing_feedback(query_id, was_correct=False)
    except Exception:
        pass

    # Show corrected answer
    patch_msg = ""
    if patch_applied:
        patch_msg = f"\n\nKnowledge updated: {patch.get('file', '?')}"
    elif patch:
        patch_msg = "\nPatch suggested but could not be applied"

    train_msg = "\nRouting feedback saved — your local model will improve."
    notify("Costa AI — Corrected", f"{correct_answer}{patch_msg}{train_msg}")


def show_corrections():
    """Show recent corrections log."""
    if not CORRECTIONS_LOG.exists():
        print("No corrections logged yet.")
        return

    try:
        corrections = json.loads(CORRECTIONS_LOG.read_text())
    except Exception:
        print("Error reading corrections log.")
        return

    for c in corrections[-10:]:
        ts = c.get("timestamp", "?")[:16]
        q = c.get("query", "?")[:60]
        patched = "✓" if c.get("patch_applied") else "✗"
        print(f"  [{ts}] {patched} {q}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "corrections":
        show_corrections()
    else:
        report_last_answer()
