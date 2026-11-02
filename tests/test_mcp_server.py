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
