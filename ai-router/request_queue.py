"""Priority request queue daemon for Costa OS AI router.

Unix socket server that queues and processes AI requests with priority ordering.
Only one request processes at a time (models can't handle concurrent requests).

Usage:
    python3 queue.py daemon   — start the daemon
    python3 queue.py status   — show queue status
    python3 queue.py query "test query"  — send a query via the socket
    python3 queue.py stop     — stop the daemon
"""

import heapq
import json
import os
import signal
import socket
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path

SOCKET_PATH = "/tmp/costa-ai.sock"
RESULT_DIR = "/tmp"
CURRENT_FILE = "/tmp/costa-ai-current.json"
STREAM_FILE = "/tmp/costa-ai-stream"


class Priority(IntEnum):
    VOICE = 0
    INTERACTIVE = 1
    WORKFLOW = 2
    BACKGROUND = 3


PRIORITY_NAMES = {
    "voice": Priority.VOICE,
    "interactive": Priority.INTERACTIVE,
    "workflow": Priority.WORKFLOW,
    "background": Priority.BACKGROUND,
}


@dataclass
class QueuedRequest:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    priority: Priority = Priority.INTERACTIVE
    force_model: str | None = None
    allow_escalation: bool = True
    gather_context: bool = True
    input_modality: str = "text"
    timestamp: float = field(default_factory=time.time)
    callback_path: str | None = None
    stream: bool = False

    def __lt__(self, other: "QueuedRequest") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

    def result_path(self) -> str:
        if self.callback_path:
            return self.callback_path
        return os.path.join(RESULT_DIR, f"costa-ai-result-{self.id}.json")


class RequestQueue:
    """Thread-safe priority queue for AI requests."""

    def __init__(self):
        self._heap: list[QueuedRequest] = []
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()

    def enqueue(self, request: QueuedRequest) -> str:
        with self._lock:
            heapq.heappush(self._heap, request)
        return request.id

    def dequeue(self) -> QueuedRequest | None:
        with self._lock:
            while self._heap:
                req = heapq.heappop(self._heap)
                if req.id not in self._cancelled:
                    return req
                self._cancelled.discard(req.id)
            return None

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            for req in self._heap:
                if req.id == request_id:
                    self._cancelled.add(request_id)
                    return True
            return False

    @property
    def size(self) -> int:
        with self._lock:
            return sum(1 for r in self._heap if r.id not in self._cancelled)

    def pending(self) -> list[dict]:
        with self._lock:
            items = sorted(
                (r for r in self._heap if r.id not in self._cancelled),
            )
            return [
                {
                    "id": r.id,
                    "query": r.query[:80],
                    "priority": r.priority.name,
                    "timestamp": r.timestamp,
                    "input_modality": r.input_modality,
                }
                for r in items
            ]


class StreamWriter:
    """Writes tokens progressively to a stream file, simulating streaming output."""

    def __init__(self, path: str = STREAM_FILE):
        self.path = path

    def start(self):
        Path(self.path).write_text("")

    def write_chunk(self, text: str):
        with open(self.path, "a") as f:
            f.write(text)

    def finish(self):
        pass  # file stays for readers to detect completion

    def write_progressive(self, full_text: str, chunk_size: int = 12):
        """Simulate streaming by writing the full response in chunks."""
        self.start()
        for i in range(0, len(full_text), chunk_size):
            self.write_chunk(full_text[i : i + chunk_size])
            time.sleep(0.02)
        self.finish()


class QueueDaemon:
    """Unix socket server that accepts, queues, and processes AI requests."""

    def __init__(self):
        self.queue = RequestQueue()
        self._running = False
        self._current: dict | None = None
        self._current_lock = threading.Lock()
        self._worker_event = threading.Event()
        self._server_socket: socket.socket | None = None

    # ---- lifecycle ----

    def start(self):
        self._running = True
        self._cleanup_socket()

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(SOCKET_PATH)
        self._server_socket.listen(8)
        self._server_socket.settimeout(1.0)

        worker = threading.Thread(target=self._worker_loop, daemon=True)
        worker.start()

        print(f"costa-ai queue daemon listening on {SOCKET_PATH}")

        try:
            self._accept_loop()
        finally:
            self._shutdown()

    def stop(self):
        self._running = False
        self._worker_event.set()

    # ---- socket server ----

    def _accept_loop(self):
        while self._running:
            try:
                conn, _ = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_connection, args=(conn,), daemon=True
            ).start()

    def _handle_connection(self, conn: socket.socket):
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                # simple framing: one JSON object per connection
                try:
                    json.loads(data)
                    break
                except json.JSONDecodeError:
                    continue

            if not data:
                return

            msg = json.loads(data)
            response = self._dispatch(msg)
            conn.sendall(json.dumps(response).encode())
        except Exception as exc:
            try:
                conn.sendall(json.dumps({"error": str(exc)}).encode())
            except OSError:
                pass
        finally:
            conn.close()

    def _dispatch(self, msg: dict) -> dict:
        action = msg.get("action", "")

        if action == "query":
            return self._handle_query(msg)
        elif action == "cancel":
            rid = msg.get("request_id", "")
            ok = self.queue.cancel(rid)
            return {"ok": ok, "request_id": rid}
        elif action == "status":
            return self._handle_status()
        elif action == "ping":
            return {"ok": True, "pong": True}
        elif action == "stop":
            self.stop()
            return {"ok": True, "stopping": True}
        else:
            return {"error": f"unknown action: {action}"}

    def _handle_query(self, msg: dict) -> dict:
        priority_raw = msg.get("priority", "interactive")
        if isinstance(priority_raw, int):
            priority = Priority(priority_raw)
        else:
            priority = PRIORITY_NAMES.get(str(priority_raw).lower(), Priority.INTERACTIVE)

        req = QueuedRequest(
            query=msg.get("query", ""),
            priority=priority,
            force_model=msg.get("force_model"),
            allow_escalation=msg.get("allow_escalation", True),
            gather_context=msg.get("gather_context", True),
            input_modality=msg.get("input_modality", "text"),
            callback_path=msg.get("callback_path"),
            stream=msg.get("stream", False),
        )
        rid = self.queue.enqueue(req)
        self._worker_event.set()
        return {"ok": True, "request_id": rid, "result_path": req.result_path()}

    def _handle_status(self) -> dict:
        with self._current_lock:
            current = dict(self._current) if self._current else None
        return {
            "ok": True,
            "queue_size": self.queue.size,
            "processing": current,
            "pending": self.queue.pending(),
        }

    # ---- worker ----

    def _worker_loop(self):
        while self._running:
            req = self.queue.dequeue()
            if req is None:
                self._worker_event.wait(timeout=2.0)
                self._worker_event.clear()
                continue

            self._set_current(req)
            try:
                result = self._process(req)
                self._write_result(req, result)
            except Exception as exc:
                self._write_result(req, {
                    "error": str(exc),
                    "request_id": req.id,
                })
            finally:
                self._clear_current()

    def _process(self, req: QueuedRequest) -> dict:
        # Import router here to avoid circular imports at module level
        from router import route_query

        result = route_query(
            req.query,
            force_model=req.force_model,
            allow_escalation=req.allow_escalation,
            gather_context_flag=req.gather_context,
        )

        # Simulate streaming if requested
        if req.stream:
            response_text = result.get("response", "")
            if response_text:
                writer = StreamWriter()
                writer.write_progressive(response_text)

        result["request_id"] = req.id
        result["priority"] = req.priority.name
        result["input_modality"] = req.input_modality
        return result

    def _write_result(self, req: QueuedRequest, result: dict):
        path = req.result_path()
        Path(path).write_text(json.dumps(result, default=str))

    def _set_current(self, req: QueuedRequest):
        info = {
            "request_id": req.id,
            "query": req.query[:120],
            "priority": req.priority.name,
            "started_at": time.time(),
        }
        with self._current_lock:
            self._current = info
        Path(CURRENT_FILE).write_text(json.dumps(info))

    def _clear_current(self):
        with self._current_lock:
            self._current = None
        try:
            os.remove(CURRENT_FILE)
        except FileNotFoundError:
            pass

    # ---- cleanup ----

    def _cleanup_socket(self):
        try:
            os.remove(SOCKET_PATH)
        except FileNotFoundError:
            pass

    def _shutdown(self):
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        self._cleanup_socket()
        try:
            os.remove(CURRENT_FILE)
        except FileNotFoundError:
            pass
        print("costa-ai queue daemon stopped")


# ---- client functions ----


def _send_message(msg: dict, timeout: float = 30.0) -> dict:
    """Send a JSON message to the daemon and return the response."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(SOCKET_PATH)
        sock.sendall(json.dumps(msg).encode())
        sock.shutdown(socket.SHUT_WR)

        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return json.loads(data)
    finally:
        sock.close()


def send_request(
    query: str,
    priority: str = "interactive",
    force_model: str | None = None,
    allow_escalation: bool = True,
    gather_context: bool = True,
    input_modality: str = "text",
    callback_path: str | None = None,
    stream: bool = False,
) -> dict:
    """Send a query to the queue daemon and return the enqueue confirmation."""
    msg: dict = {
        "action": "query",
        "query": query,
        "priority": priority,
        "allow_escalation": allow_escalation,
        "gather_context": gather_context,
        "input_modality": input_modality,
        "stream": stream,
    }
    if force_model:
        msg["force_model"] = force_model
    if callback_path:
        msg["callback_path"] = callback_path
    return _send_message(msg)


def get_queue_status() -> dict:
    """Return current queue status from the daemon."""
    return _send_message({"action": "status"})


def cancel_request(request_id: str) -> bool:
    """Cancel a pending request by id."""
    resp = _send_message({"action": "cancel", "request_id": request_id})
    return resp.get("ok", False)


def is_daemon_running() -> bool:
    """Check if the daemon socket exists and responds to a ping."""
    if not os.path.exists(SOCKET_PATH):
        return False
    try:
        resp = _send_message({"action": "ping"}, timeout=2.0)
        return resp.get("pong", False)
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False


# ---- main ----


def _run_daemon():
    daemon = QueueDaemon()

    def _signal_handler(signum, frame):
        daemon.stop()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    daemon.start()


def main():
    if len(sys.argv) < 2:
        print("Usage: queue.py {daemon|status|query <text>|stop}")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "daemon":
        _run_daemon()

    elif cmd == "status":
        if not is_daemon_running():
            print("daemon is not running")
            sys.exit(1)
        status = get_queue_status()
        print(json.dumps(status, indent=2, default=str))

    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: queue.py query <text> [priority]")
            sys.exit(1)
        query_text = sys.argv[2]
        priority = sys.argv[3] if len(sys.argv) > 3 else "interactive"
        if not is_daemon_running():
            print("daemon is not running")
            sys.exit(1)
        resp = send_request(query_text, priority=priority)
        print(json.dumps(resp, indent=2, default=str))

    elif cmd == "stop":
        if not is_daemon_running():
            print("daemon is not running")
            sys.exit(0)
        resp = _send_message({"action": "stop"})
        print(json.dumps(resp, indent=2, default=str))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
