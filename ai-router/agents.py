#!/usr/bin/env python3
"""Costa OS Agent Pool — dispatch tasks to specialized background agents.

Each agent has a role, system prompt, tool access, and queue assignment.
Queues enforce concurrency limits (e.g., only one SSH to a remote server at a time).
"""

import json
import os
import subprocess
import threading
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque
from typing import Optional

AGENTS_DIR = Path.home() / ".config" / "costa" / "agents"
INSTALLED_AGENTS_DIR = Path("/usr/share/costa-os/configs/costa/agents")
PROJECT_AGENTS_DIR = Path(__file__).parent.parent / "configs" / "costa" / "agents"
STATUS_FILE = Path("/tmp/costa-agents-status.json")
LOG_DIR = Path.home() / ".local" / "share" / "costa" / "agent-logs"


@dataclass
class AgentDef:
    """Agent definition loaded from YAML."""
    name: str
    title: str
    icon: str = ""
    description: str = ""
    queue: str = "unlimited"
    max_concurrent: int = 1
    tools: list = field(default_factory=list)
    servers: list = field(default_factory=list)
    system_prompt: str = ""
    schedule: dict = field(default_factory=dict)
    min_tier: str = ""  # "cloud", "local-14b", "local-7b", or "" (let router decide)


@dataclass
class Task:
    """A task dispatched to an agent."""
    id: str
    agent_name: str
    instruction: str
    status: str = "queued"  # queued, running, done, failed
    result: str = ""
    started_at: float = 0
    finished_at: float = 0
    dispatched_by: str = ""  # who requested this


class ResourceQueue:
    """Cross-process queue that enforces max concurrency per resource.

    Uses fcntl.flock on a shared lock file so that multiple costa-agents
    processes (from different Claude Code sessions) never exceed the
    concurrency limit simultaneously. Critical for SSH — two concurrent
    SSH sessions to the same droplet will crash.
    """
    LOCK_DIR = Path("/tmp/costa-agent-locks")

    def __init__(self, name: str, max_concurrent: int = 1):
        self.name = name
        self.max_concurrent = max_concurrent
        self.LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.LOCK_DIR / f"{name}.lock"
        self._status_path = self.LOCK_DIR / f"{name}.status"
        self._fd: Optional[int] = None

    def acquire(self, timeout: float = 300) -> bool:
        """Block until a slot is available. Returns False on timeout."""
        import fcntl, errno

        fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o666)
        deadline = time.time() + timeout

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Got the lock — write our PID for debugging
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, f"{os.getpid()}\n".encode())
                self._fd = fd
                self._write_status("active")
                return True
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    os.close(fd)
                    raise
                # Lock is held by another process — wait and retry
                if time.time() >= deadline:
                    os.close(fd)
                    return False
                self._write_status("waiting")
                time.sleep(0.5)

    def release(self):
        import fcntl
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._write_status("idle")

    def _write_status(self, state: str):
        """Write queue state for external tools (shell bar, status command)."""
        try:
            self._status_path.write_text(json.dumps({
                "state": state,
                "pid": os.getpid(),
                "time": time.time(),
            }))
        except Exception:
            pass

    @property
    def active_count(self) -> int:
        """Check if any process holds the lock."""
        import fcntl, errno
        try:
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o666)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                return 0  # nobody holds it
            except OSError as e:
                os.close(fd)
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    return 1  # someone holds it
                return 0
        except Exception:
            return 0

    @property
    def waiting_count(self) -> int:
        """Approximate — count status files that say 'waiting'."""
        try:
            data = json.loads(self._status_path.read_text())
            return 1 if data.get("state") == "waiting" else 0
        except Exception:
            return 0


class AgentPool:
    """Manages agent definitions, resource queues, and task dispatch."""

    def __init__(self):
        self.agents: dict[str, AgentDef] = {}
        self.queues: dict[str, ResourceQueue] = {}
        self.tasks: list[Task] = []
        self._task_counter = 0
        self._lock = threading.Lock()
        self._load_agents()

    def _load_agents(self):
        """Load agent definitions from YAML files."""
        for agents_dir in [PROJECT_AGENTS_DIR, INSTALLED_AGENTS_DIR, AGENTS_DIR]:
            if not agents_dir.exists():
                continue
            for f in sorted(agents_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(f.read_text())
                    agent = AgentDef(
                        name=data["name"],
                        title=data.get("title", data["name"]),
                        icon=data.get("icon", ""),
                        description=data.get("description", ""),
                        queue=data.get("queue", "unlimited"),
                        max_concurrent=data.get("max_concurrent", 1),
                        tools=data.get("tools", []),
                        servers=data.get("servers", []),
                        system_prompt=data.get("system_prompt", ""),
                        schedule=data.get("schedule", {}),
                        min_tier=data.get("min_tier", ""),
                    )
                    self.agents[agent.name] = agent

                    # Create queue if needed
                    q = agent.queue
                    if q != "unlimited" and q not in self.queues:
                        self.queues[q] = ResourceQueue(q, agent.max_concurrent)
                except Exception as e:
                    print(f"Warning: failed to load agent {f}: {e}")

    def list_agents(self) -> list[dict]:
        """Return agent info for display."""
        result = []
        for a in self.agents.values():
            q = self.queues.get(a.queue)
            result.append({
                "name": a.name,
                "title": a.title,
                "icon": a.icon,
                "description": a.description,
                "queue": a.queue,
                "queue_active": q.active_count if q else 0,
                "queue_waiting": q.waiting_count if q else 0,
                "status": self._agent_status(a.name),
            })
        return result

    def _agent_status(self, name: str) -> str:
        """Get current status of an agent."""
        for task in reversed(self.tasks):
            if task.agent_name == name:
                if task.status in ("queued", "running"):
                    return task.status
        return "idle"

    def dispatch(self, agent_name: str, instruction: str,
                 dispatched_by: str = "user") -> Optional[Task]:
        """Dispatch a task to an agent. Returns the Task or None if agent unknown."""
        agent = self.agents.get(agent_name)
        if not agent:
            return None

        with self._lock:
            self._task_counter += 1
            task = Task(
                id=f"task-{self._task_counter}-{int(time.time())}",
                agent_name=agent_name,
                instruction=instruction,
                dispatched_by=dispatched_by,
            )
            self.tasks.append(task)

        # Run in background thread
        thread = threading.Thread(
            target=self._run_task, args=(agent, task), daemon=True
        )
        thread.start()
        self._save_status()
        return task

    def _run_task(self, agent: AgentDef, task: Task):
        """Execute a task within its resource queue."""
        queue = self.queues.get(agent.queue)

        # Acquire queue slot (blocks if at capacity)
        if queue:
            task.status = "queued"
            self._save_status()
            if not queue.acquire(timeout=600):  # 10 min — deployments can be slow
                task.status = "failed"
                task.result = f"Timed out waiting for {agent.queue} queue"
                task.finished_at = time.time()
                self._save_status()
                self._notify(agent, task)
                return

        try:
            task.status = "running"
            task.started_at = time.time()
            self._save_status()

            result = self._execute(agent, task)
            task.result = result

            # Detect failures in the result text
            if any(marker in result for marker in ["✗", "FAIL", "Error:", "failed"]):
                task.status = "failed"
            else:
                task.status = "done"
        except Exception as e:
            task.result = f"Error: {e}"
            task.status = "failed"
        finally:
            task.finished_at = time.time()
            if queue:
                queue.release()
            self._save_status()
            self._log_task(task)
            self._write_last_result(task)
            self._notify(agent, task)

    def _execute(self, agent: AgentDef, task: Task) -> str:
        """Execute the task using the appropriate model for this agent.

        Model selection priority:
        1. If agent has min_tier="cloud", force to sonnet (needs cloud capability)
        2. If agent has min_tier="local-14b", use local but only if 14b+ is loaded
        3. Otherwise, let the router decide based on query content
        """
        # Include server config if the agent has servers defined
        server_context = ""
        if agent.servers:
            server_lines = []
            for s in agent.servers:
                server_lines.append(f"  - {s.get('name', '?')}: ssh {s.get('host', '?')}")
                if s.get('deploy_dir'):
                    server_lines.append(f"    deploy_dir: {s['deploy_dir']}")
                if s.get('build_cmd'):
                    server_lines.append(f"    build: {s['build_cmd']}")
                if s.get('restart_cmd'):
                    server_lines.append(f"    restart: {s['restart_cmd']}")
                if s.get('healthcheck'):
                    server_lines.append(f"    healthcheck: {s['healthcheck']}")
            server_context = "\n\nSERVER CONFIG:\n" + "\n".join(server_lines)

        prompt = f"""You are acting as the "{agent.title}" agent for Costa OS.

{agent.system_prompt}{server_context}

YOUR TASK:
{task.instruction}

Execute this task now. Be concise in your response. End with a one-line summary."""

        # Determine if we need to force a specific model tier
        force_model = None
        if agent.min_tier == "cloud":
            force_model = "sonnet"
        elif agent.min_tier == "local-14b":
            # Check if 14b is actually loaded; if not, escalate to cloud
            try:
                current = Path("/tmp/ollama-smart-model").read_text().strip()
                if "14b" not in current and "32b" not in current:
                    force_model = "sonnet"  # local model too small, use cloud
            except Exception:
                force_model = "sonnet"

        # For agents with server configs, try direct execution first
        # (SSH commands don't need an LLM — just run the deploy checklist)
        if agent.servers and self._can_direct_execute(agent, task):
            return self._direct_execute(agent, task)

        try:
            import sys
            router_dir = str(Path(__file__).parent)
            if router_dir not in sys.path:
                sys.path.insert(0, router_dir)
            from router import route_query

            result = route_query(prompt, force_model=force_model)
            return result.get("response", str(result))
        except Exception:
            # Fallback: shell out to costa-ai
            try:
                cmd = ["costa-ai"]
                if force_model:
                    cmd.extend(["--model", force_model])
                cmd.append(prompt)
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                return r.stdout.strip() if r.returncode == 0 else f"Error: {r.stderr}"
            except Exception as e:
                return f"Execution failed: {e}"

    def _can_direct_execute(self, agent: AgentDef, task: Task) -> bool:
        """Check if this agent task can be executed directly (without LLM)."""
        instruction = task.instruction.lower()
        # Deployer with known server can run the deploy checklist directly
        if agent.name == "deployer" and any(
            kw in instruction for kw in ["deploy", "push", "ship", "release"]
        ):
            return True
        # Monitor healthchecks can run directly
        if agent.name == "monitor" and any(
            kw in instruction for kw in ["healthcheck", "health check", "check health", "status"]
        ):
            return True
        return False

    def _direct_execute(self, agent: AgentDef, task: Task) -> str:
        """Execute agent task directly via shell commands (no LLM needed)."""
        results = []

        if agent.name == "deployer":
            for server in agent.servers:
                host = server.get("host", "")
                deploy_dir = server.get("deploy_dir", "")
                build_cmd = server.get("build_cmd", "npm run build")
                restart_cmd = server.get("restart_cmd", "")
                healthcheck = server.get("healthcheck", "")

                if not host or not deploy_dir:
                    results.append(f"✗ {server.get('name', '?')}: missing host or deploy_dir")
                    continue

                name = server.get("name", host)
                steps = []

                # 1. Pull latest code
                pull_cmd = f"cd {deploy_dir} && git pull origin main"
                r = subprocess.run(
                    ["ssh", host, pull_cmd],
                    capture_output=True, text=True, timeout=30
                )
                if r.returncode != 0:
                    results.append(f"✗ {name}: git pull failed — {r.stderr.strip()[:200]}")
                    continue
                steps.append(f"pulled: {r.stdout.strip().split(chr(10))[-1]}")

                # 2. Build
                full_build = f"cd {deploy_dir} && rm -rf .next && {build_cmd}"
                r = subprocess.run(
                    ["ssh", host, full_build],
                    capture_output=True, text=True, timeout=300
                )
                if r.returncode != 0:
                    results.append(f"✗ {name}: build failed — {r.stderr.strip()[:200]}")
                    continue
                steps.append("build: OK")

                # 3. Restart
                if restart_cmd:
                    r = subprocess.run(
                        ["ssh", host, restart_cmd],
                        capture_output=True, text=True, timeout=30
                    )
                    steps.append(f"restart: {'OK' if r.returncode == 0 else 'WARN ' + r.stderr.strip()[:100]}")

                # 4. Healthcheck
                if healthcheck:
                    import time as _time
                    _time.sleep(3)
                    try:
                        r = subprocess.run(
                            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", healthcheck],
                            capture_output=True, text=True, timeout=10
                        )
                        code = r.stdout.strip()
                        steps.append(f"healthcheck: {code}")
                        if code != "200":
                            results.append(f"⚠ {name}: deployed but healthcheck returned {code}")
                            continue
                    except Exception:
                        steps.append("healthcheck: timeout")

                results.append(f"✓ {name}: {' → '.join(steps)}")

        elif agent.name == "monitor":
            for server in agent.servers:
                healthcheck = server.get("healthcheck", "")
                name = server.get("name", server.get("host", "?"))
                if healthcheck:
                    try:
                        r = subprocess.run(
                            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", healthcheck],
                            capture_output=True, text=True, timeout=10
                        )
                        code = r.stdout.strip()
                        results.append(f"{'✓' if code == '200' else '✗'} {name}: HTTP {code}")
                    except Exception:
                        results.append(f"✗ {name}: timeout")

        return "\n".join(results) if results else "No servers configured for direct execution."

    def _notify(self, agent: AgentDef, task: Task):
        """Send desktop notification about task completion."""
        icon = agent.icon or "󰒋"
        status = "completed" if task.status == "done" else "FAILED"
        summary = task.result.split("\n")[-1][:100] if task.result else "No output"
        elapsed = task.finished_at - task.started_at if task.started_at else 0

        subprocess.Popen([
            "notify-send", "-a", "Costa Agents",
            f"{icon} {agent.title}: {status}",
            f"{summary}\n({elapsed:.1f}s)",
        ], start_new_session=True)

    def _write_last_result(self, task: Task):
        """Write last task result to a machine-readable file for external tools."""
        try:
            result_file = Path("/tmp/costa-agent-last-result.json")
            result_file.write_text(json.dumps({
                "id": task.id,
                "agent": task.agent_name,
                "instruction": task.instruction,
                "status": task.status,
                "result": task.result,
                "elapsed_s": round(task.finished_at - task.started_at, 1) if task.started_at else 0,
            }, indent=2))
        except Exception:
            pass

    def _log_task(self, task: Task):
        """Write task result to log file."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"{task.agent_name}.log"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        elapsed = task.finished_at - task.started_at if task.started_at else 0
        with open(log_file, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{timestamp}] Task: {task.id} | Status: {task.status} | {elapsed:.1f}s\n")
            f.write(f"Instruction: {task.instruction[:200]}\n")
            f.write(f"Result: {task.result[:500]}\n")

    def _save_status(self):
        """Write current agent/queue status to JSON for shell bar."""
        try:
            status = {
                "agents": {},
                "queues": {},
                "active_tasks": [],
            }
            for name, agent in self.agents.items():
                status["agents"][name] = {
                    "title": agent.title,
                    "icon": agent.icon,
                    "status": self._agent_status(name),
                    "queue": agent.queue,
                }
            for name, q in self.queues.items():
                status["queues"][name] = {
                    "active": q.active_count,
                    "waiting": q.waiting_count,
                    "max": q.max_concurrent,
                }
            for task in self.tasks:
                if task.status in ("queued", "running"):
                    status["active_tasks"].append({
                        "id": task.id,
                        "agent": task.agent_name,
                        "instruction": task.instruction[:100],
                        "status": task.status,
                    })
            STATUS_FILE.write_text(json.dumps(status, indent=2))
        except Exception:
            pass

    def get_task(self, task_id: str) -> Optional[Task]:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_recent_tasks(self, limit: int = 20) -> list[Task]:
        return list(reversed(self.tasks[-limit:]))


# ── Singleton ──
_pool: Optional[AgentPool] = None


def get_pool() -> AgentPool:
    global _pool
    if _pool is None:
        _pool = AgentPool()
    return _pool
