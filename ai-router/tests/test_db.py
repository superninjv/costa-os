"""Tests for ai-router/db.py — SQLite persistence, usage tracking, cost estimation."""

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Override DB_PATH before importing db module
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db_path = _test_db.name
_test_db.close()


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    """Each test gets a fresh database."""
    import db
    monkeypatch.setattr(db, "DB_PATH", Path(_test_db_path))
    monkeypatch.setattr(db, "_connection", None)
    # Remove old db
    try:
        os.unlink(_test_db_path)
    except FileNotFoundError:
        pass
    yield
    db.close_db()


class TestCostEstimation:
    def test_local_is_free(self):
        from db import estimate_cost
        assert estimate_cost("qwen2.5:14b", 1000, 1000) == 0

    def test_haiku_cost(self):
        from db import estimate_cost
        cost = estimate_cost("haiku", 1000, 1000)
        assert cost > 0
        assert cost < 0.01  # haiku is cheap

    def test_sonnet_cost(self):
        from db import estimate_cost
        cost = estimate_cost("sonnet", 1000, 1000)
        assert cost > estimate_cost("haiku", 1000, 1000)

    def test_opus_cost(self):
        from db import estimate_cost
        cost = estimate_cost("opus", 1000, 1000)
        assert cost > estimate_cost("sonnet", 1000, 1000)

    def test_zero_tokens(self):
        from db import estimate_cost
        assert estimate_cost("haiku", 0, 0) == 0

    def test_model_name_detection(self):
        from db import estimate_cost
        # Full model IDs should still detect the tier
        assert estimate_cost("claude-haiku-4-5-20251001", 1000, 0) > 0
        assert estimate_cost("claude-sonnet-4-6-20250514", 1000, 0) > 0


class TestTokenEstimation:
    def test_empty(self):
        from db import estimate_tokens
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_short(self):
        from db import estimate_tokens
        assert estimate_tokens("hi") >= 1

    def test_proportional(self):
        from db import estimate_tokens
        short = estimate_tokens("hello world")
        long = estimate_tokens("hello world " * 100)
        assert long > short


class TestLogQuery:
    def test_basic_logging(self):
        from db import log_query, get_db

        result = {
            "query": "what is linux",
            "response": "Linux is an operating system.",
            "model": "qwen2.5:14b",
            "route": "local",
            "escalated": False,
            "elapsed_ms": 500,
        }
        row_id = log_query(result)
        assert row_id > 0

        db = get_db()
        row = db.execute("SELECT * FROM queries WHERE id = ?", (row_id,)).fetchone()
        assert row["query"] == "what is linux"
        assert row["model"] == "qwen2.5:14b"
        assert row["route"] == "local"
        assert row["escalated"] == 0
        assert row["cost_usd"] == 0  # local is free

    def test_cloud_cost_logged(self):
        from db import log_query, get_db

        result = {
            "query": "x" * 400,  # ~100 tokens
            "response": "y" * 400,
            "model": "haiku",
            "route": "local+escalated",
            "escalated": True,
            "elapsed_ms": 1200,
        }
        row_id = log_query(result)
        db = get_db()
        row = db.execute("SELECT * FROM queries WHERE id = ?", (row_id,)).fetchone()
        assert row["cost_usd"] > 0
        assert row["escalated"] == 1

    def test_modality_stored(self):
        from db import log_query, get_db

        result = {
            "query": "test",
            "response": "ok",
            "model": "local",
            "route": "local",
        }
        row_id = log_query(result, input_modality="voice")
        db = get_db()
        row = db.execute("SELECT * FROM queries WHERE id = ?", (row_id,)).fetchone()
        assert row["input_modality"] == "voice"

    def test_command_executed_stored(self):
        from db import log_query, get_db

        result = {
            "query": "turn up volume",
            "response": "Done.",
            "model": "local",
            "route": "local",
            "command_executed": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 80%",
        }
        row_id = log_query(result)
        db = get_db()
        row = db.execute("SELECT * FROM queries WHERE id = ?", (row_id,)).fetchone()
        assert "wpctl" in row["command_executed"]


class TestConversationHistory:
    def test_empty_history(self):
        from db import get_conversation_history
        assert get_conversation_history() == []

    def test_history_from_logged_queries(self):
        from db import log_query, get_conversation_history

        for i in range(3):
            log_query({
                "query": f"question {i}",
                "response": f"answer {i}",
                "model": "qwen2.5:14b",
                "route": "local",
            })

        history = get_conversation_history(5)
        assert len(history) == 3
        assert history[0]["q"] == "question 0"
        assert history[2]["q"] == "question 2"

    def test_history_limit(self):
        from db import log_query, get_conversation_history

        for i in range(10):
            log_query({
                "query": f"q{i}",
                "response": f"a{i}",
                "model": "qwen2.5:14b",
                "route": "local",
            })

        history = get_conversation_history(3)
        assert len(history) == 3


class TestSearchHistory:
    def test_search_by_query(self):
        from db import log_query, search_history

        log_query({"query": "how to install docker", "response": "use pacman", "model": "local", "route": "local"})
        log_query({"query": "weather today", "response": "sunny", "model": "local", "route": "local"})

        results = search_history("docker")
        assert len(results) == 1
        assert "docker" in results[0]["query"]

    def test_search_by_response(self):
        from db import log_query, search_history

        log_query({"query": "install something", "response": "use pacman -S docker", "model": "local", "route": "local"})

        results = search_history("pacman")
        assert len(results) == 1

    def test_search_no_results(self):
        from db import search_history
        assert search_history("nonexistent_xyz") == []


class TestUsageStats:
    def test_empty_stats(self):
        from db import get_usage_stats
        stats = get_usage_stats("today")
        assert stats["total_queries"] == 0
        assert stats["total_cost"] == 0

    def test_stats_accumulate(self):
        from db import log_query, get_usage_stats

        for i in range(5):
            log_query({
                "query": f"test {i}",
                "response": f"ok {i}",
                "model": "qwen2.5:14b",
                "route": "local",
            })

        stats = get_usage_stats("today")
        assert stats["total_queries"] == 5
        assert stats["total_cost"] == 0  # all local

    def test_model_breakdown(self):
        from db import log_query, get_usage_stats

        log_query({"query": "a", "response": "b", "model": "qwen2.5:14b", "route": "local"})
        log_query({"query": "c", "response": "d", "model": "haiku", "route": "local+escalated"})

        stats = get_usage_stats("today")
        assert "qwen2.5:14b" in stats["model_breakdown"]
        assert "haiku" in stats["model_breakdown"]

    def test_period_filtering(self):
        from db import get_usage_stats
        # All periods should work without error
        for period in ("today", "week", "month", "all"):
            stats = get_usage_stats(period)
            assert "total_queries" in stats


class TestBudget:
    def test_no_budget_set(self):
        from db import check_budget
        budget = check_budget()
        assert budget["budget"] == 0
        assert not budget["exceeded"]

    def test_set_and_check_budget(self):
        from db import set_budget, check_budget
        set_budget(5.00, "month")
        budget = check_budget()
        assert budget["budget"] == 5.0
        assert budget["remaining"] == 5.0
        assert not budget["exceeded"]

    def test_budget_exceeded(self):
        from db import set_budget, check_budget, log_query

        set_budget(0.001, "month")

        # Log an expensive query
        log_query({
            "query": "x" * 4000,
            "response": "y" * 4000,
            "model": "opus",
            "route": "opus",
        })

        budget = check_budget()
        assert budget["exceeded"]


class TestSettings:
    def test_get_default(self):
        from db import get_setting
        assert get_setting("nonexistent", "default") == "default"

    def test_set_and_get(self):
        from db import set_setting, get_setting
        set_setting("test_key", "test_value")
        assert get_setting("test_key") == "test_value"

    def test_overwrite(self):
        from db import set_setting, get_setting
        set_setting("key", "v1")
        set_setting("key", "v2")
        assert get_setting("key") == "v2"


class TestWorkflowLog:
    def test_log_and_retrieve(self):
        from db import log_workflow_run, get_workflow_log

        run_id = log_workflow_run("test-wf", status="completed", steps_run=3, total_ms=1500)
        assert run_id > 0

        logs = get_workflow_log("test-wf")
        assert len(logs) == 1
        assert logs[0]["status"] == "completed"
        assert logs[0]["steps_run"] == 3

    def test_update_run(self):
        from db import log_workflow_run, update_workflow_run, get_workflow_log

        run_id = log_workflow_run("wf2", status="running")
        update_workflow_run(run_id, "completed", steps_run=5, total_ms=2000)

        logs = get_workflow_log("wf2")
        assert logs[0]["status"] == "completed"
        assert logs[0]["steps_run"] == 5


class TestRoutingFeedback:
    def test_feedback_stored(self):
        from db import log_query, update_routing_feedback, get_db

        row_id = log_query({
            "query": "test",
            "response": "ok",
            "model": "local",
            "route": "local",
        })
        update_routing_feedback(row_id, True)

        db = get_db()
        row = db.execute("SELECT routing_label FROM queries WHERE id = ?", (row_id,)).fetchone()
        assert row["routing_label"] == "correct"


class TestTrainingData:
    def test_get_training_data(self):
        from db import log_query, get_training_data

        log_query({"query": "q1", "response": "r1", "model": "local", "route": "local"})
        log_query({"query": "q2", "response": "r2", "model": "haiku", "route": "haiku+web"})

        data = get_training_data()
        assert len(data) == 2
        assert data[0]["route"] in ("local", "haiku+web")
