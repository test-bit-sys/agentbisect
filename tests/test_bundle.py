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
