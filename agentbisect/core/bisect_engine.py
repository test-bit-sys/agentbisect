"""
Binary search and heuristic bisect engine for AI agent session trajectories.
Supports pluggable evaluators, non-monotonic trajectory detection, and flaky test retry handling.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from agentbisect.core.models import (
    AgentStep,
    AgentSession,
    BisectReport,
    BisectStatus,
    BisectStepResult,
    RegressionClassification,
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
        self._evaluation_cache: Dict[Tuple[int, str, str], BisectStepResult] = {}

        if evaluator:
            self.evaluator = evaluator
            cmd_val = getattr(evaluator, "command", None)
            if cmd_val and isinstance(cmd_val, str):
                self.test_command = cmd_val
            elif hasattr(evaluator, "name") and isinstance(evaluator.name, str):
                self.test_command = evaluator.name
            else:
                self.test_command = "evaluator"
        elif test_command:
            self.test_command = test_command
            self.evaluator = CommandEvaluator(
                command=test_command,
                timeout_seconds=timeout_seconds,
                retries=retries,
            )
        else:
            raise ValueError("Either test_command or evaluator must be provided.")

    def validate_preconditions(
        self,
        known_good: Optional[int] = None,
        known_bad: Optional[int] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Validates bisection preconditions: step ordering, trajectory consistency,
        and checkpoint existence in the shadow ledger.
        """
        errors = []
        total_steps = len(self.session.steps)
        if total_steps == 0:
            errors.append("Session contains no steps to bisect.")
            return False, errors

        # Validate step indices if explicitly provided
        if known_good is not None:
            if known_good < 1 or known_good > total_steps:
                errors.append(f"Known good step {known_good} is out of bounds [1, {total_steps}].")
        if known_bad is not None:
            if known_bad < 1 or known_bad > total_steps:
                errors.append(f"Known bad step {known_bad} is out of bounds [1, {total_steps}].")
        if known_good is not None and known_bad is not None and known_good >= known_bad:
            errors.append(
                f"Invalid ordering: known good step ({known_good}) must be strictly less than known bad step ({known_bad})."
            )

        # Verify checkpoints exist in shadow ledger
        missing_checkpoints = []
        for step in self.session.steps:
            commit = self.ledger.get_commit_for_step(step.step_number)
            if not commit:
                missing_checkpoints.append(step.step_number)

        if missing_checkpoints:
            sample = missing_checkpoints[:5]
            errors.append(
                f"Missing checkpoint commits in shadow ledger for steps: {sample}{'...' if len(missing_checkpoints) > 5 else ''}"
            )

        return len(errors) == 0, errors

    def _execute_test(self, step_number: int, commit_hash: str) -> BisectStepResult:
        """Restores workspace to the given step and executes the evaluation strategy with memoization."""
        cache_key = (step_number, commit_hash, self.test_command)
        if cache_key in self._evaluation_cache:
            return self._evaluation_cache[cache_key].model_copy(deep=True)

        try:
            self.ledger.restore_step(step_number)
            result = self.evaluator.evaluate(
                step_number=step_number,
                commit_hash=commit_hash,
                workspace_root=self.ledger.workspace_root,
            )
            # Cache completed evaluation results
            self._evaluation_cache[cache_key] = result.model_copy(deep=True)
        except Exception as e:
            # Infrastructure exceptions during restore are not cached so retries can succeed
            result = BisectStepResult(
                step_number=step_number,
                commit_hash=commit_hash,
                status=BisectStatus.ERROR,
                exit_code=-2,
                stdout="",
                stderr=f"Failed restoring or evaluating Step #{step_number}: {e}",
                duration_seconds=0.0,
                command=self.test_command,
            )
        self.evaluated_steps.append(result)
        if self.on_step_evaluated:
            self.on_step_evaluated(result, len(self.evaluated_steps), len(self.session.steps))
        return result

    def run(
        self,
        verify_endpoints: bool = True,
        verify_monotonicity: bool = False,
        known_good: Optional[int] = None,
        known_bad: Optional[int] = None,
    ) -> BisectReport:
        """
        Executes search across the session trajectory [1 .. N].
        Returns a BisectReport containing the first bad step, confidence, and analysis.
        Guarantees transactional workspace restoration.
        """
        # Scope cache and evaluated steps strictly to this run
        self.evaluated_steps = []
        self._evaluation_cache.clear()

        total_steps = len(self.session.steps)
        if total_steps == 0:
            raise ValueError("Session contains no steps to bisect.")

        # Validate preconditions
        valid, precond_errors = self.validate_preconditions(known_good=known_good, known_bad=known_bad)
        if not valid:
            return BisectReport(
                session_id=self.session.metadata.session_id,
                test_command=self.test_command,
                total_steps=total_steps,
                first_bad_step=None,
                last_good_step=None,
                steps_evaluated=self.evaluated_steps,
                evaluations_count=0,
                classification=RegressionClassification.INCONCLUSIVE,
                confidence=0.0,
                diagnostics=precond_errors,
                divergence_reason=f"Precondition validation failed: {'; '.join(precond_errors)}",
            )

        # Record original workspace HEAD to guarantee restoration
        original_head = self.ledger.get_current_head()
        stashed = self.ledger.stash_worktree()

        diagnostics: List[str] = []

        try:
            # Handle single-step trajectories cleanly
            if total_steps == 1:
                commit_1 = self.ledger.get_commit_for_step(1) or ""
                res_1 = self._execute_test(1, commit_1)
                if res_1.status == BisectStatus.PASS:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=1,
                        first_bad_step=None,
                        last_good_step=self.session.get_step(1),
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.NO_REGRESSION,
                        confidence=1.0,
                        divergence_reason="Step 1 PASSES the test. No regression detected.",
                    )
                elif res_1.status == BisectStatus.FAIL:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=1,
                        first_bad_step=self.session.get_step(1),
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.BROKEN_BASELINE,
                        confidence=1.0,
                        divergence_reason="Step 1 FAILS the test! The test was broken before the agent began.",
                    )
                elif res_1.status == BisectStatus.ERROR:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=1,
                        first_bad_step=self.session.get_step(1),
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.BROKEN_BASELINE,
                        confidence=1.0,
                        diagnostics=[f"Step #1 baseline returned ERROR: {res_1.stderr}"],
                        divergence_reason=f"Step 1 baseline failed with ERROR! {res_1.stderr.strip()}",
                    )
                else:  # INCONCLUSIVE
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=1,
                        first_bad_step=None,
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.INCONCLUSIVE,
                        confidence=0.0,
                        diagnostics=[f"Step #1 baseline returned INCONCLUSIVE: {res_1.stderr}"],
                        divergence_reason=f"Step 1 baseline test is INCONCLUSIVE (timed out or unstable): {res_1.stderr.strip()}",
                    )

            latest_step_num = known_bad if known_bad is not None else total_steps
            latest_commit = self.ledger.get_commit_for_step(latest_step_num) or ""

            first_bad_step: Optional[AgentStep] = None
            last_good_step: Optional[AgentStep] = None
            bad_test_result: Optional[BisectStepResult] = None

            if verify_endpoints:
                # 1. Verify latest step fails
                res_latest = self._execute_test(latest_step_num, latest_commit)
                if res_latest.status == BisectStatus.PASS:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=total_steps,
                        first_bad_step=None,
                        last_good_step=self.session.get_step(latest_step_num),
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.NO_REGRESSION,
                        confidence=1.0,
                        divergence_reason="Current latest step already PASSES the test. No regression detected.",
                    )

                bad_test_result = res_latest
                first_bad_step = self.session.get_step(latest_step_num)

                # 2. Verify step 1 passes (or check if already broken)
                first_step_num = known_good if known_good is not None else 1
                first_commit = self.ledger.get_commit_for_step(first_step_num) or ""
                res_first = self._execute_test(first_step_num, first_commit)
                if res_first.status == BisectStatus.FAIL:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=total_steps,
                        first_bad_step=self.session.get_step(first_step_num),
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.BROKEN_BASELINE,
                        confidence=1.0,
                        divergence_reason=f"Step {first_step_num} already FAILS the test! The test was broken before the agent began.",
                    )
                elif res_first.status == BisectStatus.ERROR:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=total_steps,
                        first_bad_step=self.session.get_step(first_step_num),
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.BROKEN_BASELINE,
                        confidence=1.0,
                        diagnostics=[f"Step #{first_step_num} baseline returned ERROR: {res_first.stderr}"],
                        divergence_reason=f"Step {first_step_num} baseline failed with ERROR! {res_first.stderr.strip()}",
                    )
                elif res_first.status == BisectStatus.INCONCLUSIVE:
                    return BisectReport(
                        session_id=self.session.metadata.session_id,
                        test_command=self.test_command,
                        total_steps=total_steps,
                        first_bad_step=None,
                        last_good_step=None,
                        steps_evaluated=self.evaluated_steps,
                        evaluations_count=len(self.evaluated_steps),
                        classification=RegressionClassification.INCONCLUSIVE,
                        confidence=0.0,
                        diagnostics=[f"Step #{first_step_num} baseline returned INCONCLUSIVE: {res_first.stderr}"],
                        divergence_reason=f"Step {first_step_num} baseline test is INCONCLUSIVE (timed out or unstable): {res_first.stderr.strip()}",
                    )

                last_good_step = self.session.get_step(first_step_num)

                low = first_step_num + 1
                high = latest_step_num - 1
            else:
                low = known_good if known_good is not None else 1
                high = known_bad if known_bad is not None else total_steps

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
                elif res.status == BisectStatus.FAIL:
                    first_bad_step = self.session.get_step(mid)
                    bad_test_result = res
                    high = mid - 1
                else:
                    # Infrastructure error or inconclusive timeout
                    diagnostics.append(f"Step #{mid} evaluation returned {res.status}: {res.stderr[:100]}")
                    # Attempt fallback to neighbor if possible
                    if mid > low:
                        mid_fallback = mid - 1
                        fb_commit = self.ledger.get_commit_for_step(mid_fallback) or ""
                        fb_res = self._execute_test(mid_fallback, fb_commit)
                        if fb_res.status == BisectStatus.PASS:
                            last_good_step = self.session.get_step(mid_fallback)
                            low = mid_fallback + 1
                        elif fb_res.status == BisectStatus.FAIL:
                            first_bad_step = self.session.get_step(mid_fallback)
                            bad_test_result = fb_res
                            high = mid_fallback - 1
                        else:
                            high = mid - 1
                    else:
                        low = mid + 1

            # 4. Optional monotonicity verification pass to detect hidden earlier regressions
            non_monotonic_detected = False
            status_by_step = {res.step_number: res.status for res in self.evaluated_steps}

            if verify_monotonicity and first_bad_step:
                candidate_num = first_bad_step.step_number
                for s_num in range(1, candidate_num):
                    if s_num not in status_by_step:
                        commit = self.ledger.get_commit_for_step(s_num) or ""
                        res_unvisited = self._execute_test(s_num, commit)
                        status_by_step[s_num] = res_unvisited.status
                        if res_unvisited.status == BisectStatus.FAIL:
                            non_monotonic_detected = True
                            first_bad_step = self.session.get_step(s_num)
                            bad_test_result = res_unvisited
                            diagnostics.append(
                                f"Non-monotonic trajectory inversion detected: Earlier Step #{s_num} FAILED, but intermediate step passed before Step #{candidate_num}."
                            )
                            break

            # 5. Check evaluated steps for inversions: Step i < Step j where status(i) is FAIL but status(j) is PASS
            eval_nums = sorted(status_by_step.keys())
            if not non_monotonic_detected:
                for idx_i in range(len(eval_nums)):
                    s_i = eval_nums[idx_i]
                    if status_by_step[s_i] == BisectStatus.FAIL:
                        for idx_j in range(idx_i + 1, len(eval_nums)):
                            s_j = eval_nums[idx_j]
                            if status_by_step[s_j] == BisectStatus.PASS:
                                non_monotonic_detected = True
                                diagnostics.append(
                                    f"Non-monotonic trajectory inversion detected: Step #{s_i} FAILED, but later Step #{s_j} PASSED."
                                )
                                break
                    if non_monotonic_detected:
                        break

            # Flaky check
            flaky_steps = [res.step_number for res in self.evaluated_steps if res.is_flaky]
            if flaky_steps:
                diagnostics.append(f"Flaky/intermittent test behavior observed at steps: {flaky_steps}")

            # Classification & confidence scoring
            if non_monotonic_detected:
                classification = RegressionClassification.EARLIEST_OBSERVED
                confidence = 0.65
            elif flaky_steps:
                classification = RegressionClassification.PROBABLE
                confidence = 0.80
            elif first_bad_step:
                if last_good_step is not None:
                    good_n = last_good_step.step_number
                    bad_n = first_bad_step.step_number
                    if bad_n == good_n + 1:
                        classification = RegressionClassification.CONFIRMED
                        confidence = 0.98
                    else:
                        classification = RegressionClassification.PROBABLE
                        confidence = 0.85
                else:
                    # No passing step was ever observed
                    if first_bad_step.step_number == 1:
                        classification = RegressionClassification.BROKEN_BASELINE
                        confidence = 0.90
                        diagnostics.append("Step 1 failed and no passing step was verified; baseline appears broken.")
                    else:
                        classification = RegressionClassification.PROBABLE
                        confidence = 0.70
            elif last_good_step:
                classification = RegressionClassification.NO_REGRESSION
                confidence = 1.0
            else:
                classification = RegressionClassification.INCONCLUSIVE
                confidence = 0.50

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
            elif last_good_step:
                divergence_reason = "All evaluated steps passed the test. No regression detected."

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
                classification=classification,
                confidence=confidence,
                non_monotonic_detected=non_monotonic_detected,
                diagnostics=diagnostics,
            )
        finally:
            # Guarantee workspace restoration
            if stashed:
                self.ledger.restore_stash(parent_commit=original_head)
            elif original_head:
                self.ledger.restore_commit(original_head)
