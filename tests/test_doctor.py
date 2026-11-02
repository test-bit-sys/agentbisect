"""
Unit tests for SystemDoctor pre-flight diagnostics.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.core.doctor import SystemDoctor


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_doctor_diagnostics(temp_workspace):
    checks = SystemDoctor.run_diagnostics(temp_workspace)
    assert len(checks) >= 4

    names = [name for name, ok, msg in checks]
    assert "Python Version" in names
    assert "Git Executable" in names
    assert "Workspace Permissions" in names

    # Python version should pass on modern python
    py_check = next(c for c in checks if c[0] == "Python Version")
    assert py_check[1] is True
