"""Tests for ai-router/tools.py — Claude tool definitions and handlers."""

import json
import pytest


class TestToolDefinitions:
    def test_all_tools_have_names(self):
        from tools import ALL_TOOLS
        for tool in ALL_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_all_tools_have_handlers(self):
        from tools import ALL_TOOLS, HANDLERS
        for tool in ALL_TOOLS:
            assert tool["name"] in HANDLERS, f"No handler for tool: {tool['name']}"

    def test_tool_count(self):
        from tools import ALL_TOOLS, SYSTEM_QUERY_TOOLS, SAFE_ACTION_TOOLS, ASK_FIRST_TOOLS
        assert len(ALL_TOOLS) == len(SYSTEM_QUERY_TOOLS) + len(SAFE_ACTION_TOOLS) + len(ASK_FIRST_TOOLS)
        assert len(ALL_TOOLS) >= 25  # at least 25 tools

    def test_no_duplicate_names(self):
        from tools import ALL_TOOLS
        names = [t["name"] for t in ALL_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"

    def test_input_schemas_valid(self):
        from tools import ALL_TOOLS
        for tool in ALL_TOOLS:
            schema = tool["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema

    def test_safety_categories(self):
        from tools import SAFE_TOOL_NAMES, ASK_FIRST_TOOL_NAMES
        # These should not overlap
        assert not SAFE_TOOL_NAMES & ASK_FIRST_TOOL_NAMES
        # run_command must be ask-first
        assert "run_command" in ASK_FIRST_TOOL_NAMES
        assert "install_package" in ASK_FIRST_TOOL_NAMES
        assert "manage_service" in ASK_FIRST_TOOL_NAMES
        # Read-only tools must be safe
        assert "get_system_info" in SAFE_TOOL_NAMES
        assert "get_gpu_status" in SAFE_TOOL_NAMES


class TestToolRouteSelection:
    def test_local_gets_no_tools(self):
        from tools import get_tools_for_route
        assert get_tools_for_route("local") == []
        assert get_tools_for_route("local+weather") == []
        assert get_tools_for_route("local+escalated") == []

    def test_haiku_gets_safe_tools(self):
        from tools import get_tools_for_route, ASK_FIRST_TOOLS
        haiku_tools = get_tools_for_route("haiku")
        haiku_names = {t["name"] for t in haiku_tools}
        # Haiku should not get ask-first tools
        for t in ASK_FIRST_TOOLS:
            assert t["name"] not in haiku_names

    def test_sonnet_gets_all_tools(self):
        from tools import get_tools_for_route, ALL_TOOLS
        sonnet_tools = get_tools_for_route("sonnet")
        assert len(sonnet_tools) == len(ALL_TOOLS)

    def test_opus_gets_all_tools(self):
        from tools import get_tools_for_route, ALL_TOOLS
        opus_tools = get_tools_for_route("opus")
        assert len(opus_tools) == len(ALL_TOOLS)


class TestToolExecution:
    def test_execute_unknown_tool(self):
        from tools import execute_tool
        result = execute_tool("nonexistent_tool", {})
        assert "Unknown tool" in result

    def test_get_system_info(self):
        from tools import execute_tool
        result = execute_tool("get_system_info", {})
        assert "Hostname" in result or "Kernel" in result

    def test_get_disk_usage(self):
        from tools import execute_tool
        result = execute_tool("get_disk_usage", {})
        # Should have some filesystem output
        assert len(result) > 10

    def test_get_installed_packages_search(self):
        from tools import execute_tool
        result = execute_tool("get_installed_packages", {"search": "python"})
        assert "python" in result.lower() or "No" in result

    def test_get_installed_packages_specific(self):
        from tools import execute_tool
        result = execute_tool("get_installed_packages", {"package": "coreutils"})
        assert "coreutils" in result.lower() or "not installed" in result.lower()

    def test_read_file_exists(self):
        from tools import execute_tool
        result = execute_tool("read_file", {"path": "/etc/hostname"})
        assert len(result) > 0

    def test_read_file_missing(self):
        from tools import execute_tool
        result = execute_tool("read_file", {"path": "/nonexistent/file"})
        assert "not found" in result.lower()

    def test_send_notification_format(self):
        from tools import execute_tool
        # This will try to send a real notification — just verify it doesn't crash
        result = execute_tool("send_notification", {"title": "Test", "body": "test body"})
        assert "sent" in result.lower() or result == "(no output)"

    def test_get_monitors(self):
        from tools import execute_tool
        result = execute_tool("get_monitors", {})
        # On a system with Hyprland, should return monitor info
        # On CI, might say "not running"
        assert len(result) > 0


class TestDangerousCommandBlocking:
    def test_rm_rf_blocked(self):
        from tools import execute_tool
        result = execute_tool("run_command", {"command": "rm -rf /"})
        assert "BLOCKED" in result

    def test_dd_blocked(self):
        from tools import execute_tool
        result = execute_tool("run_command", {"command": "dd if=/dev/zero of=/dev/sda"})
        assert "BLOCKED" in result

    def test_shutdown_blocked(self):
        from tools import execute_tool
        result = execute_tool("run_command", {"command": "shutdown now"})
        assert "BLOCKED" in result

    def test_safe_command_allowed(self):
        from tools import execute_tool
        result = execute_tool("run_command", {"command": "echo hello"})
        assert "BLOCKED" not in result

    def test_get_tool_names(self):
        from tools import get_tool_names
        names = get_tool_names()
        assert "get_system_info" in names
        assert "run_command" in names
        assert len(names) >= 25
