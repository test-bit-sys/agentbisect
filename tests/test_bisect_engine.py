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



def test_bisect_engine_broken_baseline_when_step_1_errors(temp_workspace):
    """
    Regression test: When step 1 evaluation returns ERROR, BisectEngine must NOT
    treat step 1 as last_good_step and falsely blame later steps.
    It must report BROKEN_BASELINE.
    """
    recorder = LiveRecorder(temp_workspace, session_id="broken_baseline_error_session")
    f = temp_workspace / "code.py"
    f.write_text("x = 1\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    f.write_text("x = 2\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    f.write_text("x = 3\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    from unittest.mock import MagicMock
    from agentbisect.core.models import BisectStepResult, RegressionClassification

    mock_evaluator = MagicMock()
    mock_evaluator.name = "mock_err"
    # Mock evaluate: always returns ERROR on step 1 and step 3
    def mock_eval(step_number, commit_hash, workspace_root):
        return BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=BisectStatus.ERROR,
            exit_code=-2,
            stdout="",
            stderr="command not found / syntax error in test runner",
            duration_seconds=0.05,
            command="bad_command",
        )
    mock_evaluator.evaluate.side_effect = mock_eval

    engine = BisectEngine(
        session=recorder.session,
        ledger=recorder.ledger,
        evaluator=mock_evaluator,
    )
    report = engine.run()
    assert report.classification == RegressionClassification.BROKEN_BASELINE
    assert report.last_good_step is None
    assert "Step 1 baseline failed with ERROR" in report.divergence_reason


def test_bisect_engine_broken_baseline_when_step_1_inconclusive(temp_workspace):
    """
    Regression test: When step 1 evaluation returns INCONCLUSIVE (timeout), BisectEngine
    must NOT mark step 1 as good state; it must report INCONCLUSIVE.
    """
    recorder = LiveRecorder(temp_workspace, session_id="broken_baseline_inconclusive_session")
    f = temp_workspace / "code.py"
    f.write_text("x = 1\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    f.write_text("x = 2\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    from unittest.mock import MagicMock
    from agentbisect.core.models import BisectStepResult, RegressionClassification

    mock_evaluator = MagicMock()
    mock_evaluator.name = "mock_inconclusive"
    def mock_eval(step_number, commit_hash, workspace_root):
        if step_number == 1:
            return BisectStepResult(
                step_number=1,
                commit_hash=commit_hash,
                status=BisectStatus.INCONCLUSIVE,
                exit_code=-1,
                stdout="",
                stderr="Timed out",
                duration_seconds=5.0,
                command="hang_cmd",
            )
        return BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=BisectStatus.FAIL,
            exit_code=1,
            stdout="",
            stderr="AssertionError",
            duration_seconds=0.1,
            command="hang_cmd",
        )
    mock_evaluator.evaluate.side_effect = mock_eval

    engine = BisectEngine(
        session=recorder.session,
        ledger=recorder.ledger,
        evaluator=mock_evaluator,
    )
    report = engine.run()
    assert report.classification == RegressionClassification.INCONCLUSIVE
    assert report.last_good_step is None
    assert "INCONCLUSIVE" in report.divergence_reason


def test_bisect_engine_single_step_trajectories(temp_workspace):
    """
    Regression test: BisectEngine should handle single-step sessions correctly.
    """
    from unittest.mock import MagicMock
    from agentbisect.core.models import BisectStepResult, RegressionClassification

    recorder = LiveRecorder(temp_workspace, session_id="single_step_session")
    f = temp_workspace / "file.py"
    f.write_text("a = 1", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    # Case A: Step 1 PASSES
    pass_evaluator = MagicMock()
    pass_evaluator.name = "mock_pass"
    pass_evaluator.evaluate.return_value = BisectStepResult(
        step_number=1,
        commit_hash="c1",
        status=BisectStatus.PASS,
        exit_code=0,
        stdout="OK",
        stderr="",
        duration_seconds=0.1,
        command="test",
    )
    engine_pass = BisectEngine(session=recorder.session, ledger=recorder.ledger, evaluator=pass_evaluator)
    report_pass = engine_pass.run()
    assert report_pass.classification == RegressionClassification.NO_REGRESSION
    assert report_pass.last_good_step is not None
    assert report_pass.first_bad_step is None

    # Case B: Step 1 FAILS
    fail_evaluator = MagicMock()
    fail_evaluator.name = "mock_fail"
    fail_evaluator.evaluate.return_value = BisectStepResult(
        step_number=1,
        commit_hash="c1",
        status=BisectStatus.FAIL,
        exit_code=1,
        stdout="",
        stderr="Failed",
        duration_seconds=0.1,
        command="test",
    )
    engine_fail = BisectEngine(session=recorder.session, ledger=recorder.ledger, evaluator=fail_evaluator)
    report_fail = engine_fail.run()
    assert report_fail.classification == RegressionClassification.BROKEN_BASELINE
    assert report_fail.last_good_step is None
    assert report_fail.first_bad_step is not None


def test_bisect_engine_step_evaluation_memoization(temp_workspace):
    """
    Verifies that BisectEngine caches evaluations so steps are not evaluated redundantly.
    """
    recorder = LiveRecorder(temp_workspace, session_id="memoization_session")
    f = temp_workspace / "calc.py"
    for i in range(1, 6):
        f.write_text(f"x = {i}\n", encoding="utf-8")
        recorder.record_step(tool_name="edit_file")

    from unittest.mock import MagicMock
    from agentbisect.core.models import BisectStepResult

    call_counts = {}
    mock_evaluator = MagicMock()
    mock_evaluator.name = "mock_cached"
    def mock_eval(step_number, commit_hash, workspace_root):
        call_counts[step_number] = call_counts.get(step_number, 0) + 1
        status = BisectStatus.PASS if step_number < 3 else BisectStatus.FAIL
        return BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=status,
            exit_code=0 if status == BisectStatus.PASS else 1,
            stdout="",
            stderr="",
            duration_seconds=0.01,
            command="test",
        )
    mock_evaluator.evaluate.side_effect = mock_eval

    engine = BisectEngine(session=recorder.session, ledger=recorder.ledger, evaluator=mock_evaluator)
    report = engine.run(verify_monotonicity=True)
    assert report.is_found()
    assert report.first_bad_step.step_number == 3

    # Every step must have been evaluated at most once
    for step_num, count in call_counts.items():
        assert count == 1, f"Step {step_num} was evaluated {count} times (expected 1 with memoization)"


def test_bisect_engine_verify_endpoints_false_never_reports_confirmed_on_broken_baseline(temp_workspace):
    """
    Adversarial test: When verify_endpoints=False and all steps fail (broken baseline),
    the engine must NEVER report CONFIRMED. It must report BROKEN_BASELINE
    because no good baseline step was ever verified.
    """
    from unittest.mock import MagicMock
    from agentbisect.core.models import BisectStepResult, RegressionClassification

    recorder = LiveRecorder(temp_workspace, session_id="broken_baseline_no_verify")
    f = temp_workspace / "code.py"
    for i in range(1, 6):
        f.write_text(f"val = {i}\n", encoding="utf-8")
        recorder.record_step(tool_name="edit_file")

    mock_eval = MagicMock()
    mock_eval.name = "mock_all_fail"
    mock_eval.evaluate.side_effect = lambda step_number, commit_hash, workspace_root, **kw: BisectStepResult(
        step_number=step_number,
        commit_hash=commit_hash,
        status=BisectStatus.FAIL,
        exit_code=1,
        stdout="",
        stderr="Test broken from step 1",
        duration_seconds=0.01,
        command="test",
    )

    engine = BisectEngine(session=recorder.session, ledger=recorder.ledger, evaluator=mock_eval)
    report = engine.run(verify_endpoints=False)
    assert report.classification != RegressionClassification.CONFIRMED, (
        "Engine reported CONFIRMED regression despite no baseline step passing!"
    )
    assert report.classification == RegressionClassification.BROKEN_BASELINE
    assert report.last_good_step is None


def test_bisect_engine_restoration_guarantee_after_evaluator_exception(temp_workspace):
    """
    Adversarial test: If the evaluator raises an unexpected exception midway through bisect,
    the workspace must still be restored safely via the finally block.
    """
    from unittest.mock import MagicMock
    recorder = LiveRecorder(temp_workspace, session_id="eval_exception_session")
    f = temp_workspace / "data.py"
    f.write_text("initial state\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file")

    f.write_text("step 2 state\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file")

    # Leave an uncommitted edit in workspace
    f.write_text("uncommitted working copy\n", encoding="utf-8")

    mock_eval = MagicMock()
    mock_eval.name = "mock_crasher"
    mock_eval.evaluate.side_effect = RuntimeError("Fatal hardware crash during test!")

    engine = BisectEngine(session=recorder.session, ledger=recorder.ledger, evaluator=mock_eval)
    try:
        engine.run(verify_endpoints=False)
    except Exception:
        pass

    assert f.read_text(encoding="utf-8") == "uncommitted working copy\n", (
        "Workspace uncommitted work was not restored after evaluator crash!"
    )


def test_bisect_engine_cache_lifetime_scoped_to_run_and_immutable(temp_workspace):
    """
    Cache scoping test:
    1. Cache lifetime is limited to the intended run and reset on each run().
    2. Cached results are returned as deep copies so mutation doesn't affect cache.
    """
    from unittest.mock import MagicMock
    from agentbisect.core.models import BisectStepResult

    recorder = LiveRecorder(temp_workspace, session_id="cache_scope_test")
    f = temp_workspace / "test.py"
    for i in range(1, 4):
        f.write_text(f"x = {i}\n", encoding="utf-8")
        recorder.record_step(tool_name="edit_file")

    eval_calls = []
    mock_eval = MagicMock()
    mock_eval.name = "mock_scoper"
    def eval_fn(step_number, commit_hash, workspace_root, **kw):
        eval_calls.append(step_number)
        return BisectStepResult(
            step_number=step_number,
            commit_hash=commit_hash,
            status=BisectStatus.PASS if step_number == 1 else BisectStatus.FAIL,
            exit_code=0 if step_number == 1 else 1,
            stdout="clean output",
            stderr="",
            duration_seconds=0.01,
            command="test_cmd",
        )
    mock_eval.evaluate.side_effect = eval_fn

    engine = BisectEngine(session=recorder.session, ledger=recorder.ledger, evaluator=mock_eval)

    # First run
    report1 = engine.run()
    assert report1.is_found()
    assert report1.first_bad_step.step_number == 2
    count_run1 = len(report1.steps_evaluated)

    # Mutate a result in report1
    report1.steps_evaluated[0].stdout = "MUTATED_BY_CONSUMER"

    # Second run on the same engine instance: cache must be scoped, steps_evaluated must NOT leak
    report2 = engine.run()
    assert len(report2.steps_evaluated) == count_run1, "Steps from run 1 leaked into run 2!"
    assert report2.steps_evaluated[0].stdout == "clean output", "Cached result was mutated by consumer!"
