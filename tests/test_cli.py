"""
Unit and integration tests for AgentBisect CLI commands.
"""

import tempfile
from pathlib import Path
from click.testing import CliRunner
from agentbisect.cli import main
from agentbisect.adapters.live_recorder import LiveRecorder


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Git bisect for AI coding agents" in result.output
    assert "find" in result.output
    assert "fork" in result.output
    assert "snapshot" in result.output
    assert "doctor" in result.output


def test_cli_doctor():
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "Running AgentBisect System Diagnostics" in result.output
    assert "Python Version" in result.output


def test_cli_snapshot_and_status():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Snapshot in fresh workspace
        snap_res = runner.invoke(main, ["snapshot", "My test checkpoint", "-w", tmpdir])
        assert snap_res.exit_code == 0
        assert "Snapshot created" in snap_res.output

        # Status
        status_res = runner.invoke(main, ["status", "-w", tmpdir])
        assert status_res.exit_code == 0
        assert "Total Steps: 1" in status_res.output


def test_cli_find_missing_transcript():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(main, ["find", "pytest", "-w", tmpdir])
        assert result.exit_code == 1
        assert "No transcript file found" in result.output


def test_cli_bundle_export_and_import():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        # Create session with snapshot
        runner.invoke(main, ["snapshot", "Step 1", "-w", str(ws)])

        # Export bundle
        out_bundle = ws / "my_bundle.bisect.zip"
        exp_res = runner.invoke(main, ["bundle", "export", "-o", str(out_bundle), "-w", str(ws)])
        assert exp_res.exit_code == 0
        assert out_bundle.exists()

        # Import bundle into new dir
        target_dir = ws / "imported_ws"
        imp_res = runner.invoke(main, ["bundle", "import", str(out_bundle), str(target_dir)])
        assert imp_res.exit_code == 0
        assert (target_dir / ".agentbisect" / "current_session.json").exists()
