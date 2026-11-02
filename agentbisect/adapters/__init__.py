"""
Adapters module for AgentBisect.
"""

from __future__ import annotations

from pathlib import Path
from agentbisect.adapters.base import BaseAdapter
from agentbisect.adapters.antigravity import AntigravityAdapter
from agentbisect.adapters.claude_code import ClaudeCodeAdapter
from agentbisect.adapters.generic_json import GenericJsonAdapter
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.models import AgentSession

ADAPTERS = [
    AntigravityAdapter,
    ClaudeCodeAdapter,
    GenericJsonAdapter,
]


def load_session(path: Path | str, workspace_root: Path | str) -> AgentSession:
    """
    Automatically detects the adapter for the given transcript file and parses it.
    """
    p = Path(path).resolve()
    ws = Path(workspace_root).resolve()

    if not p.exists():
        raise FileNotFoundError(f"Transcript file not found: {p}")

    for adapter_cls in ADAPTERS:
        if adapter_cls.can_handle(p):
            return adapter_cls.parse(p, ws)

    # Fallback to generic
    return GenericJsonAdapter.parse(p, ws)


__all__ = [
    "BaseAdapter",
    "AntigravityAdapter",
    "ClaudeCodeAdapter",
    "GenericJsonAdapter",
    "LiveRecorder",
    "load_session",
]
