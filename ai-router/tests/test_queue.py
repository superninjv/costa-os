"""Tests for ai-router/queue.py — priority request queue."""

import json
import os
import time
import uuid
from unittest.mock import patch

import pytest


class TestPriority:
    def test_priority_ordering(self):
        from request_queue import Priority
        assert Priority.VOICE < Priority.INTERACTIVE
        assert Priority.INTERACTIVE < Priority.WORKFLOW
        assert Priority.WORKFLOW < Priority.BACKGROUND


class TestQueuedRequest:
    def test_creation(self):
        from request_queue import QueuedRequest, Priority
        req = QueuedRequest(query="test", priority=Priority.INTERACTIVE)
        assert req.query == "test"
        assert req.priority == Priority.INTERACTIVE
        assert req.id is not None

    def test_ordering(self):
        from request_queue import QueuedRequest, Priority
        voice = QueuedRequest(query="voice", priority=Priority.VOICE)
        bg = QueuedRequest(query="bg", priority=Priority.BACKGROUND)
        # Voice should sort before background (lower priority number)
        assert voice < bg


class TestRequestQueue:
    def test_enqueue_dequeue(self):
        from request_queue import RequestQueue, QueuedRequest, Priority
        q = RequestQueue()
        req = QueuedRequest(query="test", priority=Priority.INTERACTIVE)
        q.enqueue(req)
        assert q.size == 1
        result = q.dequeue()
        assert result.query == "test"
        assert q.size == 0

    def test_priority_ordering(self):
        from request_queue import RequestQueue, QueuedRequest, Priority
        q = RequestQueue()
        bg = QueuedRequest(query="background", priority=Priority.BACKGROUND)
        voice = QueuedRequest(query="voice", priority=Priority.VOICE)
        interactive = QueuedRequest(query="interactive", priority=Priority.INTERACTIVE)

        # Enqueue in wrong order
        q.enqueue(bg)
        q.enqueue(interactive)
        q.enqueue(voice)

        # Should dequeue in priority order
        first = q.dequeue()
        assert first.query == "voice"
        second = q.dequeue()
        assert second.query == "interactive"
        third = q.dequeue()
        assert third.query == "background"

    def test_cancel(self):
        from request_queue import RequestQueue, QueuedRequest, Priority
        q = RequestQueue()
        req = QueuedRequest(query="test", priority=Priority.INTERACTIVE)
        q.enqueue(req)
        assert q.cancel(req.id)
        assert q.size == 0

    def test_cancel_nonexistent(self):
        from request_queue import RequestQueue
        q = RequestQueue()
        assert not q.cancel("nonexistent-id")

    def test_empty_dequeue(self):
        from request_queue import RequestQueue
        q = RequestQueue()
        assert q.dequeue() is None

    def test_pending_list(self):
        from request_queue import RequestQueue, QueuedRequest, Priority
        q = RequestQueue()
        q.enqueue(QueuedRequest(query="a", priority=Priority.INTERACTIVE))
        q.enqueue(QueuedRequest(query="b", priority=Priority.WORKFLOW))
        pending = q.pending()
        assert len(pending) == 2


class TestClientFunctions:
    def test_is_daemon_running_no_socket(self):
        from request_queue import is_daemon_running
        assert not is_daemon_running()
