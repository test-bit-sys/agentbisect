"""
Adapter for Cline and Roo-Code task sessions.
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
class ClineAdapter(BaseAdapter):
    name = "cline"

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        if not file_path.is_file():
            return False
        if "cline" in file_path.name.lower() or "ui_messages" in file_path.name.lower():
            return True
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1024)
                if '"say":' in head or '"ask":' in head or 'replace_in_file' in head:
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        steps: List[AgentStep] = []
        step_counter = 1

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                raw_data = json.load(f)
        except Exception:
            raw_data = []

        if isinstance(raw_data, list):
            for msg in raw_data:
                say = msg.get("say")
                text = msg.get("text") or ""
                files_affected = []

                if say in ("command", "command_output"):
                    steps.append(
                        AgentStep(
                            step_number=step_counter,
                            step_id=f"cline_step_{step_counter}",
                            timestamp=str(msg.get("ts", "")),
                            step_type=StepType.COMMAND,
                            tool_name="command",
                            tool_args={"command": text[:60]},
                        )
                    )
                    step_counter += 1
                elif say in ("tool", "browser_action"):
                    steps.append(
                        AgentStep(
                            step_number=step_counter,
                            step_id=f"cline_step_{step_counter}",
                            timestamp=str(msg.get("ts", "")),
                            step_type=StepType.TOOL_CALL,
                            tool_name=say,
                            agent_thought=text,
                        )
                    )
                    step_counter += 1
                elif say == "user_feedback":
                    steps.append(
                        AgentStep(
                            step_number=step_counter,
                            step_id=f"cline_step_{step_counter}",
                            timestamp=str(msg.get("ts", "")),
                            step_type=StepType.PROMPT_TURN,
                            user_prompt=text,
                        )
                    )
                    step_counter += 1

        meta = SessionMetadata(
            session_id=file_path.stem,
            framework="cline",
            workspace_root=str(workspace_root.resolve()),
            total_steps=len(steps),
            source_transcript_path=str(file_path.resolve()),
        )
        return AgentSession(metadata=meta, steps=steps)
