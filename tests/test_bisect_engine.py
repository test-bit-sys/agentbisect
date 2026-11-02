"""
Unit tests for BisectEngine.
"""

import sys
import tempfile
from pathlib import Path
import pytest
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.bisect_engine import BisectEngine
from agentbisect.core.models import BisectStatus


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_bisect_engine_identifies_exact_culprit(temp_workspace):
    """
    Simulates a 10-step trajectory where step 6 breaks the test.
    Verifies that BisectEngine identifies step 6 as first_bad_step.
    """
    recorder = LiveRecorder(temp_workspace, session_id="test_bisect_session")

    # Step 1: Create valid test script and code
    code_file = temp_workspace / "calc.py"
    test_file = temp_workspace / "test_calc.py"

    code_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    test_file.write_text(
        "from calc import add\n"
        "def test_add():\n"
        "    assert add(2, 2) == 4\n"
        "if __name__ == '__main__':\n"
        "    test_add()\n",
        encoding="utf-8",
    )

    recorder.record_step(tool_name="write_file", files_affected=["calc.py", "test_calc.py"])

    # Steps 2 to 5: All valid modifications
    for i in range(2, 6):
        code_file.write_text(f"def add(a, b): return a + b\n# mod {i}\n", encoding="utf-8")
        recorder.record_step(tool_name="edit_file", files_affected=["calc.py"])

    # Step 6: THE REGRESSION (bug introduces 2+2 != 4)
    code_file.write_text("def add(a, b): return a + b + 999\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file", files_affected=["calc.py"])

    # Steps 7 to 10: Subsequent edits
    for i in range(7, 11):
        extra_file = temp_workspace / f"extra_{i}.py"
        extra_file.write_text(f"x = {i}\n", encoding="utf-8")
        recorder.record_step(tool_name="write_file", files_affected=[f"extra_{i}.py"])

    # Run BisectEngine testing test_calc.py
    engine = BisectEngine(
        session=recorder.session,
        ledger=recorder.ledger,
        test_command=f'"{sys.executable}" test_calc.py',
        timeout_seconds=30,
    )

    report = engine.run()

    assert report.is_found()
    assert report.first_bad_step.step_number == 6
    assert report.last_good_step.step_number == 5
    assert report.waste_estimate.wasted_steps == 5  # steps 6, 7, 8, 9, 10
    assert report.evaluations_count <= 6  # logarithmic bound O(log2 N)
    assert report.classification.value == "CONFIRMED_FIRST_REGRESSION"
    assert report.confidence >= 0.95

    # Verification: workspace MUST be restored to latest state (step 10)
    extra_10 = temp_workspace / "extra_10.py"
    assert extra_10.exists(), "Workspace was not restored to the latest state upon completion!"


def test_bisect_engine_preconditions(temp_workspace):
    from agentbisect.core.models import AgentSession, SessionMetadata

    # Empty session
    empty_session = AgentSession(
        metadata=SessionMetadata(session_id="empty", workspace_root=str(temp_workspace)),
        steps=[],
    )
    from agentbisect.core.shadow_ledger import ShadowLedger
    ledger = ShadowLedger(temp_workspace)

    engine = BisectEngine(
        session=empty_session,
        ledger=ledger,
        test_command="python -c 'exit(0)'",
    )
    with pytest.raises(ValueError, match="Session contains no steps"):
        engine.run()


def test_bisect_engine_invalid_bounds(temp_workspace):
    recorder = LiveRecorder(temp_workspace, session_id="bounds_test")
    f = temp_workspace / "file.txt"
    f.write_text("v1", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    engine = BisectEngine(
        session=recorder.session,
        ledger=recorder.ledger,
        test_command="python -c 'exit(0)'",
    )
    # known_good >= known_bad is invalid
    report = engine.run(known_good=5, known_bad=2)
    assert report.classification.value == "INCONCLUSIVE"
    assert "Invalid ordering" in report.divergence_reason


def test_bisect_engine_restores_uncommitted_worktree_changes(temp_workspace):
    recorder = LiveRecorder(temp_workspace, session_id="stash_test")
    app = temp_workspace / "app.py"
    test_f = temp_workspace / "test_app.py"

    app.write_text("x = 1\n", encoding="utf-8")
    test_f.write_text("import app\nassert app.x == 1\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    app.write_text("x = 99\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    # Now create an uncommitted dirty file in workspace before bisect
    dirty_file = temp_workspace / "dirty_user_edit.txt"
    dirty_file.write_text("crucial user work in progress", encoding="utf-8")

    engine = BisectEngine(
        session=recorder.session,
        ledger=recorder.ledger,
        test_command=f'"{sys.executable}" test_app.py',
    )
    report = engine.run()
    assert report.is_found()
    assert report.first_bad_step.step_number == 2

    # Verify uncommitted file is preserved intact
    assert dirty_file.exists(), "User uncommitted work was deleted by bisect!"
    assert dirty_file.read_text(encoding="utf-8") == "crucial user work in progress"


def test_bisect_engine_non_monotonic_trajectory_detection(temp_workspace):
    """
    Trajectory:
    Step 1: PASS (x = 1)
    Step 2: FAIL (x = 2) -> bug introduced
    Step 3: PASS (x = 1) -> bug fixed!
    Step 4: PASS (x = 1)
    Step 5: FAIL (x = 5) -> new bug introduced
    Non-monotonic inversion: Step 2 failed, but later Step 3/4 passed.
    """
    recorder = LiveRecorder(temp_workspace, session_id="non_monotonic_session")
    code = temp_workspace / "flag.py"
    test_script = temp_workspace / "test_flag.py"

    test_script.write_text("import flag\nassert flag.val == 1\n", encoding="utf-8")

    # Step 1: PASS
    code.write_text("val = 1\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    # Step 2: FAIL
    code.write_text("val = 2\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    # Step 3: PASS (fixed)
    code.write_text("val = 1\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    # Step 4: PASS
    code.write_text("val = 1\n# extra\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    # Step 5: FAIL (broken again)
    code.write_text("val = 5\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    engine = BisectEngine(
        session=recorder.session,
        ledger=recorder.ledger,
        test_command=f'"{sys.executable}" test_flag.py',
        timeout_seconds=10,
    )
    report = engine.run(verify_monotonicity=True)
    assert report.non_monotonic_detected is True
    assert report.classification.value == "EARLIEST_OBSERVED_FAILURE"
    assert any("Non-monotonic trajectory inversion" in d for d in report.diagnostics)

