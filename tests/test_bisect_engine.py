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
