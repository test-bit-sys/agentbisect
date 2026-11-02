"""
Unit tests for ForkEngine.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.fork_engine import ForkEngine


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_fork_engine_rollback_and_prompt(temp_workspace):
    recorder = LiveRecorder(temp_workspace, session_id="test_fork_session")

    target_file = temp_workspace / "service.py"

    # Step 1: Good version
    target_file.write_text("def run(): return 'good'\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file", files_affected=["service.py"])

    # Step 2: Broken version
    target_file.write_text("def run(): raise RuntimeError('broken')\n", encoding="utf-8")
    recorder.record_step(tool_name="edit_file", files_affected=["service.py"])

    assert "broken" in target_file.read_text(encoding="utf-8")

    # Execute fork to step 1
    fork_engine = ForkEngine(recorder.session, recorder.ledger)
    fork_result = fork_engine.fork_to_step(
        target_step_num=1,
        culprit_step_num=2,
        custom_hint="Preserve the clean return statement and do not raise RuntimeError.",
        error_message="RuntimeError: broken",
    )

    # Verify workspace files are restored
    assert target_file.read_text(encoding="utf-8") == "def run(): return 'good'\n"

    # Verify generated prompt
    assert Path(fork_result.prompt_file_path).exists()
    prompt_text = Path(fork_result.prompt_file_path).read_text(encoding="utf-8")
    assert "Step 1" in prompt_text
    assert "Step 2" in prompt_text
    assert "Preserve the clean return statement" in prompt_text
