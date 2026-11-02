"""
Base adapter interface for importing agent transcripts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from agentbisect.core.models import AgentSession


class BaseAdapter(ABC):
    """Abstract base class for all transcript adapters."""

    name: str = "base"

    @classmethod
    @abstractmethod
    def can_handle(cls, file_path: Path) -> bool:
        """Determines if this adapter can parse the given transcript file."""
        pass

    @classmethod
    @abstractmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        """Parses the transcript file into an AgentSession model."""
        pass
