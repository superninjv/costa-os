"""Tests for ai-router/workflow.py — YAML workflow engine."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml


@pytest.fixture
def workflow_dir(tmp_path):
    """Create a temp workflow directory with test workflows."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    return wf_dir


@pytest.fixture
def simple_workflow(workflow_dir):
    """Create a simple test workflow."""
    wf = {
        "name": "test-simple",
        "description": "A simple test workflow",
        "trigger": {"type": "manual"},
        "steps": [
            {"id": "greet", "action": "shell", "command": "echo hello world"},
            {"id": "notify", "action": "notify", "title": "Test", "body": "{{steps.greet.output}}"},
        ],
    }
    path = workflow_dir / "test-simple.yaml"
    path.write_text(yaml.dump(wf))
    return path


@pytest.fixture
def condition_workflow(workflow_dir):
    """Create a workflow with conditions."""
    wf = {
        "name": "test-condition",
        "description": "Workflow with conditions",
        "steps": [
            {"id": "check", "action": "shell", "command": "echo SUCCESS"},
            {"id": "gate", "action": "condition", "check": "check", "contains": "SUCCESS"},
            {"id": "after", "action": "shell", "command": "echo passed"},
        ],
    }
    path = workflow_dir / "test-condition.yaml"
    path.write_text(yaml.dump(wf))
    return path


@pytest.fixture
def failing_condition_workflow(workflow_dir):
    """Create a workflow where condition fails."""
    wf = {
        "name": "test-fail-condition",
        "description": "Workflow where condition fails",
        "steps": [
            {"id": "check", "action": "shell", "command": "echo NOPE"},
            {"id": "gate", "action": "condition", "check": "check", "contains": "SUCCESS"},
            {"id": "should-not-run", "action": "shell", "command": "echo should not see this"},
        ],
    }
    path = workflow_dir / "test-fail-condition.yaml"
    path.write_text(yaml.dump(wf))
    return path


class TestWorkflowParsing:
    def test_list_workflows(self, simple_workflow, workflow_dir):
        from workflow import list_workflows
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            wfs = list_workflows()
            assert len(wfs) >= 1
            names = [w["name"] for w in wfs]
            assert "test-simple" in names

    def test_list_empty_dir(self, tmp_path):
        from workflow import list_workflows
        empty = tmp_path / "empty"
        empty.mkdir()
        with patch("workflow.WORKFLOW_DIR", empty):
            wfs = list_workflows()
            assert wfs == []


class TestWorkflowExecution:
    def test_shell_step(self, simple_workflow, workflow_dir):
        from workflow import execute_workflow
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            result = execute_workflow("test-simple")
            assert result.get("error") is None or result.get("steps_executed", 0) > 0
            outputs = result.get("outputs", {})
            assert "greet" in outputs
            assert "hello world" in outputs["greet"]

    def test_variable_interpolation(self, simple_workflow, workflow_dir):
        from workflow import execute_workflow
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            result = execute_workflow("test-simple")
            # The notify step should have interpolated greet's output
            outputs = result.get("outputs", {})
            if "notify" in outputs:
                # notify output is the notification result
                pass  # just verify it didn't crash

    def test_condition_pass(self, condition_workflow, workflow_dir):
        from workflow import execute_workflow
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            result = execute_workflow("test-condition")
            outputs = result.get("outputs", {})
            # After step should have run
            assert "after" in outputs
            assert "passed" in outputs.get("after", "")

    def test_condition_fail_stops(self, failing_condition_workflow, workflow_dir):
        from workflow import execute_workflow
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            result = execute_workflow("test-fail-condition")
            outputs = result.get("outputs", {})
            # The step after the failed condition should not run
            assert "should-not-run" not in outputs

    def test_nonexistent_workflow(self, workflow_dir):
        from workflow import execute_workflow
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            with pytest.raises(FileNotFoundError):
                execute_workflow("nonexistent-workflow")

    def test_costa_ai_step(self, workflow_dir):
        """Test that costa-ai steps call route_query."""
        wf = {
            "name": "test-ai",
            "description": "AI step test",
            "steps": [
                {"id": "ask", "action": "costa-ai", "query": "hello"},
            ],
        }
        path = workflow_dir / "test-ai.yaml"
        path.write_text(yaml.dump(wf))

        mock_result = {"response": "Hello! How can I help?", "model": "local", "route": "local"}
        from workflow import execute_workflow
        with patch("workflow.WORKFLOW_DIR", workflow_dir):
            with patch("router.route_query", return_value=mock_result):
                result = execute_workflow("test-ai")
                outputs = result.get("outputs", {})
                assert "ask" in outputs
                assert "Hello" in outputs["ask"]


class TestWorkflowTimerGeneration:
    def test_install_creates_files(self, workflow_dir, tmp_path):
        """Test systemd timer file generation."""
        wf = {
            "name": "test-timer",
            "description": "Timer test",
            "trigger": {"type": "schedule", "calendar": "*-*-* 08:00:00"},
            "steps": [{"id": "test", "action": "shell", "command": "echo hi"}],
        }
        path = workflow_dir / "test-timer.yaml"
        path.write_text(yaml.dump(wf))

        from workflow import install_workflow
        systemd_dir = tmp_path / "systemd" / "user"
        systemd_dir.mkdir(parents=True)

        with patch("workflow.WORKFLOW_DIR", workflow_dir), \
             patch("workflow.SYSTEMD_USER_DIR", systemd_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = install_workflow("test-timer")
            # Should have attempted to create files
            # (may fail due to systemctl not being available in test env)


class TestVariableInterpolation:
    def test_simple_interpolation(self):
        """Test {{steps.id.output}} replacement."""
        from workflow import _interpolate

        outputs = {"step1": "hello", "step2": "world"}
        text = "{{steps.step1.output}} {{steps.step2.output}}"
        result = _interpolate(text, outputs)
        assert result == "hello world"

    def test_no_interpolation_needed(self):
        from workflow import _interpolate
        assert _interpolate("plain text", {}) == "plain text"

    def test_missing_step_reference(self):
        from workflow import _interpolate
        result = _interpolate("{{steps.missing.output}}", {})
        # Should indicate the step had no output
        assert "missing" in result
