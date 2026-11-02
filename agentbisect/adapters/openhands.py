"""
Adapter for OpenHands (formerly OpenDevin) and SWE-bench trajectory logs.
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
class OpenHandsAdapter(BaseAdapter):
    name = "openhands"

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        if not file_path.is_file():
            return False
        if "openhands" in file_path.name.lower():
            return True
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1024)
                if ('"action":' in head or '"action_type":' in head) and ('"args":' in head or '"parameters":' in head):
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        steps: List[AgentStep] = []
        step_counter = 1

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                action = data.get("action") or data.get("action_type") or "action"
                args = data.get("args") or data.get("parameters") or {}
                thought = data.get("thought") or data.get("observation")
                files_affected = []

                if isinstance(args, dict):
                    for k in ("path", "file_path", "filename", "file"):
                        if k in args:
                            files_affected.append(str(args[k]))

                step_type = StepType.TOOL_CALL
                if action in ("run", "execute_command"):
                    step_type = StepType.COMMAND
                elif action in ("edit", "write", "file_editor"):
                    step_type = StepType.FILE_EDIT

                steps.append(
                    AgentStep(
                        step_number=step_counter,
                        step_id=f"openhands_step_{step_counter}",
                        timestamp=data.get("timestamp") or "",
                        step_type=step_type,
                        tool_name=action,
                        tool_args=args if isinstance(args, dict) else {},
                        agent_thought=thought,
                        files_affected=files_affected,
                    )
                )
                step_counter += 1

        meta = SessionMetadata(
            session_id=file_path.stem,
            framework="openhands",
            workspace_root=str(workspace_root.resolve()),
            total_steps=len(steps),
            source_transcript_path=str(file_path.resolve()),
        )
        return AgentSession(metadata=meta, steps=steps)
