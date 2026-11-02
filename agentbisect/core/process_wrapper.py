"""
Process Wrapper for AgentBisect:
Transparently executes external commands or agent processes while monitoring filesystem mutations
and recording checkpoints into the Shadow Git Ledger.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.models import AgentStep, StepType


class ProcessWrapper:
    """Wraps an external command and creates automated step checkpoints."""

    def __init__(self, workspace_root: Path | str = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self.recorder = LiveRecorder(self.workspace_root)

    def run_wrapped(
        self,
        command_args: List[str],
        step_summary: Optional[str] = None,
    ) -> int:
        """
        Executes command_args in workspace, measures execution, checks for file diffs,
        and records a step in the shadow ledger if changes occurred.
        """
        cmd_str = " ".join(command_args) if isinstance(command_args, (list, tuple)) else str(command_args)
        summary = step_summary or f"run_command: {cmd_str[:35]}"

        # Avoid shell=True for argument sequences where possible to prevent injection,
        # but permit fallback for Windows shell built-ins (e.g. dir, type, copy).
        use_shell = isinstance(command_args, str)

        start_time = time.time()
        try:
            proc = subprocess.run(
                command_args,
                cwd=str(self.workspace_root),
                shell=use_shell,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            if sys.platform == "win32" and not use_shell:
                proc = subprocess.run(
                    command_args,
                    cwd=str(self.workspace_root),
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            else:
                raise
        duration_ms = int((time.time() - start_time) * 1000)

        # Print outputs to console
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="")

        # Record step
        self.recorder.record_step(
            tool_name="run_command",
            tool_args={"command": cmd_str, "exit_code": proc.returncode},
            tool_result=proc.stdout or proc.stderr,
            agent_thought=summary,
            duration_ms=duration_ms,
            step_type=StepType.COMMAND,
        )

        return proc.returncode
