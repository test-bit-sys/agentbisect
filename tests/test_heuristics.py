"""
Unit tests for SearchStrategy heuristics.
"""

from agentbisect.core.heuristics import SearchStrategy
from agentbisect.core.models import AgentStep, StepType


def test_search_strategy_heuristics():
    # 1. Binary midpoint
    assert SearchStrategy.binary_midpoint(1, 10) == 5
    assert SearchStrategy.binary_midpoint(5, 6) == 5

    # 2. Weighted candidate
    # Step 5 modified README.md
    # Step 6 modified auth.py (high risk)
    steps = [
        AgentStep(step_number=i, step_id=f"s_{i}", files_affected=[f"file_{i}.txt"])
        for i in range(1, 11)
    ]
    steps[4].files_affected = ["README.md"]
    steps[5].files_affected = ["src/auth.py"]

    candidate = SearchStrategy.weighted_candidate(1, 10, steps)
    # Around midpoint 5, step 6 modifies Python source file, so it should be prioritized
    assert candidate in (5, 6)
