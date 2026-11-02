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



def test_snapshot_step_with_deleted_files_in_files_param(temp_workspace):
    """
    Regression test: When a file is deleted and passed in `files` parameter to
    snapshot_step, the deletion must be recorded in shadow git.
    """
    ledger = ShadowLedger(temp_workspace)
    victim = temp_workspace / "obsolete.txt"
    victim.write_text("to be deleted", encoding="utf-8")
    commit_1 = ledger.snapshot_step(1, summary="Create obsolete.txt")

    # Step 2: Delete the file and snapshot with explicit files parameter
    victim.unlink()
    commit_2 = ledger.snapshot_step(2, summary="Delete obsolete.txt", files=["obsolete.txt"])

    # Step diff must record the deletion
    diff = ledger.get_step_diff(2)
    assert "deleted file mode" in diff or "--- a/obsolete.txt" in diff

    # Restore step 1: file exists
    ledger.restore_step(1)
    assert victim.exists()
    assert victim.read_text(encoding="utf-8") == "to be deleted"

    # Restore step 2: file MUST be absent
    ledger.restore_step(2)
    assert not victim.exists()


def test_snapshot_step_with_absolute_and_nested_paths(temp_workspace):
    """
    Tests that snapshot_step handles absolute paths and nested directory paths in `files`.
    """
    ledger = ShadowLedger(temp_workspace)
    sub = temp_workspace / "nested" / "pkg"
    sub.mkdir(parents=True)
    mod = sub / "mod.py"
    mod.write_text("val = 42\n", encoding="utf-8")

    # Snapshot using absolute path
    commit_1 = ledger.snapshot_step(1, summary="Nested mod", files=[str(mod.resolve())])
    assert commit_1 is not None

    affected = ledger.get_affected_files(1)
    assert any("mod.py" in f for f in affected)


def test_restore_preserves_agentbisect_artifacts(temp_workspace):
    """
    Tests that AgentBisect internal artifacts like AGENT_FORK_PROMPT.md and
    agentbisect_report.html are preserved when restoring an earlier step.
    """
    ledger = ShadowLedger(temp_workspace)
    f = temp_workspace / "app.py"
    f.write_text("v1", encoding="utf-8")
    ledger.snapshot_step(1, summary="Step 1")

    f.write_text("v2", encoding="utf-8")
    ledger.snapshot_step(2, summary="Step 2")

    # Simulate artifacts created in workspace
    fork_prompt = temp_workspace / "AGENT_FORK_PROMPT.md"
    fork_prompt.write_text("# Fork prompt content", encoding="utf-8")
    html_report = temp_workspace / "agentbisect_report.html"
    html_report.write_text("<html>Report</html>", encoding="utf-8")

    # Restore step 1
    ledger.restore_step(1)
    assert f.read_text(encoding="utf-8") == "v1"
    assert fork_prompt.exists(), "AGENT_FORK_PROMPT.md was wiped by restore_step!"
    assert html_report.exists(), "agentbisect_report.html was wiped by restore_step!"


def test_shadow_ledger_handles_spaces_and_unicode_filenames(temp_workspace):
    """
    Adversarial test: Git quoting (core.quotePath) must not corrupt filenames
    with spaces and Unicode characters (e.g. emojis or accents).
    """
    ledger = ShadowLedger(temp_workspace)
    special_file = temp_workspace / "file with spaces and rocket 🚀.py"
    special_file.write_text("x = 100\n", encoding="utf-8")

    commit = ledger.snapshot_step(1, summary="Unicode file", files=[str(special_file.name)])
    assert commit is not None

    affected = ledger.get_affected_files(1)
    assert len(affected) == 1
    assert "file with spaces and rocket 🚀.py" in affected[0]
    assert not affected[0].startswith('"'), "Filename was C-quoted by git!"

    # Modify and snapshot step 2
    special_file.write_text("x = 200\n", encoding="utf-8")
    ledger.snapshot_step(2, summary="Update unicode", files=[str(special_file.name)])
    assert special_file.read_text(encoding="utf-8") == "x = 200\n"

    # Restore step 1
    ledger.restore_step(1)
    assert special_file.read_text(encoding="utf-8") == "x = 100\n"


def test_shadow_ledger_handles_directory_deletion(temp_workspace):
    """
    Adversarial test: When an agent deletes an entire directory, snapshot_step
    must remove the tracked directory contents from the index cleanly.
    """
    ledger = ShadowLedger(temp_workspace)
    pkg_dir = temp_workspace / "mypackage"
    pkg_dir.mkdir()
    (pkg_dir / "mod1.py").write_text("m1 = True\n", encoding="utf-8")
    (pkg_dir / "mod2.py").write_text("m2 = True\n", encoding="utf-8")

    ledger.snapshot_step(1, summary="Create package")

    # Delete the directory
    import shutil
    shutil.rmtree(pkg_dir)

    ledger.snapshot_step(2, summary="Delete package", files=["mypackage"])
    affected = ledger.get_affected_files(2)
    assert any("mod1.py" in f for f in affected)
    assert any("mod2.py" in f for f in affected)

    # Restore step 1: directory and its files must reappear
    ledger.restore_step(1)
    assert (pkg_dir / "mod1.py").exists()
    assert (pkg_dir / "mod2.py").exists()


def test_shadow_ledger_stash_and_restore_zero_initial_commits(temp_workspace):
    """
    Adversarial test: Stashing and restoring uncommitted files on a repository
    that has zero initial commits must cleanly restore untracked workspace state.
    """
    ledger = ShadowLedger(temp_workspace)
    # Working tree has an uncommitted file before any steps exist
    draft = temp_workspace / "draft.txt"
    draft.write_text("important uncommitted work\n", encoding="utf-8")

    stashed = ledger.stash_worktree()
    assert stashed is True

    # Restore stash with parent_commit=None
    ledger.restore_stash(parent_commit=None)
    assert draft.exists()
    assert draft.read_text(encoding="utf-8") == "important uncommitted work\n"
