"""
Unit tests for ProcessWrapper.
"""

import sys
import tempfile
from pathlib import Path
import pytest
from agentbisect.core.process_wrapper import ProcessWrapper


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_process_wrapper_records_step(temp_workspace):
    wrapper = ProcessWrapper(temp_workspace)
    assert len(wrapper.recorder.session.steps) == 0

    # Run a command that touches a file
    test_file = temp_workspace / "wrapped_output.txt"
    cmd = [sys.executable, "-c", f"open(r'{test_file}', 'w').write('hello from wrapper')"]

    exit_code = wrapper.run_wrapped(cmd, step_summary="Execute wrapped python script")
    assert exit_code == 0
    assert test_file.exists()

    # Verify step was recorded
    assert len(wrapper.recorder.session.steps) == 1
    step = wrapper.recorder.session.steps[0]
    assert step.step_number == 1
    assert step.tool_name == "run_command"
