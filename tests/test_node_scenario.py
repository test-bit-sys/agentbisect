"""
Integration test for Node.js scenario with native test runner.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.core.bisect_engine import BisectEngine
from agentbisect.core.shadow_ledger import ShadowLedger
from agentbisect.demo.scenarios_js import setup_node_demo_environment


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_node_demo_scenario_identifies_step_9(temp_workspace):
    session = setup_node_demo_environment(temp_workspace)
    assert len(session.steps) == 15

    ledger = ShadowLedger(temp_workspace)
    engine = BisectEngine(
        session=session,
        ledger=ledger,
        test_command="node --test",
        timeout_seconds=30,
    )

    report = engine.run()
    assert report.is_found()
    assert report.first_bad_step.step_number == 9
    assert report.last_good_step.step_number == 8
    assert report.evaluations_count <= 6
