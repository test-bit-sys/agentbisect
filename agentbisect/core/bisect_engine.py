"""
Binary search and heuristic bisect engine for AI agent session trajectories.
Supports pluggable evaluators and flaky test retry handling.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional
from agentbisect.core.models import (
    AgentStep,
    AgentSession,
    BisectReport,
    BisectStatus,
    BisectStepResult,
)
from agentbisect.core.shadow_ledger import ShadowLedger
from agentbisect.core.analyzer import SessionAnalyzer
from agentbisect.core.heuristics import SearchStrategy
from agentbisect.evaluators.base import BaseEvaluator
from agentbisect.evaluators.command import CommandEvaluator


class BisectEngine:
    """
    Executes automated binary or heuristic search over an agent's session steps
    to isolate the exact first step where tests/evaluations broke.
    """

    def __init__(
        self,
        session: AgentSession,
        ledger: ShadowLedger,
        test_command: Optional[str] = None,
        evaluator: Optional[BaseEvaluator] = None,
        timeout_seconds: int = 60,
        retries: int = 1,
        strategy: str = "binary",
        on_step_evaluated: Optional[Callable[[BisectStepResult, int, int], None]] = None,
    ):
        self.session = session
        self.ledger = ledger
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.strategy = strategy
        self.on_step_evaluated = on_step_evaluated
        self.evaluated_steps: List[BisectStepResult] = []

        if evaluator:
            self.evaluator = evaluator
            self.test_command = getattr(evaluator, "command", evaluator.name)
        elif test_command:
            self.test_command = test_command
            self.evaluator = CommandEvaluator(
                command=test_command,
                timeout_seconds=timeout_seconds,
                retries=retries,
            )
        else:
            raise ValueError("Either test_command or evaluator must be provided.")

    def _execute_test(self, step_number: int, commit_hash: str) -> BisectStepResult:
        """Restores workspace to the given step and executes the evaluation strategy."""
        self.ledger.restore_step(step_number)
        result = self.evaluator.evaluate(
            step_number=step_number,
            commit_hash=commit_hash,
            workspace_root=self.ledger.workspace_root,
        )
        self.evaluated_steps.append(result)
        if self.on_step_evaluated:
            self.on_step_evaluated(result, len(self.evaluated_steps), len(self.session.steps))
        return result

    def run(self, verify_endpoints: bool = True) -> BisectReport:
        """
        Executes search across the session trajectory [1 .. N].
        Returns a BisectReport containing the first bad step and analysis.
        """
        total_steps = len(self.session.steps)
        if total_steps == 0:
            raise ValueError("Session contains no steps to bisect.")

        # Stash uncommitted changes in worktree if any
        stashed = self.ledger.stash_worktree()

        try:
            latest_step_num = total_steps
            latest_commit = self.ledger.get_commit_for_step(latest_step_num) or ""

            first_bad_step: Optional[AgentStep] = None
            last_good_step: Optional[AgentStep] = None
            bad_test_result: Optional[BisectStepResult] = None

            if verify_endpoints and total_steps > 1:
                # 1. Verify latest step fails
                res_latest = self._execute_test(latest_step_num, latest_commit)
                if res_latest.status == BisectStatus.PASS:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=total_steps,
                        first_bad_step=None,
                        last_good_step=self.session.steps[-1],
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        divergence_reason="Current latest step already PASSES the test. No regression detected.",
                    )

                bad_test_result = res_latest
                first_bad_step = self.session.steps[-1]

                # 2. Verify step 1 passes (or check if already broken)
                first_commit = self.ledger.get_commit_for_step(1) or ""
                res_first = self._execute_test(1, first_commit)
                if res_first.status == BisectStatus.FAIL:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=total_steps,
                        first_bad_step=self.session.steps[0],
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        divergence_reason="Step 1 already FAILS the test! The test was broken before the agent began.",
                    )
                last_good_step = self.session.steps[0]

                low = 2
                high = total_steps - 1
            else:
                low = 1
                high = total_steps

            # 3. Search loop (binary or weighted heuristic)
            while low <= high:
                if self.strategy == "heuristic":
                    mid = SearchStrategy.weighted_candidate(low, high, self.session.steps)
                else:
                    mid = SearchStrategy.binary_midpoint(low, high)

                commit = self.ledger.get_commit_for_step(mid) or ""
                res = self._execute_test(mid, commit)

                if res.status == BisectStatus.PASS:
                    last_good_step = self.session.get_step(mid)
                    low = mid + 1
                else:
                    first_bad_step = self.session.get_step(mid)
                    bad_test_result = res
                    high = mid - 1

            # Calculate waste
            first_bad_num = first_bad_step.step_number if first_bad_step else (total_steps + 1)
            waste = SessionAnalyzer.calculate_waste(self.session, first_bad_num)

            # Formulate root cause and suggested prompt
            divergence_reason = ""
            suggested_fork_prompt = ""
            if first_bad_step:
                if not first_bad_step.diff:
                    first_bad_step.diff = self.ledger.get_step_diff(first_bad_step.step_number)
                if not first_bad_step.files_affected:
                    first_bad_step.files_affected = self.ledger.get_affected_files(first_bad_step.step_number)

                stderr = bad_test_result.stderr if bad_test_result else ""
                stdout = bad_test_result.stdout if bad_test_result else ""
                divergence_reason = SessionAnalyzer.extract_divergence_reason(
                    first_bad_step, stderr, stdout
                )

                good_num = last_good_step.step_number if last_good_step else 0
                suggested_fork_prompt = (
                    f"Workspace has been rewound to Step {good_num} (last verified good state).\n"
                    f"At Step {first_bad_step.step_number}, your tool call '{first_bad_step.summary()}' broke the test with:\n"
                    f"```\n{divergence_reason}\n```\n"
                    f"Please take an alternative approach that preserves existing tests and avoids this error."
                )

            return BisectReport(
                session_id=self.session.metadata.session_id,
                test_command=self.test_command,
                total_steps=total_steps,
                first_bad_step=first_bad_step,
                last_good_step=last_good_step,
                steps_evaluated=self.evaluated_steps,
                evaluations_count=len(self.evaluated_steps),
                waste_estimate=waste,
                suggested_fork_prompt=suggested_fork_prompt,
                divergence_reason=divergence_reason,
            )
        finally:
            if stashed:
                self.ledger.restore_stash()
