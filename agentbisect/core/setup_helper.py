"""
Universal Agent Setup Manager for AgentBisect:
Provides automated and one-click configurations for popular AI coding agents:
Cursor, Claude Desktop / Claude Code, Google Antigravity, Cline, Windsurf, and Aider.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class AgentSetupManager:
    """Automates integration with AI coding agents and MCP clients."""

    MCP_CONFIG_ENTRY = {
        "command": "agentbisect",
        "args": ["mcp"],
    }

    @staticmethod
    def get_skill_content() -> str:
        """Returns the AgentBisect Antigravity / Agent Skill definition."""
        return """---
name: agentbisect
description: "Autonomous trajectory debugging and binary-search regression locator for AI coding agents. Enables agents to locate the exact step that broke tests and rewind the workspace to a clean state."
---

# AgentBisect Skill

Use this skill whenever an agent coding session encounters test failures, compilation errors, or broken functionality after multi-step autonomous modifications.

## Core Capabilities
- `agentbisect_snapshot`: Create a shadow git checkpoint before making risky edits.
- `agentbisect_bisect`: Run binary search over steps to locate the exact step that broke the test suite.
- `agentbisect_rewind`: Rewind the filesystem to the last known good step and obtain recovery guidance.
- `agentbisect_get_diff`: View git diff introduced at any specific historical step.
- `agentbisect_status`: Inspect current session metadata.
"""

    @classmethod
    def setup_cursor(cls, workspace_root: Path, write: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """Generates or updates .cursor/mcp.json."""
        target_dir = workspace_root / ".cursor"
        target_file = target_dir / "mcp.json"

        data: Dict[str, Any] = {"mcpServers": {"agentbisect": cls.MCP_CONFIG_ENTRY}}

        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
                if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
                    existing["mcpServers"] = {}
                existing["mcpServers"]["agentbisect"] = cls.MCP_CONFIG_ENTRY
                data = existing
            except Exception:
                pass

        if write:
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True, f"Updated Cursor MCP configuration at {target_file}", data
        return False, f"Cursor configuration ready for {target_file}", data

    @classmethod
    def setup_antigravity(cls, workspace_root: Path, write: bool = False) -> Tuple[bool, str, str]:
        """Creates or links the Antigravity skill inside workspace or home directory."""
        target_file = workspace_root / ".gemini" / "skills" / "agentbisect" / "SKILL.md"
        content = cls.get_skill_content()

        if write:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            return True, f"Antigravity skill installed at {target_file}", content
        return False, f"Antigravity skill path: {target_file}", content

    @classmethod
    def setup_claude(cls, workspace_root: Path, write: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """Generates Claude Desktop configuration snippet."""
        if sys.platform == "win32":
            claude_config_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
        elif sys.platform == "darwin":
            claude_config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        else:
            claude_config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

        data: Dict[str, Any] = {"mcpServers": {"agentbisect": cls.MCP_CONFIG_ENTRY}}

        if claude_config_path.exists():
            try:
                with open(claude_config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict):
                    if "mcpServers" not in existing or not isinstance(existing["mcpServers"], dict):
                        existing["mcpServers"] = {}
                    existing["mcpServers"]["agentbisect"] = cls.MCP_CONFIG_ENTRY
                    data = existing
            except Exception:
                pass

        if write and claude_config_path.parent.exists():
            with open(claude_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True, f"Updated Claude Desktop config at {claude_config_path}", data

        return False, f"Claude Desktop config path: {claude_config_path}", data

    @classmethod
    def setup_cline(cls, workspace_root: Path, write: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """Generates Cline (VS Code extension) configuration."""
        target_dir = workspace_root / ".cline"
        target_file = target_dir / "mcp.json"
        data: Dict[str, Any] = {"mcpServers": {"agentbisect": cls.MCP_CONFIG_ENTRY}}

        if write:
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True, f"Updated Cline configuration at {target_file}", data
        return False, f"Cline config ready for {target_file}", data

    @classmethod
    def setup_windsurf(cls, workspace_root: Path, write: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        """Generates Windsurf MCP config snippet."""
        windsurf_config = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
        data: Dict[str, Any] = {"mcpServers": {"agentbisect": cls.MCP_CONFIG_ENTRY}}

        if write and windsurf_config.parent.exists():
            with open(windsurf_config, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True, f"Updated Windsurf config at {windsurf_config}", data
        return False, f"Windsurf config path: {windsurf_config}", data
