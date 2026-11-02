"""
Live recorder for actively recording agent actions and workspace states step-by-step.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from agentbisect.core.models import (
    AgentSession,
    AgentStep,
    SessionMetadata,
    StepType,
)
from agentbisect.core.shadow_ledger import ShadowLedger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveRecorder:
    """
    Flight data recorder for agent sessions.
    Automatically captures snapshots into the ShadowLedger after every tool call or action.
    """

    def __init__(
        self,
        workspace_root: Path | str,
        session_id: Optional[str] = None,
        framework: str = "generic",
    ):
        self.workspace_root = Path(workspace_root).resolve()
        now_tag = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        self.session_id = session_id or f"session_{now_tag}_{uuid.uuid4().hex[:6]}"
        self.ledger = ShadowLedger(self.workspace_root)

        self.storage_dir = self.workspace_root / ".agentbisect"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.storage_dir / "current_session.json"

        # Initialize session
        self.session = AgentSession(
            metadata=SessionMetadata(
                session_id=self.session_id,
                framework=framework,
                workspace_root=str(self.workspace_root),
                created_at=_now_iso(),
                total_steps=0,
            ),
            steps=[],
        )

        # Baseline snapshot
        self.baseline_commit = self.ledger.create_initial_baseline()
        self.session.metadata.baseline_commit = self.baseline_commit
        self._save()

    def _save(self) -> None:
        self.session.metadata.total_steps = len(self.session.steps)
        self.session.save_json(self.session_file)

    def record_step(
        self,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        tool_result: Optional[str] = None,
        agent_thought: Optional[str] = None,
        user_prompt: Optional[str] = None,
        files_affected: Optional[List[str]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        duration_ms: Optional[int] = None,
        step_type: StepType = StepType.TOOL_CALL,
    ) -> AgentStep:
        """
        Records an agent action, creates a shadow git snapshot, and persists the step.
        """
        step_number = len(self.session.steps) + 1
        step_id = f"step_{step_number}_{uuid.uuid4().hex[:4]}"

        # Auto-detect modified files if none provided
        auto_files = files_affected or []
        if not auto_files and tool_args and isinstance(tool_args, dict):
            for k in ("path", "Path", "file_path", "FilePath", "file"):
                if k in tool_args:
                    auto_files.append(str(tool_args[k]))

        # Snapshot in shadow ledger
        summary_text = tool_name or (user_prompt[:30] if user_prompt else f"Step {step_number}")
        commit_hash = self.ledger.snapshot_step(
            step_number=step_number,
            summary=summary_text,
            files=auto_files if auto_files else None,
        )

        step = AgentStep(
            step_number=step_number,
            step_id=step_id,
            timestamp=_now_iso(),
            step_type=step_type,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            agent_thought=agent_thought,
            user_prompt=user_prompt,
            files_affected=auto_files,
            commit_hash=commit_hash,
            token_usage=token_usage,
            duration_ms=duration_ms,
        )

        self.session.steps.append(step)
        self._save()
        return step
