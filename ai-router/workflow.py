"""Costa OS Workflow Engine — YAML-defined automation with AI, shell, and notify steps.

An n8n-style workflow system for Costa OS. Workflows are defined as YAML files
in ~/.config/costa/workflows/ and can be triggered manually, by schedule (systemd
timers), or by other Costa subsystems.

Step types:
    costa-ai  — route a query through the AI stack (local Ollama or cloud)
    shell     — run a shell command with timeout
    notify    — send a desktop notification via notify-send
    condition — evaluate a simple condition; skip remaining steps if false
    wait      — sleep for a duration
"""

import subprocess
import json
import re
import shlex
import time
import sqlite3
import sys
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

WORKFLOW_DIR = Path.home() / ".config" / "costa" / "workflows"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
LOG_DB = Path.home() / ".local" / "share" / "costa" / "workflow-log.db"
SESSION_LOG_DIR = Path.home() / ".local" / "share" / "costa" / "claude-sessions"
SESSION_STATUS = Path("/tmp/costa-session-status.json")
MAX_BUDGET_CAP = 50.0  # Hard cap — YAML cannot exceed this

INTERPOLATION_RE = re.compile(r"\{\{steps\.(\w+)\.output\}\}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStep:
    """A single step within a workflow."""
    id: str
    action: str
    query: str = ""
    command: str = ""
    title: str = ""
    body: str = ""
    model: str | None = None
    condition: str = ""
    duration: float = 0.0
    depends_on: list[str] = field(default_factory=list)
    # claude-code step fields
    workdir: str = ""
    budget: float = 0.0
    allowed_tools: str = ""
    permission_mode: str = ""
    timeout: float = 0.0
    prompt_file: str = ""


@dataclass
class Workflow:
    """A parsed YAML workflow definition."""
    name: str
    description: str
    trigger: dict = field(default_factory=dict)
    steps: list[WorkflowStep] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path) -> "Workflow":
        """Parse a YAML workflow file into a Workflow instance."""
        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid workflow file: {path}")

        steps = []
        for s in data.get("steps", []):
            # Build condition string from shorthand keys if needed
            condition = s.get("condition", "")
            if not condition and s.get("action") == "condition":
                check = s.get("check", "")
                if check:
                    if s.get("contains"):
                        condition = f'steps.{check}.output contains "{s["contains"]}"'
                    elif s.get("matches"):
                        condition = f'steps.{check}.output matches "{s["matches"]}"'
                    elif s.get("is_empty"):
                        condition = f'steps.{check}.output is_empty'
                    elif s.get("not_empty"):
                        condition = f'steps.{check}.output not_empty'

            steps.append(WorkflowStep(
                id=s.get("id", ""),
                action=s.get("action", ""),
                query=s.get("query", ""),
                command=s.get("command", ""),
                title=s.get("title", ""),
                body=s.get("body", ""),
                model=s.get("model"),
                condition=condition,
                duration=float(s.get("duration", 0)),
                depends_on=s.get("depends_on", []),
                workdir=s.get("workdir", ""),
                budget=float(s.get("budget", 0)),
                allowed_tools=s.get("allowed_tools", ""),
                permission_mode=s.get("permission_mode", ""),
                timeout=float(s.get("timeout", 0)),
                prompt_file=s.get("prompt_file", ""),
            ))

        return cls(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            trigger=data.get("trigger", {}),
            steps=steps,
        )

    @classmethod
    def load(cls, name: str) -> "Workflow":
        """Load a workflow by name from the standard directory."""
        path = WORKFLOW_DIR / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {path}")
        return cls.from_file(path)


# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

def _interpolate(text: str, outputs: dict[str, str]) -> str:
    """Replace {{steps.<id>.output}} placeholders with actual step outputs."""
    def _replace(match: re.Match) -> str:
        step_id = match.group(1)
        return outputs.get(step_id, f"[no output from {step_id}]")
    return INTERPOLATION_RE.sub(_replace, text)


def _interpolate_shell(text: str, outputs: dict[str, str]) -> str:
    """Like _interpolate but shell-quotes each substituted value to prevent injection."""
    def _replace(match: re.Match) -> str:
        step_id = match.group(1)
        value = outputs.get(step_id, f"[no output from {step_id}]")
        return shlex.quote(value)
    return INTERPOLATION_RE.sub(_replace, text)


# ---------------------------------------------------------------------------
# Step executors
# ---------------------------------------------------------------------------

def _exec_costa_ai(step: WorkflowStep, outputs: dict[str, str]) -> str:
    """Execute a costa-ai step by routing through the AI stack."""
    from router import route_query

    query = _interpolate(step.query, outputs)
    force_model = step.model if step.model and step.model != "local" else None
    result = route_query(query, force_model=force_model)
    return result.get("response", "")


# Dangerous patterns that should never appear in workflow shell steps.
# Workflow YAML files are user-authored, but interpolated values from AI step
# outputs could inject malicious content via {{steps.<id>.output}}.
_WORKFLOW_DANGEROUS_RE = re.compile(
    r"|".join([
        r"\brm\s+(-rf?|--recursive)",
        r"\bdd\s+if=",
        r"\bmkfs\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bpoweroff\b",
        r"\bcurl\b.*\|\s*\bbash\b",
        r"\bwget\b.*\|\s*\bsh\b",
        r"\beval\b",
        r"\bexec\b",
        r"\bpython[23]?\s+-c\b",
        r">\s*/dev/",
    ]),
    re.IGNORECASE,
)


def _exec_shell(step: WorkflowStep, outputs: dict[str, str]) -> str:
    """Execute a shell command and return its stdout.

    WARNING: Workflow YAML shell steps run with shell=True. The command
    template comes from a trusted YAML file. Interpolated step outputs
    (from AI responses) are shell-quoted to prevent injection and also
    checked against a dangerous pattern deny list.
    """
    command = _interpolate_shell(step.command, outputs)

    # Check the final interpolated command for dangerous patterns
    if _WORKFLOW_DANGEROUS_RE.search(command):
        return f"[BLOCKED: interpolated command matches dangerous pattern: {command[:120]}]"

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0 and proc.stderr.strip():
            output = output + ("\n" if output else "") + proc.stderr.strip()
        return output
    except subprocess.TimeoutExpired:
        return "[shell step timed out after 60s]"


def _exec_claude_code(step: WorkflowStep, outputs: dict[str, str]) -> str:
    """Execute an autonomous Claude Code session via the CLI's headless mode.

    Runs `claude -p` with budget limits, tool restrictions, and session logging.
    Output is saved to ~/.local/share/costa/claude-sessions/.
    """
    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve prompt — from prompt_file or inline query
    query = _interpolate(step.query, outputs)
    if step.prompt_file:
        prompt_path = Path(_interpolate(step.prompt_file, outputs)).expanduser()
        if prompt_path.exists():
            query = prompt_path.read_text()

    if not query:
        return "[claude-code: no prompt provided]"

    # Build command
    cmd = ["claude", "-p", "--output-format", "json"]

    if step.model:
        cmd.extend(["--model", step.model])

    budget = min(step.budget or 5.0, MAX_BUDGET_CAP)
    cmd.extend(["--max-budget-usd", str(budget)])

    if step.allowed_tools:
        cmd.extend(["--allowedTools", step.allowed_tools])

    mode = step.permission_mode or "acceptEdits"
    cmd.extend(["--permission-mode", mode])

    cmd.extend(["--", query])

    # Working directory
    workdir = None
    if step.workdir:
        workdir = str(Path(_interpolate(step.workdir, outputs)).expanduser())

    # Session logging
    session_name = f"session-{time.strftime('%Y%m%d-%H%M%S')}"
    log_file = SESSION_LOG_DIR / f"{session_name}.json"

    # Write status for bar integration
    status = {
        "session": session_name,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workdir": workdir or "",
        "budget": budget,
        "model": step.model or "default",
        "status": "running",
    }
    try:
        SESSION_STATUS.write_text(json.dumps(status))
    except Exception:
        pass

    # Run Claude Code
    timeout = step.timeout or 14400  # 4 hours default
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        output = proc.stdout
        stderr = proc.stderr

        # Save full output to session log
        log_data = {
            **status,
            "status": "completed" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode,
            "output": output[:50000],  # Cap at 50KB for log
            "stderr": stderr[:5000] if stderr else "",
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        log_file.write_text(json.dumps(log_data, indent=2))

        # Parse JSON output for workflow interpolation
        try:
            result = json.loads(output)
            # Extract the text result from Claude's JSON output
            workflow_output = result.get("result", output[:10000])
        except (json.JSONDecodeError, AttributeError):
            workflow_output = output[:10000]

    except subprocess.TimeoutExpired:
        workflow_output = f"[claude-code session timed out after {timeout}s]"
        log_data = {**status, "status": "timeout", "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
        log_file.write_text(json.dumps(log_data, indent=2))

    # Clear running status
    try:
        SESSION_STATUS.write_text(json.dumps({"status": "idle"}))
    except Exception:
        pass

    return workflow_output


def _exec_notify(step: WorkflowStep, outputs: dict[str, str]) -> str:
    """Send a desktop notification via notify-send."""
    title = _interpolate(step.title, outputs)
    body = _interpolate(step.body, outputs)
    try:
        subprocess.run(
            ["notify-send", "--app-name=Costa Flow", title, body],
            timeout=5,
        )
        return f"Notified: {title}"
    except Exception as e:
        return f"[notify failed: {e}]"


def _eval_condition(step: WorkflowStep, outputs: dict[str, str]) -> bool:
    """Evaluate a simple condition string.

    Supported forms:
        steps.<id>.output contains "<text>"
        steps.<id>.output matches "<regex>"
        steps.<id>.output is_empty
        steps.<id>.output not_empty
    """
    cond = step.condition.strip()
    if not cond:
        return True

    # Parse: steps.<id>.output <operator> <value>
    m = re.match(
        r"steps\.(\w+)\.output\s+(contains|matches|is_empty|not_empty)(?:\s+\"(.*)\")?",
        cond,
    )
    if not m:
        return True  # unparseable condition — treat as true, don't block

    step_id, operator, value = m.group(1), m.group(2), m.group(3) or ""
    step_output = outputs.get(step_id, "")

    if operator == "contains":
        return value.lower() in step_output.lower()
    elif operator == "matches":
        return bool(re.search(value, step_output, re.IGNORECASE))
    elif operator == "is_empty":
        return step_output.strip() == ""
    elif operator == "not_empty":
        return step_output.strip() != ""

    return True


def _exec_wait(step: WorkflowStep) -> str:
    """Sleep for the specified duration."""
    duration = step.duration
    if duration > 0:
        time.sleep(duration)
    return f"Waited {duration}s"


# ---------------------------------------------------------------------------
# Logging (SQLite)
# ---------------------------------------------------------------------------

def _get_log_db() -> sqlite3.Connection:
    """Open (and initialize if needed) the workflow log database."""
    LOG_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOG_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            total_ms INTEGER,
            steps_executed INTEGER,
            outputs TEXT,
            error TEXT
        )
    """)
    conn.commit()
    return conn


def _log_run(name: str, total_ms: int, steps_executed: int,
             outputs: dict[str, str], error: str | None = None) -> None:
    """Write a workflow run to the log database."""
    try:
        conn = _get_log_db()
        conn.execute(
            "INSERT INTO workflow_runs (name, total_ms, steps_executed, outputs, error) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, total_ms, steps_executed, json.dumps(outputs), error),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # logging should never break a workflow


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def execute_workflow(name: str) -> dict[str, Any]:
    """Load and execute a workflow by name.

    Returns:
        dict with: name, steps_executed, total_ms, outputs (step_id -> output)
    """
    wf = Workflow.load(name)
    outputs: dict[str, str] = {}
    steps_executed = 0
    start = time.time()
    error = None

    for step in wf.steps:
        try:
            # Check depends_on — all dependencies must have produced output
            if step.depends_on:
                missing = [d for d in step.depends_on if d not in outputs]
                if missing:
                    outputs[step.id] = f"[skipped: missing dependencies {missing}]"
                    continue

            if step.action == "costa-ai":
                outputs[step.id] = _exec_costa_ai(step, outputs)

            elif step.action == "shell":
                outputs[step.id] = _exec_shell(step, outputs)

            elif step.action == "claude-code":
                outputs[step.id] = _exec_claude_code(step, outputs)

            elif step.action == "notify":
                outputs[step.id] = _exec_notify(step, outputs)

            elif step.action == "condition":
                if not _eval_condition(step, outputs):
                    outputs[step.id] = "[condition false — stopping workflow]"
                    steps_executed += 1
                    break
                outputs[step.id] = "[condition true — continuing]"

            elif step.action == "wait":
                outputs[step.id] = _exec_wait(step)

            else:
                outputs[step.id] = f"[unknown action: {step.action}]"

            steps_executed += 1

        except Exception as e:
            outputs[step.id] = f"[error: {e}]"
            steps_executed += 1
            if step.action == "condition":
                error = str(e)
                break

    total_ms = int((time.time() - start) * 1000)
    _log_run(name, total_ms, steps_executed, outputs, error)

    return {
        "name": wf.name,
        "steps_executed": steps_executed,
        "total_ms": total_ms,
        "outputs": outputs,
    }


# ---------------------------------------------------------------------------
# Workflow management
# ---------------------------------------------------------------------------

def list_workflows() -> list[dict[str, Any]]:
    """Return available workflows with name, description, and trigger info."""
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    workflows = []
    for path in sorted(WORKFLOW_DIR.glob("*.yaml")):
        try:
            wf = Workflow.from_file(path)
            workflows.append({
                "name": wf.name,
                "description": wf.description,
                "trigger": wf.trigger,
                "steps": len(wf.steps),
                "file": str(path),
            })
        except Exception as e:
            workflows.append({
                "name": path.stem,
                "description": f"[parse error: {e}]",
                "trigger": {},
                "steps": 0,
                "file": str(path),
            })
    return workflows


def install_workflow(name: str) -> str:
    """Create a systemd user timer for a scheduled workflow.

    Reads trigger.calendar from the YAML and generates a .service + .timer pair.
    Returns a status message.
    """
    wf = Workflow.load(name)

    calendar = wf.trigger.get("calendar")
    if not calendar:
        return f"Workflow '{name}' has no trigger.calendar — cannot install timer."

    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    service_name = f"costa-flow-{name}"
    service_path = SYSTEMD_USER_DIR / f"{service_name}.service"
    timer_path = SYSTEMD_USER_DIR / f"{service_name}.timer"

    # Find the costa-flow script or fall back to running this module directly
    costa_flow_bin = "costa-flow"
    service_content = f"""\
[Unit]
Description=Costa Flow: {wf.description or name}

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 {Path(__file__).resolve()} run {name}
Environment=HOME={Path.home()}
"""

    timer_content = f"""\
[Unit]
Description=Timer for Costa Flow: {wf.description or name}

[Timer]
OnCalendar={calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""

    service_path.write_text(service_content)
    timer_path.write_text(timer_content)

    # Reload systemd and enable the timer
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{service_name}.timer"],
        capture_output=True,
    )

    return f"Installed and enabled {service_name}.timer (schedule: {calendar})"


def uninstall_workflow(name: str) -> str:
    """Remove the systemd user timer for a workflow."""
    service_name = f"costa-flow-{name}"
    timer_path = SYSTEMD_USER_DIR / f"{service_name}.timer"
    service_path = SYSTEMD_USER_DIR / f"{service_name}.service"

    if not timer_path.exists() and not service_path.exists():
        return f"No timer found for workflow '{name}'."

    # Stop and disable
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{service_name}.timer"],
        capture_output=True,
    )

    # Remove files
    if timer_path.exists():
        timer_path.unlink()
    if service_path.exists():
        service_path.unlink()

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)

    return f"Uninstalled {service_name}.timer and {service_name}.service"


def get_workflow_log(name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Read recent workflow runs from the SQLite log database."""
    if not LOG_DB.exists():
        return []

    try:
        conn = _get_log_db()
        cursor = conn.execute(
            "SELECT id, name, started_at, total_ms, steps_executed, outputs, error "
            "FROM workflow_runs WHERE name = ? ORDER BY id DESC LIMIT ?",
            (name, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": r[0],
                "name": r[1],
                "started_at": r[2],
                "total_ms": r[3],
                "steps_executed": r[4],
                "outputs": json.loads(r[5]) if r[5] else {},
                "error": r[6],
            }
            for r in rows
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: workflow.py <run|list|install|uninstall|log> [name]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        workflows = list_workflows()
        if not workflows:
            print("No workflows found in ~/.config/costa/workflows/")
            return
        for wf in workflows:
            trigger = wf["trigger"].get("type", "manual")
            calendar = wf["trigger"].get("calendar", "")
            schedule = f" ({calendar})" if calendar else ""
            print(f"  {wf['name']:24s} {wf['steps']} steps  [{trigger}{schedule}]")
            if wf["description"]:
                print(f"    {wf['description']}")

    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Usage: workflow.py run <name>")
            sys.exit(1)
        name = sys.argv[2]
        print(f"Running workflow: {name}")
        result = execute_workflow(name)
        print(f"Done in {result['total_ms']}ms — {result['steps_executed']} steps executed")
        for step_id, output in result["outputs"].items():
            preview = output[:120].replace("\n", " ") if output else "(empty)"
            print(f"  {step_id}: {preview}")

    elif cmd == "install":
        if len(sys.argv) < 3:
            print("Usage: workflow.py install <name>")
            sys.exit(1)
        print(install_workflow(sys.argv[2]))

    elif cmd == "uninstall":
        if len(sys.argv) < 3:
            print("Usage: workflow.py uninstall <name>")
            sys.exit(1)
        print(uninstall_workflow(sys.argv[2]))

    elif cmd == "log":
        if len(sys.argv) < 3:
            print("Usage: workflow.py log <name>")
            sys.exit(1)
        runs = get_workflow_log(sys.argv[2])
        if not runs:
            print("No runs logged.")
            return
        for run in runs:
            status = "ERROR" if run["error"] else "OK"
            print(f"  [{run['started_at']}] {status} — {run['steps_executed']} steps, {run['total_ms']}ms")
            if run["error"]:
                print(f"    Error: {run['error']}")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: workflow.py <run|list|install|uninstall|log> [name]")
        sys.exit(1)


if __name__ == "__main__":
    main()
