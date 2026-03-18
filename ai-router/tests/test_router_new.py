"""Tests for router.py — new features: timing, cancel, ML integration, tool_use."""

import json
import os
import signal
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestSelectRoute:
    """Test routing logic including ML fallback."""

    def test_regex_patterns_work(self):
        from router import select_route
        # These should match regex patterns
        assert select_route("what's the weather") == "local+weather"
        assert select_route("latest news today") == "haiku+web"
        assert select_route("find that python file") == "file_search"

    def test_default_is_local(self):
        from router import select_route
        assert select_route("what is linux") == "local"
        assert select_route("hello") == "local"

    def test_ml_router_graceful_fallback(self):
        """ML router should gracefully fail when not trained."""
        from router import select_route
        # Should not raise even if ml_router.pt doesn't exist
        route = select_route("install firefox")
        assert route in ("local", "sonnet", "haiku+web", "file_search",
                          "project_switch", "opus", "local+weather")


class TestTimingBreakdown:
    """Test that route_query returns timing data."""

    @patch("router.query_ollama", return_value="test response")
    @patch("router.gather_context", return_value="")
    @patch("router.select_knowledge", return_value="")
    @patch("router.get_conversation_history", return_value=[])
    @patch("router.is_window_command", return_value=False)
    @patch("router.is_keybind_query", return_value=False)
    def test_timing_fields_present(self, *mocks):
        from router import route_query
        result = route_query("what is linux", gather_context_flag=False)

        assert "elapsed_ms" in result
        assert "total_ms" in result
        assert result["elapsed_ms"] >= 0
        assert result["total_ms"] >= 0

    @patch("router.query_ollama", return_value="test response")
    @patch("router.gather_context", return_value="some context")
    @patch("router.select_knowledge", return_value="some knowledge")
    @patch("router.get_conversation_history", return_value=[])
    @patch("router.is_window_command", return_value=False)
    @patch("router.is_keybind_query", return_value=False)
    def test_context_and_knowledge_timing(self, *mocks):
        from router import route_query
        result = route_query("what packages for python")

        assert "context_ms" in result
        assert "knowledge_ms" in result
        assert "model_ms" in result

    @patch("router.query_ollama", return_value="test response")
    @patch("router.gather_context", return_value="")
    @patch("router.select_knowledge", return_value="")
    @patch("router.get_conversation_history", return_value=[])
    @patch("router.is_window_command", return_value=False)
    @patch("router.is_keybind_query", return_value=False)
    def test_query_included_in_result(self, *mocks):
        from router import route_query
        result = route_query("hello world")
        assert result.get("query") == "hello world"


class TestCancelMechanism:
    def test_pid_file_created_and_cleaned(self):
        """PID file should be created during query and cleaned up after."""
        from router import PID_FILE

        @patch("router.query_ollama", return_value="response")
        @patch("router.gather_context", return_value="")
        @patch("router.select_knowledge", return_value="")
        @patch("router.get_conversation_history", return_value=[])
        @patch("router.is_window_command", return_value=False)
        @patch("router.is_keybind_query", return_value=False)
        def run_query(*mocks):
            from router import route_query
            return route_query("test")

        result = run_query()
        # PID file should be cleaned up after query
        assert not PID_FILE.exists()

    def test_cancelled_result(self):
        from router import _cancelled_result
        result = _cancelled_result("test query", time.time(), "text")
        assert result["response"] == "(Cancelled)"
        assert result["route"] == "cancelled"

    def test_stop_running_query_no_pid(self):
        from router import stop_running_query, PID_FILE
        PID_FILE.unlink(missing_ok=True)
        assert not stop_running_query()


class TestDbLogging:
    """Test that queries get logged to the database."""

    @patch("router.query_ollama", return_value="test response")
    @patch("router.gather_context", return_value="")
    @patch("router.select_knowledge", return_value="")
    @patch("router.get_conversation_history", return_value=[])
    @patch("router.is_window_command", return_value=False)
    @patch("router.is_keybind_query", return_value=False)
    def test_query_logged(self, *mocks):
        # Use a temp db
        import db
        _orig_path = db.DB_PATH
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db.DB_PATH = Path(f.name)
            db._connection = None

        try:
            from router import route_query
            route_query("test logging query")

            rows = db.get_history(5)
            assert len(rows) >= 1
            assert any("test logging" in (r.get("query") or "") for r in rows)
        finally:
            db.close_db()
            db.DB_PATH = _orig_path
            db._connection = None
            os.unlink(f.name)


class TestQueryClaude:
    """Test the tool_use-enabled query_claude function."""

    def test_no_api_key_returns_empty(self):
        from router import query_claude
        with patch("router._get_anthropic_key", return_value=None):
            result = query_claude("test", model="haiku")
            assert result == ""

    @patch("router._get_anthropic_key", return_value="test-key")
    def test_budget_exceeded_returns_empty(self, mock_key):
        from router import query_claude
        import db
        with patch.object(db, "check_budget", return_value={"exceeded": True}):
            result = query_claude("test", model="haiku")
            assert result == ""


class TestConversationHistory:
    """Test DB-backed conversation history."""

    def test_fallback_to_file(self):
        """Should fall back to file when db fails."""
        from router import get_conversation_history
        # With no db and no file, should return empty
        history = get_conversation_history()
        assert isinstance(history, list)

    def test_format_conversation_context(self):
        from router import format_conversation_context
        history = [
            {"q": "hello", "a": "hi there", "m": "local", "t": "2024-01-01"},
            {"q": "what time", "a": "3pm", "m": "local", "t": "2024-01-01"},
        ]
        context = format_conversation_context(history)
        assert "hello" in context
        assert "hi there" in context
        assert "RECENT CONVERSATION" in context

    def test_empty_history_returns_empty(self):
        from router import format_conversation_context
        assert format_conversation_context([]) == ""
