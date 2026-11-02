"""
Unit tests for Evaluators.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.core.models import BisectStatus
from agentbisect.evaluators.command import CommandEvaluator
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
    assert len(res_pass.attempts) == 1

    # Negative match
    evaluator_fail = RegexEvaluator(target_file_pattern="*.env", required_regex=r"MISSING_TOKEN")
    res_fail = evaluator_fail.evaluate(step_number=1, commit_hash="dummy", workspace_root=temp_workspace)
    assert res_fail.status == BisectStatus.FAIL


def test_command_evaluator_pass_and_fail(temp_workspace):
    eval_pass = CommandEvaluator(command='python -c "exit(0)"', timeout_seconds=5)
    res_pass = eval_pass.evaluate(step_number=1, commit_hash="c1", workspace_root=temp_workspace)
    assert res_pass.status == BisectStatus.PASS
    assert res_pass.exit_code == 0
    assert not res_pass.is_flaky

    eval_fail = CommandEvaluator(command='python -c "exit(42)"', timeout_seconds=5)
    res_fail = eval_fail.evaluate(step_number=2, commit_hash="c2", workspace_root=temp_workspace)
    assert res_fail.status == BisectStatus.FAIL
    assert res_fail.exit_code == 42


def test_command_evaluator_timeout_inconclusive(temp_workspace):
    # Command that sleeps longer than timeout should return INCONCLUSIVE, not code regression FAIL
    eval_timeout = CommandEvaluator(
        command='python -c "import time; time.sleep(2)"',
        timeout_seconds=1,
    )
    res = eval_timeout.evaluate(step_number=3, commit_hash="c3", workspace_root=temp_workspace)
    assert res.status == BisectStatus.INCONCLUSIVE
    assert "timed out" in res.stderr.lower()


def test_command_evaluator_flaky_retry_tracking(temp_workspace):
    # Flaky script: fails on first run, passes on second run
    flaky_script = temp_workspace / "flaky.py"
    marker = temp_workspace / "marker.tmp"
    flaky_script.write_text(
        "import sys, pathlib\n"
        "p = pathlib.Path('marker.tmp')\n"
        "if not p.exists():\n"
        "    p.write_text('ran')\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )

    eval_flaky = CommandEvaluator(
        command="python flaky.py",
        timeout_seconds=5,
        retries=2,
        stability_policy="majority",
    )
    res = eval_flaky.evaluate(step_number=4, commit_hash="c4", workspace_root=temp_workspace)
    assert len(res.attempts) == 2
    assert res.is_flaky is True
    assert res.attempts[0].status == BisectStatus.FAIL
    assert res.attempts[1].status == BisectStatus.PASS

