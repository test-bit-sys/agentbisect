"""
Adapter for Google Antigravity / Gemini CLI transcript logs (JSONL).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from agentbisect.adapters.base import BaseAdapter
from agentbisect.core.models import (
    AgentSession,
    AgentStep,
    SessionMetadata,
    StepType,
)


class AntigravityAdapter(BaseAdapter):
    name = "antigravity"

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        if not file_path.is_file():
            return False
        if file_path.suffix in (".jsonl", ".log") or "transcript" in file_path.name.lower():
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for _ in range(5):
                        line = f.readline()
                        if not line:
                            break
                        data = json.loads(line)
                        if "step_index" in data or "tool_calls" in data or "source" in data:
                            return True
            except Exception:
                pass
        return False

    @classmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        steps: List[AgentStep] = []
        session_id = file_path.stem
        created_at = None

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            step_counter = 1
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                if not created_at and "created_at" in data:
                    created_at = data["created_at"]

                # Extract tool calls or user input
                tool_calls = data.get("tool_calls") or []
                thought = data.get("thinking")
                content = data.get("content")
                step_type_raw = data.get("type", "")

                if tool_calls:
                    for tc in tool_calls:
                        name = tc.get("name") or tc.get("ToolName") or "tool"
                        args = tc.get("args") or tc.get("Arguments") or {}
                        files_affected = []
                        if isinstance(args, dict):
                            for key in ("Path", "path", "file", "FilePath"):
                                if key in args:
                                    files_affected.append(str(args[key]))

                        steps.append(
                            AgentStep(
                                step_number=step_counter,
                                step_id=f"step_{step_counter}",
                                timestamp=data.get("created_at") or "",
                                step_type=StepType.TOOL_CALL,
                                tool_name=name,
                                tool_args=args if isinstance(args, dict) else {},
                                agent_thought=thought,
                                files_affected=files_affected,
                            )
                        )
                        step_counter += 1
                elif step_type_raw == "USER_INPUT" and content:
                    steps.append(
                        AgentStep(
                            step_number=step_counter,
                            step_id=f"step_{step_counter}",
                            timestamp=data.get("created_at") or "",
                            step_type=StepType.PROMPT_TURN,
                            user_prompt=content if isinstance(content, str) else str(content),
                        )
                    )
                    step_counter += 1

        metadata = SessionMetadata(
            session_id=session_id,
            framework="antigravity",
            workspace_root=str(workspace_root.resolve()),
            created_at=created_at or "",
            total_steps=len(steps),
            source_transcript_path=str(file_path.resolve()),
        )

        return AgentSession(metadata=metadata, steps=steps)
