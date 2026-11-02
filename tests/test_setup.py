"""
Unit tests for AgentSetupManager and setup command.
"""

import tempfile
from pathlib import Path
from agentbisect.core.setup_helper import AgentSetupManager


def test_agent_setup_cursor():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        written, msg, data = AgentSetupManager.setup_cursor(ws, write=True)
        assert written is True
        target_file = ws / ".cursor" / "mcp.json"
        assert target_file.exists()
        assert "agentbisect" in data["mcpServers"]


def test_agent_setup_antigravity():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        written, msg, content = AgentSetupManager.setup_antigravity(ws, write=True)
        assert written is True
        target_file = ws / ".gemini" / "skills" / "agentbisect" / "SKILL.md"
        assert target_file.exists()
        assert "agentbisect_bisect" in content


def test_agent_setup_cline():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        written, msg, data = AgentSetupManager.setup_cline(ws, write=True)
        assert written is True
        target_file = ws / ".cline" / "mcp.json"
        assert target_file.exists()
        assert "agentbisect" in data["mcpServers"]
