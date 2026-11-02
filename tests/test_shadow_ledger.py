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


def test_shadow_ledger_lock(temp_workspace):
    ledger = ShadowLedger(temp_workspace)
    with ledger.lock(timeout_seconds=2):
        # Trying to acquire lock concurrently should timeout
        with pytest.raises(TimeoutError, match="Could not acquire shadow ledger lock"):
            with ledger.lock(timeout_seconds=0.1):
                pass

    # Lock file must be cleanly released
    lock_file = ledger.ledger_dir / "agentbisect.lock"
    assert not lock_file.exists()


def test_restore_preserves_user_git_directory(temp_workspace):
    # Simulate a user repository with an existing .git folder
    user_git = temp_workspace / ".git"
    user_git.mkdir()
    config_file = user_git / "config"
    config_file.write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")

    ledger = ShadowLedger(temp_workspace)
    doc = temp_workspace / "doc.txt"
    doc.write_text("initial", encoding="utf-8")
    ledger.snapshot_step(1, summary="Step 1")

    doc.write_text("updated", encoding="utf-8")
    extra = temp_workspace / "temp.txt"
    extra.write_text("extra", encoding="utf-8")
    ledger.snapshot_step(2, summary="Step 2")

    # Restore step 1 (which runs git clean)
    ledger.restore_step(1)

    # Critical safety assertion: user's .git MUST be preserved!
    assert user_git.exists(), "User's .git was wiped by restore_step!"
    assert config_file.exists()
    assert config_file.read_text(encoding="utf-8") == "[core]\nrepositoryformatversion = 0\n"
    assert not extra.exists()


def test_stash_and_restore_worktree(temp_workspace):
    ledger = ShadowLedger(temp_workspace)
    f = temp_workspace / "app.py"
    f.write_text("v1", encoding="utf-8")
    ledger.snapshot_step(1, summary="Step 1")

    # Modify file without snapshotting
    f.write_text("uncommitted work", encoding="utf-8")

    # Stash
    stashed = ledger.stash_worktree()
    assert stashed is True

    # Restore step 1
    ledger.restore_step(1)
    assert f.read_text(encoding="utf-8") == "v1"

    # Restore stash
    ledger.restore_stash()
    assert f.read_text(encoding="utf-8") == "uncommitted work"

