"""
Unit tests for BundleManager (export and import).
"""

import tempfile
from pathlib import Path
import pytest
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.bundle import BundleManager


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_bundle_export_and_import(temp_workspace):
    # Setup session with a step
    recorder = LiveRecorder(temp_workspace, session_id="bundle_test_session")
    f = temp_workspace / "main.py"
    f.write_text("print('hello')", encoding="utf-8")
    recorder.record_step(tool_name="write_file", files_affected=["main.py"])

    # Export bundle
    bundle_zip = temp_workspace / "export.bisect.zip"
    exported_path = BundleManager.export_bundle(temp_workspace, bundle_zip)
    assert exported_path.exists()
    assert exported_path.suffix == ".zip"

    # Import into clean target workspace
    with tempfile.TemporaryDirectory() as target_dir:
        imported_session = BundleManager.import_bundle(exported_path, target_dir)
        assert imported_session.metadata.session_id == "bundle_test_session"
        assert len(imported_session.steps) == 1
        assert (Path(target_dir) / ".agentbisect" / "current_session.json").exists()


def test_bundle_import_rejects_path_traversal(temp_workspace):
    import zipfile

    malicious_zip = temp_workspace / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as z:
        # Create an entry with path traversal attempt
        z.writestr("../../../malicious_file.txt", "pwned")

    target_ws = temp_workspace / "target"
    target_ws.mkdir()

    with pytest.raises(ValueError, match="Path traversal detected"):
        BundleManager.import_bundle(malicious_zip, target_ws)

    # Ensure file was not written outside workspace
    assert not (temp_workspace.parent / "malicious_file.txt").exists()


def test_bundle_import_rejects_files_outside_agentbisect(temp_workspace):
    import zipfile

    unsafe_zip = temp_workspace / "unsafe.zip"
    with zipfile.ZipFile(unsafe_zip, "w") as z:
        z.writestr("src/main.py", "malicious_payload = True")

    target_ws = temp_workspace / "target"
    target_ws.mkdir()

    with pytest.raises(ValueError, match="Bundle contains file outside .agentbisect"):
        BundleManager.import_bundle(unsafe_zip, target_ws)


def test_bundle_excludes_lock_files_and_uses_posix_paths(temp_workspace):
    """
    Regression test: Verifies that BundleManager excludes lock files and temporary
    files, and uses forward slashes in ZIP archive names per ZIP specification.
    """
    import zipfile

    recorder = LiveRecorder(temp_workspace, session_id="lock_test_session")
    recorder.record_step(tool_name="write_file")

    # Create a simulated lock file inside shadow_git
    lock_file = temp_workspace / ".agentbisect" / "shadow_git" / "agentbisect.lock"
    lock_file.write_text("12345\n", encoding="utf-8")

    # Export bundle into .agentbisect itself to verify self-exclusion
    bundle_path = temp_workspace / ".agentbisect" / "nested.bisect.zip"
    BundleManager.export_bundle(temp_workspace, bundle_path)

    with zipfile.ZipFile(bundle_path, "r") as z:
        names = z.namelist()
        for name in names:
            assert "\\" not in name, f"Backslash found in ZIP entry name: {name}"
            assert not name.endswith(".lock"), f"Lock file was packaged into bundle: {name}"
            assert "nested.bisect.zip" not in name, "Archive packaged itself recursively!"


def test_bundle_import_rejects_windows_drive_traversal(temp_workspace):
    """
    Security test: Bundle containing Windows drive-letter paths (e.g. C:payload.txt, C:\\payload.txt)
    must be rejected as path traversal across all operating systems.
    """
    import zipfile
    for i, bad_path in enumerate(["C:escape.txt", "C:\\escape.txt", "D:/escape.txt", "c:payload.txt"]):
        drive_zip = temp_workspace / f"drive_traversal_{i}.zip"
        with zipfile.ZipFile(drive_zip, "w") as z:
            z.writestr(bad_path, "payload")

        target_ws = temp_workspace / f"target_drive_{i}"
        target_ws.mkdir()

        with pytest.raises(ValueError, match="Path traversal detected in bundle entry"):
            BundleManager.import_bundle(drive_zip, target_ws)


def test_bundle_import_rejects_duplicate_entries(temp_workspace):
    """
    Security test: ZIP with duplicate entries must be rejected.
    """
    import zipfile
    dup_zip = temp_workspace / "duplicate.zip"
    with zipfile.ZipFile(dup_zip, "w") as z:
        z.writestr(".agentbisect/current_session.json", "{}")
        z.writestr(".agentbisect/current_session.json", "{}")

    target_ws = temp_workspace / "target_dup"
    target_ws.mkdir()

    with pytest.raises(ValueError, match="Duplicate entry detected in bundle"):
        BundleManager.import_bundle(dup_zip, target_ws)


def test_bundle_import_failure_does_not_corrupt_target_workspace(temp_workspace):
    """
    Integrity test: Failed import must NOT leave a partially extracted or corrupted
    .agentbisect directory in target_workspace.
    """
    import zipfile
    bad_zip = temp_workspace / "bad_session.zip"
    with zipfile.ZipFile(bad_zip, "w") as z:
        # Valid path but session is missing / invalid
        z.writestr(".agentbisect/random_file.txt", "hello")

    target_ws = temp_workspace / "target_clean"
    target_ws.mkdir()

    with pytest.raises(ValueError, match="Imported bundle did not contain a valid session"):
        BundleManager.import_bundle(bad_zip, target_ws)

    # target_ws / .agentbisect must NOT exist
    assert not (target_ws / ".agentbisect").exists(), (
        "Failed bundle import left partially extracted .agentbisect in workspace!"
    )


def test_bundle_import_preserves_existing_data_on_copy_failure(temp_workspace, monkeypatch):
    """
    Transactional test: If copy/replace fails midway while replacing an existing .agentbisect,
    the pre-existing .agentbisect must be cleanly rolled back and preserved.
    """
    import shutil
    from agentbisect.adapters.live_recorder import LiveRecorder

    # 1. Create a valid target workspace with an existing .agentbisect session
    target_ws = temp_workspace / "target_existing"
    target_ws.mkdir()
    recorder = LiveRecorder(target_ws, session_id="original_session_123")
    recorder.record_step(tool_name="write_file")
    original_session_file = target_ws / ".agentbisect" / "current_session.json"
    assert original_session_file.exists()
    original_content = original_session_file.read_text(encoding="utf-8")

    # 2. Create another valid workspace and export a new bundle
    source_ws = temp_workspace / "source_ws"
    source_ws.mkdir()
    source_rec = LiveRecorder(source_ws, session_id="new_incoming_session_456")
    source_rec.record_step(tool_name="write_file")
    bundle_zip = temp_workspace / "incoming.bisect.zip"
    BundleManager.export_bundle(source_ws, bundle_zip)

    # 3. Simulate failure during shutil.copytree into target_ws / .agentbisect
    real_copytree = shutil.copytree
    def failing_copytree(src, dst, *args, **kwargs):
        # Create a partial file before crashing
        Path(dst).mkdir(parents=True, exist_ok=True)
        (Path(dst) / "partial.tmp").write_text("corrupted", encoding="utf-8")
        raise IOError("Disk full or permission denied during copytree!")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)

    # 4. Attempt import: should fail and trigger rollback
    import pytest
    with pytest.raises(IOError, match="Disk full or permission denied"):
        BundleManager.import_bundle(bundle_zip, target_ws)

    # 5. Verify pre-existing data was completely preserved
    assert (target_ws / ".agentbisect").exists()
    assert not (target_ws / ".agentbisect" / "partial.tmp").exists()
    assert not (target_ws / ".agentbisect_backup").exists()
    assert original_session_file.read_text(encoding="utf-8") == original_content
