"""
Base Evaluator interface for AgentBisect:
Defines the protocol for verifying whether a workspace state PASSES or FAILS.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from agentbisect.core.models import BisectStatus, BisectStepResult


class BaseEvaluator(ABC):
    """Abstract base class for all evaluation strategies."""

    name: str = "base_evaluator"

    @abstractmethod
    def evaluate(
        self,
        step_number: int,
        commit_hash: str,
        workspace_root: Path,
    ) -> BisectStepResult:
        """Executes verification at the given step and returns a BisectStepResult."""
        pass
