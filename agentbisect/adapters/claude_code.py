"""
Adapter for Claude Code session transcripts and logs.
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
class ClaudeCodeAdapter(BaseAdapter):
    name = "claude_code"

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        if not file_path.is_file():
            return False
        if "claude" in file_path.name.lower() or ".claude" in str(file_path).lower():
            return True
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1024)
                if "claude" in head.lower() or "tool_use" in head:
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        steps: List[AgentStep] = []
        step_counter = 1
        created_at = None

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                event_type = data.get("type") or data.get("event")
                if event_type in ("tool_use", "tool_call"):
                    tool_name = data.get("name") or data.get("tool") or "tool"
                    tool_input = data.get("input") or data.get("args") or {}
                    files = []
                    if isinstance(tool_input, dict):
                        for k in ("file_path", "path", "file"):
                            if k in tool_input:
                                files.append(str(tool_input[k]))

                    steps.append(
                        AgentStep(
                            step_number=step_counter,
                            step_id=f"claude_step_{step_counter}",
                            timestamp=data.get("timestamp") or "",
                            step_type=StepType.TOOL_CALL,
                            tool_name=tool_name,
                            tool_args=tool_input if isinstance(tool_input, dict) else {},
                            files_affected=files,
                        )
                    )
                    step_counter += 1
                elif event_type == "user_message":
                    steps.append(
                        AgentStep(
                            step_number=step_counter,
                            step_id=f"claude_step_{step_counter}",
                            timestamp=data.get("timestamp") or "",
                            step_type=StepType.PROMPT_TURN,
                            user_prompt=str(data.get("message") or data.get("text") or ""),
                        )
                    )
                    step_counter += 1

        metadata = SessionMetadata(
            session_id=file_path.stem,
            framework="claude_code",
            workspace_root=str(workspace_root.resolve()),
            created_at=created_at or "",
            total_steps=len(steps),
            source_transcript_path=str(file_path.resolve()),
        )
        return AgentSession(metadata=metadata, steps=steps)
