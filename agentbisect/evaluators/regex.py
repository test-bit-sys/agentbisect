"""
Regex-based evaluator for testing file content patterns or assertions without executing tests.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from agentbisect.core.models import BisectStatus, BisectStepResult
from agentbisect.evaluators.base import BaseEvaluator


class RegexEvaluator(BaseEvaluator):
    name = "regex_evaluator"

    def __init__(self, target_file_pattern: str, required_regex: str, should_match: bool = True):
        self.target_file_pattern = target_file_pattern
        self.required_regex = re.compile(required_regex)
        self.should_match = should_match

    def evaluate(
        self,
        step_number: int,
        commit_hash: str,
        workspace_root: Path,
    ) -> BisectStepResult:
        start_time = time.time()
        matching_files = list(workspace_root.glob(self.target_file_pattern))

        if not matching_files:
            duration = time.time() - start_time
            return BisectStepResult(
                step_number=step_number,
                commit_hash=commit_hash,
                status=BisectStatus.FAIL,
                exit_code=1,
                stdout="",
                stderr=f"No files matched pattern: {self.target_file_pattern}",
                duration_seconds=round(duration, 3),
                command=f"regex:{self.required_regex.pattern}",
            )

        found = False
        for f in matching_files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                if self.required_regex.search(content):
                    found = True
                    break
            except Exception:
                continue

        duration = time.time() - start_time
        passed = (found == self.should_match)
        status = BisectStatus.PASS if passed else BisectStatus.FAIL

        return BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=status,
            exit_code=0 if passed else 1,
            stdout=f"Pattern '{self.required_regex.pattern}' found: {found}",
            stderr="" if passed else f"Regex expectation failed for {self.target_file_pattern}",
            duration_seconds=round(duration, 3),
            command=f"regex:{self.required_regex.pattern}",
        )
