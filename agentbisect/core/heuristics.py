"""
Search strategies and heuristics for AgentBisect:
Includes standard Binary Search, and Weighted Heuristic Search based on diff risk scores.
"""

from __future__ import annotations

from typing import List
from agentbisect.core.models import AgentStep


class SearchStrategy:
    """Calculates next candidate step index to evaluate."""

    @staticmethod
    def binary_midpoint(low: int, high: int) -> int:
        return (low + high) // 2

    @staticmethod
    def weighted_candidate(low: int, high: int, steps: List[AgentStep]) -> int:
        """
        Picks the candidate closest to midpoint that has the highest risk score.
        Risk score is calculated based on modified source code vs docs/configs.
        """
        if low >= high:
            return low

        mid = (low + high) // 2
        # Check window around mid [mid-1, mid, mid+1] within bounds
        candidates = [i for i in (mid, mid - 1, mid + 1) if low <= i <= high]

        best_candidate = mid
        best_score = -1

        for c in candidates:
            step = next((s for s in steps if s.step_number == c), None)
            if not step:
                continue

            score = 1
            for f in step.files_affected:
                f_lower = f.lower()
                if f_lower.endswith((".py", ".js", ".ts", ".rs", ".go", ".c", ".cpp")):
                    score += 5
                if "test" in f_lower or "spec" in f_lower:
                    score += 3
                if f_lower.endswith((".md", ".txt", ".json", ".yaml", ".yml")):
                    score += 0.5

            if step.diff:
                score += min(len(step.diff.splitlines()) * 0.1, 10)

            if score > best_score:
                best_score = score
                best_candidate = c

        return best_candidate
