"""
Unit tests for ShadowLedger.
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.core.shadow_ledger import ShadowLedger


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_shadow_ledger_initialization(temp_workspace):
    ledger = ShadowLedger(temp_workspace)
    assert ledger.git_dir.exists()
    assert (ledger.git_dir / "HEAD").exists()


def test_snapshot_and_restore(temp_workspace):
    ledger = ShadowLedger(temp_workspace)

    # Step 1: Create file A
    file_a = temp_workspace / "a.txt"
    file_a.write_text("version 1", encoding="utf-8")
    commit_1 = ledger.snapshot_step(1, summary="Add a.txt")

    assert commit_1 is not None
    assert len(commit_1) == 40
    assert ledger.get_commit_for_step(1) == commit_1

    # Step 2: Modify file A and create file B
    file_a.write_text("version 2", encoding="utf-8")
    file_b = temp_workspace / "b.txt"
    file_b.write_text("hello b", encoding="utf-8")
    commit_2 = ledger.snapshot_step(2, summary="Update a.txt and add b.txt")

    assert commit_2 != commit_1
    assert ledger.get_commit_for_step(2) == commit_2

    # Verify diff
    diff = ledger.get_step_diff(2)
    assert "version 1" in diff
    assert "version 2" in diff

    # Restore back to step 1
    ledger.restore_step(1)
    assert file_a.read_text(encoding="utf-8") == "version 1"
    assert not file_b.exists()

    # Restore to step 2
    ledger.restore_step(2)
    assert file_a.read_text(encoding="utf-8") == "version 2"
    assert file_b.exists()
    assert file_b.read_text(encoding="utf-8") == "hello b"
