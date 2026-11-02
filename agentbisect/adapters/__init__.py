"""
Adapters module for AgentBisect.
Dynamically discovers and loads all registered adapters.
"""

from __future__ import annotations

from pathlib import Path
from agentbisect.adapters.base import BaseAdapter
from agentbisect.adapters.registry import (
    register_adapter,
    detect_adapter,
    list_registered_adapters,
    get_adapter,
)
from agentbisect.adapters.antigravity import AntigravityAdapter
from agentbisect.adapters.claude_code import ClaudeCodeAdapter
from agentbisect.adapters.generic_json import GenericJsonAdapter
from agentbisect.adapters.openhands import OpenHandsAdapter
from agentbisect.adapters.cline import ClineAdapter
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.models import AgentSession


def load_session(path: Path | str, workspace_root: Path | str) -> AgentSession:
    """
    Automatically detects the appropriate adapter for the given transcript file and parses it.
    """
    p = Path(path).resolve()
    ws = Path(workspace_root).resolve()

    if not p.exists():
        raise FileNotFoundError(f"Transcript file not found: {p}")

    adapter_cls = detect_adapter(p)
    if adapter_cls:
        return adapter_cls.parse(p, ws)

    # Fallback to generic JSON adapter
    return GenericJsonAdapter.parse(p, ws)


__all__ = [
    "BaseAdapter",
    "register_adapter",
    "detect_adapter",
    "list_registered_adapters",
    "get_adapter",
    "AntigravityAdapter",
    "ClaudeCodeAdapter",
    "GenericJsonAdapter",
    "OpenHandsAdapter",
    "ClineAdapter",
    "LiveRecorder",
    "load_session",
]
