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
