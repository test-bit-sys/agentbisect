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


def test_analyzer_calculate_waste_defensive_against_none_tokens():
    """
    Regression test: Verifies that SessionAnalyzer.calculate_waste handles None token values
    without raising TypeError.
    """
    from agentbisect.core.analyzer import SessionAnalyzer
    from agentbisect.core.models import AgentSession, SessionMetadata, AgentStep

    session = AgentSession(
        metadata=SessionMetadata(session_id="none_tokens", workspace_root="."),
        steps=[
            AgentStep(step_number=1, step_id="1", token_usage={"total": None, "total_tokens": None}),
            AgentStep(step_number=2, step_id="2", token_usage=None),
            AgentStep(step_number=3, step_id="3", token_usage={"prompt_tokens": 100, "completion_tokens": 50}),
        ],
    )

    waste = SessionAnalyzer.calculate_waste(session, first_bad_step_num=1)
    assert waste.wasted_steps == 3
    assert waste.wasted_tokens > 0
    assert waste.estimated_cost_usd > 0


def test_session_analyzer_waste_calculation_with_malformed_token_usage():
    """
    Robustness test: calculate_waste must handle None, non-integer strings,
    and missing fields in token_usage without crashing.
    """
    from agentbisect.core.models import AgentSession, SessionMetadata, AgentStep
    from agentbisect.core.analyzer import SessionAnalyzer

    session = AgentSession(
        metadata=SessionMetadata(session_id="malformed_test", workspace_root="/tmp"),
        steps=[
            AgentStep(
                step_number=1,
                step_id="s1",
                tool_name="edit_file",
                token_usage={"total": "invalid_string_tokens"},
                duration_ms=None,
            ),
            AgentStep(
                step_number=2,
                step_id="s2",
                tool_name="edit_file",
                token_usage={"prompt_tokens": None, "completion_tokens": "not_an_int"},
                duration_ms=None,
            ),
            AgentStep(
                step_number=3,
                step_id="s3",
                tool_name="edit_file",
                token_usage=None,
                duration_ms=10000,
            ),
        ],
    )

    waste = SessionAnalyzer.calculate_waste(session, first_bad_step_num=1)
    assert waste.wasted_steps == 3
    # All 3 steps fallback gracefully to defaults (1800 tokens each)
    assert waste.wasted_tokens == 1800 * 3
    assert waste.estimated_cost_usd > 0
    assert waste.time_saved_minutes > 0
