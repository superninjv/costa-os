"""Costa AI SQLite persistence — query history, usage tracking, cost estimation, budgets.

Database: ~/.config/costa/costa.db

Provides:
- Query logging with timing breakdown and cost estimation
- Conversation history (replaces /tmp/costa-conversation.json)
- Full-text search over past queries
- Usage statistics and cost aggregation
- Monthly API spend budget enforcement
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path.home() / ".config" / "costa" / "costa.db"

# Cost per 1K tokens (USD) — Anthropic pricing as of 2025
COST_PER_1K = {
    "haiku": {"input": 0.001, "output": 0.005},
    "sonnet": {"input": 0.003, "output": 0.015},
    "opus": {"input": 0.015, "output": 0.075},
    "local": {"input": 0, "output": 0},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id              INTEGER PRIMARY KEY,
    ts              TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
    query           TEXT NOT NULL,
    response        TEXT,
    model           TEXT,
    route           TEXT,
    escalated       BOOLEAN DEFAULT 0,
    context_ms      INTEGER,
    knowledge_ms    INTEGER,
    model_ms        INTEGER,
    total_ms        INTEGER,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        REAL DEFAULT 0,
    input_modality  TEXT DEFAULT 'text',
    command_executed TEXT,
    tags            TEXT,
    routing_label   TEXT
);

CREATE INDEX IF NOT EXISTS idx_queries_ts ON queries(ts);
CREATE INDEX IF NOT EXISTS idx_queries_model ON queries(model);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY,
    started     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
    last_active TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
    title       TEXT,
    turn_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    conversation_id INTEGER REFERENCES conversations(id),
    query_id        INTEGER REFERENCES queries(id),
    turn_number     INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id          INTEGER PRIMARY KEY,
    workflow    TEXT NOT NULL,
    started     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
    finished    TEXT,
    status      TEXT DEFAULT 'running',
    steps_run   INTEGER DEFAULT 0,
    total_ms    INTEGER,
    outputs     TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow);

CREATE TABLE IF NOT EXISTS query_ast_features (
    query_id INTEGER,
    file_path TEXT,
    ast_features TEXT,
    ts TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_qaf_query_id ON query_ast_features(query_id);
"""

_connection = None


def get_db() -> sqlite3.Connection:
    """Get or create the singleton database connection."""
    global _connection
    if _connection is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA synchronous=NORMAL")
        _connection.executescript(SCHEMA)
        _connection.commit()
    return _connection


def close_db():
    """Close the database connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def estimate_cost(model: str, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """Estimate the cost of a query in USD."""
    # Determine pricing tier from model name
    tier = "local"
    model_lower = (model or "").lower()
    for key in ("opus", "sonnet", "haiku"):
        if key in model_lower:
            tier = key
            break

    rates = COST_PER_1K.get(tier, COST_PER_1K["local"])
    cost = (input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"]
    return round(cost, 6)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def log_query(result: dict, input_modality: str = "text") -> int:
    """Log a completed query to the database.

    Args:
        result: dict from route_query() with keys: response, model, route,
                escalated, elapsed_ms, command_executed, and optional timing breakdowns
        input_modality: 'text', 'voice', or 'rofi'

    Returns:
        The query row id.
    """
    db = get_db()

    query_text = result.get("query", "")
    response = result.get("response", "")
    model = result.get("model", "")
    route = result.get("route", "")

    input_tokens = estimate_tokens(query_text)
    output_tokens = estimate_tokens(response)
    cost = estimate_cost(model, input_tokens, output_tokens)

    cursor = db.execute(
        """INSERT INTO queries
           (query, response, model, route, escalated,
            context_ms, knowledge_ms, model_ms, total_ms,
            input_tokens, output_tokens, cost_usd,
            input_modality, command_executed, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            query_text,
            response,
            model,
            route,
            1 if result.get("escalated") else 0,
            result.get("context_ms"),
            result.get("knowledge_ms"),
            result.get("model_ms"),
            result.get("total_ms") or result.get("elapsed_ms"),
            input_tokens,
            output_tokens,
            cost,
            input_modality,
            result.get("command_executed"),
            json.dumps(result.get("tags")) if result.get("tags") else None,
        ),
    )
    db.commit()
    return cursor.lastrowid


def get_conversation_history(n: int = 5) -> list[dict]:
    """Get the last N conversation turns from the database.

    Returns list of dicts with keys: q, a, m, t (matching the old JSON format).
    """
    db = get_db()
    rows = db.execute(
        """SELECT query, response, model, ts
           FROM queries
           WHERE response IS NOT NULL AND response != ''
             AND route IN ('local', 'local+escalated', 'local+weather')
           ORDER BY id DESC LIMIT ?""",
        (n,),
    ).fetchall()

    # Reverse to chronological order
    history = []
    for row in reversed(rows):
        history.append({
            "q": row["query"],
            "a": (row["response"] or "")[:300],
            "m": row["model"] or "",
            "t": row["ts"],
        })
    return history


def search_history(term: str, limit: int = 20) -> list[dict]:
    """Full-text search over past queries and responses."""
    db = get_db()
    rows = db.execute(
        """SELECT id, ts, query, response, model, route, total_ms, cost_usd
           FROM queries
           WHERE query LIKE ? OR response LIKE ?
           ORDER BY id DESC LIMIT ?""",
        (f"%{term}%", f"%{term}%", limit),
    ).fetchall()
    return [dict(row) for row in rows]


def get_history(n: int = 20) -> list[dict]:
    """Get the last N queries with metadata."""
    db = get_db()
    rows = db.execute(
        """SELECT id, ts, query, response, model, route, escalated,
                  total_ms, cost_usd, input_modality, command_executed
           FROM queries ORDER BY id DESC LIMIT ?""",
        (n,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_usage_stats(period: str = "today") -> dict:
    """Get aggregated usage statistics for a time period.

    Args:
        period: 'today', 'week', 'month', 'all'

    Returns:
        dict with: total_queries, total_cost, avg_latency_ms, model_breakdown,
                   escalation_rate, queries_by_modality
    """
    db = get_db()

    if period == "today":
        since = datetime.now().strftime("%Y-%m-%dT00:00:00")
    elif period == "week":
        since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    elif period == "month":
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    else:
        since = "2000-01-01T00:00:00"

    # Overall stats
    row = db.execute(
        """SELECT COUNT(*) as total, SUM(cost_usd) as cost,
                  AVG(total_ms) as avg_ms, SUM(escalated) as escalated
           FROM queries WHERE ts >= ?""",
        (since,),
    ).fetchone()

    total = row["total"] or 0
    cost = round(row["cost"] or 0, 4)
    avg_ms = int(row["avg_ms"] or 0)
    escalated = row["escalated"] or 0

    # Model breakdown
    model_rows = db.execute(
        """SELECT model, COUNT(*) as count, SUM(cost_usd) as cost
           FROM queries WHERE ts >= ?
           GROUP BY model ORDER BY count DESC""",
        (since,),
    ).fetchall()
    model_breakdown = {r["model"]: {"count": r["count"], "cost": round(r["cost"] or 0, 4)}
                       for r in model_rows}

    # Modality breakdown
    modality_rows = db.execute(
        """SELECT input_modality, COUNT(*) as count
           FROM queries WHERE ts >= ?
           GROUP BY input_modality""",
        (since,),
    ).fetchall()
    modality_breakdown = {r["input_modality"]: r["count"] for r in modality_rows}

    return {
        "period": period,
        "total_queries": total,
        "total_cost": cost,
        "avg_latency_ms": avg_ms,
        "escalation_rate": round(escalated / total, 2) if total > 0 else 0,
        "escalated_count": escalated,
        "model_breakdown": model_breakdown,
        "queries_by_modality": modality_breakdown,
    }


def get_setting(key: str, default: str = "") -> str:
    """Get a setting value."""
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """Set a setting value."""
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    db.commit()


def check_budget() -> dict:
    """Check current spend against budget.

    Returns:
        dict with: budget, spent, remaining, exceeded, period
    """
    budget_str = get_setting("monthly_budget", "0")
    try:
        budget = float(budget_str)
    except ValueError:
        budget = 0

    if budget <= 0:
        return {"budget": 0, "spent": 0, "remaining": 0, "exceeded": False, "period": "month"}

    # Get current month's spend
    month_start = datetime.now().strftime("%Y-%m-01T00:00:00")
    db = get_db()
    row = db.execute(
        "SELECT SUM(cost_usd) as spent FROM queries WHERE ts >= ?",
        (month_start,),
    ).fetchone()

    spent = round(row["spent"] or 0, 4)
    remaining = round(budget - spent, 4)

    return {
        "budget": budget,
        "spent": spent,
        "remaining": remaining,
        "exceeded": spent >= budget,
        "period": "month",
    }


def set_budget(amount: float, period: str = "month"):
    """Set the API spend budget."""
    set_setting(f"{period}ly_budget", str(amount))


def log_workflow_run(workflow: str, status: str = "running",
                     steps_run: int = 0, total_ms: int = 0,
                     outputs: dict | None = None) -> int:
    """Log a workflow execution."""
    db = get_db()
    cursor = db.execute(
        """INSERT INTO workflow_runs (workflow, status, steps_run, total_ms, outputs)
           VALUES (?, ?, ?, ?, ?)""",
        (workflow, status, steps_run, total_ms,
         json.dumps(outputs) if outputs else None),
    )
    db.commit()
    return cursor.lastrowid


def update_workflow_run(run_id: int, status: str, steps_run: int = 0,
                        total_ms: int = 0, outputs: dict | None = None):
    """Update a workflow run record."""
    db = get_db()
    db.execute(
        """UPDATE workflow_runs
           SET finished = strftime('%Y-%m-%dT%H:%M:%S','now','localtime'),
               status = ?, steps_run = ?, total_ms = ?, outputs = ?
           WHERE id = ?""",
        (status, steps_run, total_ms,
         json.dumps(outputs) if outputs else None, run_id),
    )
    db.commit()


def get_workflow_log(workflow: str, limit: int = 10) -> list[dict]:
    """Get recent runs for a workflow."""
    db = get_db()
    rows = db.execute(
        """SELECT * FROM workflow_runs
           WHERE workflow = ?
           ORDER BY id DESC LIMIT ?""",
        (workflow, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def update_routing_feedback(query_id: int, was_correct: bool):
    """Log routing outcome for next training cycle."""
    db = get_db()
    label = "correct" if was_correct else "incorrect"
    db.execute(
        "UPDATE queries SET routing_label = ? WHERE id = ?",
        (label, query_id),
    )
    db.commit()


def get_training_data(limit: int = 5000) -> list[dict]:
    """Get labeled query data for ML router training."""
    db = get_db()
    rows = db.execute(
        """SELECT query, route, escalated, routing_label
           FROM queries
           WHERE route IS NOT NULL
           ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def backfill_routing_labels() -> int:
    """One-time backfill: set routing_label for all unlabeled queries.

    Non-escalated → "correct", escalated → "incorrect".
    Returns the number of rows updated.
    """
    db = get_db()
    cursor = db.execute(
        """UPDATE queries SET routing_label = CASE
               WHEN escalated = 1 THEN 'incorrect'
               ELSE 'correct'
           END
           WHERE routing_label IS NULL
             AND route IS NOT NULL
             AND route != 'cancelled'""",
    )
    db.commit()
    return cursor.rowcount


def find_recent_query(query_text: str, max_age_minutes: int = 30) -> int | None:
    """Find a recent query ID by matching query text.

    Args:
        query_text: The query text to search for.
        max_age_minutes: Maximum age in minutes to search.

    Returns:
        The query row ID or None if not found.
    """
    db = get_db()
    since = (datetime.now() - timedelta(minutes=max_age_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    row = db.execute(
        """SELECT id FROM queries
           WHERE query = ? AND ts >= ?
           ORDER BY id DESC LIMIT 1""",
        (query_text, since),
    ).fetchone()
    return row["id"] if row else None


def log_ast_features(query_id: int, file_path: str, features_array: list) -> None:
    """Store AST feature vector for a query/file pair.

    Args:
        query_id: The query row ID from the queries table.
        file_path: Path to the source file the features were extracted from.
        features_array: List of floats representing AST features.
    """
    db = get_db()
    db.execute(
        """INSERT INTO query_ast_features (query_id, file_path, ast_features)
           VALUES (?, ?, ?)""",
        (query_id, file_path, json.dumps(features_array)),
    )
    db.commit()


def get_ast_training_data(limit: int = 5000) -> list[dict]:
    """Get AST feature data joined with query routing labels for ML training.

    Returns:
        List of dicts with keys: query, route, file_path, ast_features (parsed list).
        Only includes rows where route is not NULL.
    """
    db = get_db()
    rows = db.execute(
        """SELECT q.query, q.route, qaf.file_path, qaf.ast_features
           FROM query_ast_features qaf
           JOIN queries q ON q.id = qaf.query_id
           WHERE q.route IS NOT NULL
           ORDER BY qaf.query_id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            "query": row["query"],
            "route": row["route"],
            "file_path": row["file_path"],
            "ast_features": json.loads(row["ast_features"]) if row["ast_features"] else [],
        })
    return result


def queries_since_last_train() -> int:
    """Count queries logged since the ML model file was last modified.

    Returns 9999 if no model file exists (always stale).
    """
    model_path = Path.home() / ".config" / "costa" / "ml_router.pt"
    if not model_path.exists():
        return 9999

    model_mtime = datetime.fromtimestamp(model_path.stat().st_mtime)
    since = model_mtime.strftime("%Y-%m-%dT%H:%M:%S")

    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM queries WHERE ts >= ?",
        (since,),
    ).fetchone()
    return row["cnt"] if row else 0
