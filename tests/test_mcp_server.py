"""
Unit tests for AgentBisect MCP Server tools.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.mcp.server import AgentBisectMCPServer


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_mcp_tool_definitions(temp_workspace):
    server = AgentBisectMCPServer(temp_workspace)
    tools = server.get_tool_definitions()
    tool_names = [t["name"] for t in tools]

    assert "agentbisect_snapshot" in tool_names
    assert "agentbisect_bisect" in tool_names
    assert "agentbisect_rewind" in tool_names
    assert "agentbisect_get_diff" in tool_names
    assert "agentbisect_status" in tool_names


def test_mcp_snapshot_and_status(temp_workspace):
    server = AgentBisectMCPServer(temp_workspace)

    # Call snapshot
    res_snap = server.handle_call_tool("agentbisect_snapshot", {"summary": "Initial setup"})
    assert "Snapshot created" in res_snap["content"][0]["text"]

    # Call status
    res_status = server.handle_call_tool("agentbisect_status", {})
    assert "total_steps" in res_status["content"][0]["text"]


def test_mcp_validation_and_error_handling(temp_workspace):
    server = AgentBisectMCPServer(temp_workspace)

    # Empty test_command in bisect
    res_empty_cmd = server.handle_call_tool("agentbisect_bisect", {"test_command": ""})
    assert res_empty_cmd.get("isError") is True
    assert "required and cannot be empty" in res_empty_cmd["content"][0]["text"]

    # Missing target_step in rewind
    res_missing_step = server.handle_call_tool("agentbisect_rewind", {})
    assert res_missing_step.get("isError") is True
    assert "target_step" in res_missing_step["content"][0]["text"]

    # Invalid non-integer step in get_diff
    res_invalid_diff = server.handle_call_tool("agentbisect_get_diff", {"step_number": "invalid"})
    assert res_invalid_diff.get("isError") is True
    assert "integer" in res_invalid_diff["content"][0]["text"]

    # Unknown tool
    res_unknown = server.handle_call_tool("unknown_tool", {})
    assert res_unknown.get("isError") is True
    assert "Unknown tool" in res_unknown["content"][0]["text"]

