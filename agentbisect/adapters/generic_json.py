"""
Generic JSON/JSONL trajectory adapter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from agentbisect.adapters.base import BaseAdapter
from agentbisect.adapters.registry import register_adapter
from agentbisect.core.models import (
    AgentSession,
    AgentStep,
    SessionMetadata,
    StepType,
)


@register_adapter
class GenericJsonAdapter(BaseAdapter):
    name = "generic_json"

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        if file_path.is_file() and file_path.suffix in (".json", ".jsonl"):
            return True
        return False

    @classmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        # Check if it's already an AgentSession JSON
        if file_path.suffix == ".json":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "metadata" in data and "steps" in data:
                    return AgentSession.model_validate(data)
                elif isinstance(data, list):
                    # List of step objects
                    steps = [AgentStep.model_validate(s) for s in data]
                    meta = SessionMetadata(
                        session_id=file_path.stem,
                        framework="generic",
                        workspace_root=str(workspace_root.resolve()),
                        total_steps=len(steps),
                        source_transcript_path=str(file_path.resolve()),
                    )
                    return AgentSession(metadata=meta, steps=steps)
            except Exception:
                pass

        # Treat as JSONL
        steps: List[AgentStep] = []
        step_counter = 1
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    if isinstance(raw, dict):
                        step = AgentStep(
                            step_number=raw.get("step_number", step_counter),
                            step_id=raw.get("step_id", f"step_{step_counter}"),
                            timestamp=raw.get("timestamp", ""),
                            step_type=raw.get("step_type", StepType.TOOL_CALL),
                            tool_name=raw.get("tool_name"),
                            tool_args=raw.get("tool_args"),
                            tool_result=raw.get("tool_result"),
                            agent_thought=raw.get("agent_thought"),
                            user_prompt=raw.get("user_prompt"),
                            files_affected=raw.get("files_affected", []),
                            commit_hash=raw.get("commit_hash"),
                            diff=raw.get("diff"),
                        )
                        steps.append(step)
                        step_counter += 1
                except Exception:
                    continue

        meta = SessionMetadata(
            session_id=file_path.stem,
            framework="generic",
            workspace_root=str(workspace_root.resolve()),
            total_steps=len(steps),
            source_transcript_path=str(file_path.resolve()),
        )
        return AgentSession(metadata=meta, steps=steps)
