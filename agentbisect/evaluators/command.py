"""
Command-based Evaluator with timeout and flaky test retry protection.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from agentbisect.core.models import BisectStatus, BisectStepResult
from agentbisect.evaluators.base import BaseEvaluator


class CommandEvaluator(BaseEvaluator):
    name = "command_evaluator"

    def __init__(self, command: str, timeout_seconds: int = 60, retries: int = 1):
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.retries = max(1, retries)

    def evaluate(
        self,
        step_number: int,
        commit_hash: str,
        workspace_root: Path,
    ) -> BisectStepResult:
        """Executes the test command with retry handling for flaky tests."""
        last_result: BisectStepResult | None = None

        for attempt in range(self.retries):
            start_time = time.time()
            try:
                proc = subprocess.run(
                    self.command,
                    shell=True,
                    cwd=str(workspace_root),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    encoding="utf-8",
                    errors="replace",
                )
                duration = time.time() - start_time
                status = BisectStatus.PASS if proc.returncode == 0 else BisectStatus.FAIL
                last_result = BisectStepResult(
                    step_number=step_number,
                    commit_hash=commit_hash,
                    status=status,
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    duration_seconds=round(duration, 3),
                    command=self.command,
                )

                # If passed, we accept immediately
                if status == BisectStatus.PASS:
                    return last_result

            except subprocess.TimeoutExpired as e:
                duration = time.time() - start_time
                last_result = BisectStepResult(
                    step_number=step_number,
                    commit_hash=commit_hash,
                    status=BisectStatus.FAIL,
                    exit_code=-1,
                    stdout=e.stdout or "",
                    stderr=f"Test timed out after {self.timeout_seconds} seconds.",
                    duration_seconds=round(duration, 3),
                    command=self.command,
                )
            except Exception as e:
                duration = time.time() - start_time
                last_result = BisectStepResult(
                    step_number=step_number,
                    commit_hash=commit_hash,
                    status=BisectStatus.ERROR,
                    exit_code=-2,
                    stdout="",
                    stderr=str(e),
                    duration_seconds=round(duration, 3),
                    command=self.command,
                )

        return last_result or BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=BisectStatus.ERROR,
            exit_code=-1,
            stdout="",
            stderr="No evaluation could be completed.",
            duration_seconds=0.0,
            command=self.command,
        )
