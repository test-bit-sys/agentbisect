"""
Command-based Evaluator with timeout, explicit regression oracle, and flaky test retry tracking.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from agentbisect.core.models import BisectStatus, BisectStepResult, EvaluationAttempt
from agentbisect.evaluators.base import BaseEvaluator


def _kill_process_tree(pid: int) -> None:
    """Terminates an entire process tree reliably on Windows and POSIX."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=5.0,
            )
        except Exception:
            pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            pass


class CommandEvaluator(BaseEvaluator):
    name = "command_evaluator"

    def __init__(
        self,
        command: str,
        timeout_seconds: int = 60,
        retries: int = 1,
        stability_policy: str = "majority",
    ):
        self.command = command
        # Bound timeout and retries safely
        self.timeout_seconds = max(1, min(timeout_seconds, 3600))
        self.retries = max(1, min(retries, 10))
        self.stability_policy = stability_policy  # 'majority' or 'require_all_pass'

    def _run_single_attempt(
        self,
        attempt_number: int,
        workspace_root: Path,
    ) -> EvaluationAttempt:
        start_time = time.time()
        proc: Optional[subprocess.Popen] = None
        try:
            kwargs = {}
            if sys.platform != "win32":
                kwargs["start_new_session"] = True

            proc = subprocess.Popen(
                self.command,
                shell=True,
                cwd=str(workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **kwargs,
            )
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
            duration = round(time.time() - start_time, 3)
            status = BisectStatus.PASS if proc.returncode == 0 else BisectStatus.FAIL
            return EvaluationAttempt(
                attempt_number=attempt_number,
                status=status,
                exit_code=proc.returncode,
                stdout=stdout or "",
                stderr=stderr or "",
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
            if proc is not None:
                _kill_process_tree(proc.pid)
                try:
                    stdout, stderr = proc.communicate(timeout=1.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            duration = round(time.time() - start_time, 3)
            stderr_msg = f"Test command timed out after {self.timeout_seconds} seconds."
            if stderr:
                stderr_msg += f"\n{stderr}"
            return EvaluationAttempt(
                attempt_number=attempt_number,
                status=BisectStatus.INCONCLUSIVE,
                exit_code=-1,
                stdout=stdout or "",
                stderr=stderr_msg,
                duration_seconds=duration,
            )
        except Exception as e:
            if proc is not None and proc.poll() is None:
                _kill_process_tree(proc.pid)
                try:
                    proc.kill()
                except Exception:
                    pass
            duration = round(time.time() - start_time, 3)
            return EvaluationAttempt(
                attempt_number=attempt_number,
                status=BisectStatus.ERROR,
                exit_code=-2,
                stdout="",
                stderr=f"Infrastructure / execution error: {type(e).__name__}: {e}",
                duration_seconds=duration,
            )

    def evaluate(
        self,
        step_number: int,
        commit_hash: str,
        workspace_root: Path,
    ) -> BisectStepResult:
        """Executes the test command with full retry recording and stability evaluation."""
        attempts: List[EvaluationAttempt] = []

        for attempt_idx in range(self.retries):
            attempt_res = self._run_single_attempt(
                attempt_number=attempt_idx + 1,
                workspace_root=workspace_root,
            )
            attempts.append(attempt_res)

            # If not configured for multiple retries, finish immediately
            if self.retries == 1:
                break

            # If single run without retries requested, or if already reached consensus
            # For multiple retries, continue to gather stability evidence unless fatal error
            if attempt_res.status == BisectStatus.ERROR:
                break

        # Analyze stability across attempts
        statuses = [a.status for a in attempts]
        pass_count = statuses.count(BisectStatus.PASS)
        fail_count = statuses.count(BisectStatus.FAIL)
        error_count = statuses.count(BisectStatus.ERROR)
        inconclusive_count = statuses.count(BisectStatus.INCONCLUSIVE)

        is_flaky = (pass_count > 0 and fail_count > 0)

        # Decide final consensus status
        if error_count > 0 and (pass_count == 0 and fail_count == 0):
            final_status = BisectStatus.ERROR
        elif inconclusive_count > 0 and (pass_count == 0 and fail_count == 0):
            final_status = BisectStatus.INCONCLUSIVE
        elif is_flaky:
            if self.stability_policy == "require_all_pass":
                final_status = BisectStatus.FAIL
            else:
                final_status = BisectStatus.PASS if pass_count > fail_count else BisectStatus.FAIL
        elif pass_count > 0 and fail_count == 0:
            final_status = BisectStatus.PASS
        elif fail_count > 0 and pass_count == 0:
            final_status = BisectStatus.FAIL
        else:
            final_status = attempts[-1].status

        latest = attempts[-1]
        total_duration = round(sum(a.duration_seconds for a in attempts), 3)

        return BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=final_status,
            exit_code=latest.exit_code,
            stdout=latest.stdout,
            stderr=latest.stderr,
            duration_seconds=total_duration,
            command=self.command,
            attempts=attempts,
            is_flaky=is_flaky,
        )
