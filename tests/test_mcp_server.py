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



def test_mcp_notifications_ignored(temp_workspace):
    """
    Regression test: JSON-RPC 2.0 / MCP notifications (messages without 'id'
    or starting with notifications/*) must NOT receive a response from the server.
    """
    server = AgentBisectMCPServer(temp_workspace)

    # 1. notifications/initialized (lifecycle message sent by MCP clients)
    resp = server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None

    # 2. General notification without id
    resp2 = server.handle_request({"jsonrpc": "2.0", "method": "custom_notify", "params": {}})
    assert resp2 is None


def test_mcp_ping(temp_workspace):
    """
    MCP specification test: ping requests must be answered with empty result.
    """
    server = AgentBisectMCPServer(temp_workspace)
    resp = server.handle_request({"jsonrpc": "2.0", "id": 100, "method": "ping"})
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 100
    assert resp["result"] == {}


def test_mcp_run_stdio_stream(temp_workspace):
    """
    End-to-end test of stdio JSON-RPC stream with initialize, notification, and tools/list.
    """
    import io
    import json

    server = AgentBisectMCPServer(temp_workspace)

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    ]
    in_buf = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    out_buf = io.StringIO()

    server.run_stdio(in_stream=in_buf, out_stream=out_buf)

    lines = [json.loads(line) for line in out_buf.getvalue().strip().split("\n") if line.strip()]
    assert len(lines) == 3, f"Expected 3 responses (notification must be omitted), got {len(lines)}"

    # Line 1: initialize response
    assert lines[0]["id"] == 1
    assert "protocolVersion" in lines[0]["result"]

    # Line 2: ping response
    assert lines[1]["id"] == 2
    assert lines[1]["result"] == {}

    # Line 3: tools/list response
    assert lines[2]["id"] == 3
    assert len(lines[2]["result"]["tools"]) >= 5


def test_mcp_id_zero_and_string_id(temp_workspace):
    """
    MCP protocol test: ID 0 and string IDs are valid request IDs, NOT notifications.
    """
    server = AgentBisectMCPServer(temp_workspace)
    resp_zero = server.handle_request({"jsonrpc": "2.0", "id": 0, "method": "ping"})
    assert resp_zero is not None
    assert resp_zero["id"] == 0
    assert resp_zero["result"] == {}

    resp_str = server.handle_request({"jsonrpc": "2.0", "id": "req-xyz-99", "method": "ping"})
    assert resp_str is not None
    assert resp_str["id"] == "req-xyz-99"
    assert resp_str["result"] == {}


def test_mcp_malformed_json_and_invalid_request(temp_workspace):
    """
    MCP protocol test: Malformed JSON returns -32700, non-object JSON returns -32600.
    """
    import io
    import json

    server = AgentBisectMCPServer(temp_workspace)
    lines = [
        "{invalid json",
        json.dumps([1, 2, 3]),
        json.dumps("just a string"),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "non_existent_method"}),
    ]
    in_buf = io.StringIO("\n".join(lines) + "\n")
    out_buf = io.StringIO()

    server.run_stdio(in_stream=in_buf, out_stream=out_buf)
    responses = [json.loads(l) for l in out_buf.getvalue().strip().split("\n") if l.strip()]

    assert len(responses) == 4
    # 1. Parse error
    assert responses[0]["error"]["code"] == -32700
    # 2. Invalid Request (array)
    assert responses[1]["error"]["code"] == -32600
    # 3. Invalid Request (string)
    assert responses[2]["error"]["code"] == -32600
    # 4. Method not found
    assert responses[3]["error"]["code"] == -32601
