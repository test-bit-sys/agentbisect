"""
Unit tests for Evaluators.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.core.models import BisectStatus
from agentbisect.evaluators.regex import RegexEvaluator


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_regex_evaluator(temp_workspace):
    target = temp_workspace / "config.env"
    target.write_text("DEBUG=True\nSECRET=12345", encoding="utf-8")

    # Positive match
    evaluator_pass = RegexEvaluator(target_file_pattern="*.env", required_regex=r"SECRET=\d+")
    res_pass = evaluator_pass.evaluate(step_number=1, commit_hash="dummy", workspace_root=temp_workspace)
    assert res_pass.status == BisectStatus.PASS

    # Negative match
    evaluator_fail = RegexEvaluator(target_file_pattern="*.env", required_regex=r"MISSING_TOKEN")
    res_fail = evaluator_fail.evaluate(step_number=1, commit_hash="dummy", workspace_root=temp_workspace)
    assert res_fail.status == BisectStatus.FAIL
