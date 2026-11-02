"""
Data models and schemas for AgentBisect.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StepType(str, Enum):
    TOOL_CALL = "tool_call"
    FILE_EDIT = "file_edit"
    COMMAND = "command"
    PROMPT_TURN = "prompt_turn"
    MANUAL = "manual"
    SNAPSHOT = "snapshot"


class BisectStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    UNTESTED = "UNTESTED"
    ERROR = "ERROR"
    INCONCLUSIVE = "INCONCLUSIVE"


class RegressionClassification(str, Enum):
    CONFIRMED = "CONFIRMED_FIRST_REGRESSION"
    PROBABLE = "PROBABLE_FIRST_REGRESSION"
    EARLIEST_OBSERVED = "EARLIEST_OBSERVED_FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"
    NO_REGRESSION = "NO_REGRESSION"
    BROKEN_BASELINE = "BROKEN_BASELINE"


class AgentStep(BaseModel):
    """Represents a single discrete step executed by an AI agent."""
    step_number: int = Field(description="1-based step index in the session trajectory")
    step_id: str = Field(description="Unique ID for this step")
    timestamp: str = Field(default_factory=utc_now_iso)
    step_type: StepType = Field(default=StepType.TOOL_CALL)
    tool_name: Optional[str] = Field(default=None, description="Name of tool invoked, e.g. edit_file, run_command")
    tool_args: Optional[Dict[str, Any]] = Field(default=None, description="Arguments passed to tool")
    tool_result: Optional[str] = Field(default=None, description="Output/response from tool")
    agent_thought: Optional[str] = Field(default=None, description="Internal reasoning / thinking of agent")
    user_prompt: Optional[str] = Field(default=None, description="User instruction for this turn")
    files_affected: List[str] = Field(default_factory=list, description="Paths of files modified/created")
    commit_hash: Optional[str] = Field(default=None, description="Shadow git commit hash corresponding to this state")
    diff: Optional[str] = Field(default=None, description="Unified git diff introduced at this step")
    token_usage: Optional[Dict[str, Any]] = Field(default=None, description="Tokens used: prompt, completion, total")
    duration_ms: Optional[int] = Field(default=None, description="Duration of step execution in ms")

    def summary(self) -> str:
        """Returns a concise 1-line summary of the step action."""
        if self.tool_name:
            if self.tool_name in ("edit_file", "write_file") and self.tool_args and "path" in self.tool_args:
                return f"{self.tool_name}({Path(self.tool_args['path']).name})"
            elif self.tool_name == "run_command" and self.tool_args and "command" in self.tool_args:
                cmd = str(self.tool_args["command"])
                if len(cmd) > 35:
                    cmd = cmd[:32] + "..."
                return f"run_command: {cmd}"
            return f"tool: {self.tool_name}"
        elif self.user_prompt:
            p = self.user_prompt.strip().replace("\n", " ")
            return f"user: {p[:40]}..." if len(p) > 40 else f"user: {p}"
        elif self.agent_thought:
            t = self.agent_thought.strip().replace("\n", " ")
            return f"thought: {t[:40]}..." if len(t) > 40 else f"thought: {t}"
        return f"step #{self.step_number}"


class SessionMetadata(BaseModel):
    """Metadata describing an agent session trajectory."""
    session_id: str
    framework: str = Field(default="generic", description="Agent framework (antigravity, claude_code, cursor, aider)")
    workspace_root: str = Field(description="Root path of the workspace being modified")
    created_at: str = Field(default_factory=utc_now_iso)
    total_steps: int = Field(default=0)
    source_transcript_path: Optional[str] = None
    baseline_commit: Optional[str] = None
    description: Optional[str] = None


class AgentSession(BaseModel):
    """A full recorded sequence of steps making up an agent session."""
    metadata: SessionMetadata
    steps: List[AgentStep] = Field(default_factory=list)

    def get_step(self, step_number: int) -> Optional[AgentStep]:
        for s in self.steps:
            if s.step_number == step_number:
                return s
        return None

    def save_json(self, path: Path | str) -> None:
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = p.with_name(f"{p.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(self.model_dump_json(indent=2))
            os.replace(tmp_path, p)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    @classmethod
    def load_json(cls, path: Path | str) -> AgentSession:
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)


class EvaluationAttempt(BaseModel):
    """Details of a single execution attempt of an evaluator."""
    attempt_number: int
    status: BisectStatus
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


class BisectStepResult(BaseModel):
    """Result of running a test command at a specific step checkpoint."""
    step_number: int
    commit_hash: str
    status: BisectStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    command: str
    attempts: List[EvaluationAttempt] = Field(default_factory=list)
    is_flaky: bool = False


class WasteEstimate(BaseModel):
    """Estimates the tokens and time wasted from the bad step onward."""
    wasted_steps: int
    wasted_tokens: int
    estimated_cost_usd: float
    time_saved_minutes: float


class BisectReport(BaseModel):
    """Comprehensive final report after running an AgentBisect session."""
    session_id: str
    test_command: str
    total_steps: int
    first_bad_step: Optional[AgentStep] = None
    last_good_step: Optional[AgentStep] = None
    steps_evaluated: List[BisectStepResult] = Field(default_factory=list)
    evaluations_count: int = 0
    waste_estimate: Optional[WasteEstimate] = None
    suggested_fork_prompt: Optional[str] = None
    divergence_reason: Optional[str] = None
    classification: RegressionClassification = RegressionClassification.NO_REGRESSION
    confidence: float = 1.0
    non_monotonic_detected: bool = False
    diagnostics: List[str] = Field(default_factory=list)

    def is_found(self) -> bool:
        return self.first_bad_step is not None
