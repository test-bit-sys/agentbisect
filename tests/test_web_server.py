"""
Unit tests for Local Web UI server endpoints.
"""

import json
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import pytest
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.report.server import create_handler_class


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_web_ui_endpoints(temp_workspace):
    # Setup session with 1 step
    recorder = LiveRecorder(temp_workspace, session_id="test_web_session")
    f1 = temp_workspace / "f1.py"
    f1.write_text("x = 1\n", encoding="utf-8")
    recorder.record_step(tool_name="write_file", files_affected=["f1.py"])

    handler_cls = create_handler_class(temp_workspace)
    # Bind to port 0 for random free port
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # Test GET /api/status
        with urllib.request.urlopen(f"{base_url}/api/status") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["session_id"] == "test_web_session"
            assert data["total_steps"] == 1

        # Test GET /api/steps
        with urllib.request.urlopen(f"{base_url}/api/steps") as resp:
            assert resp.status == 200
            steps = json.loads(resp.read().decode("utf-8"))
            assert len(steps) == 1
            assert steps[0]["step_number"] == 1

        # Test GET /api/step/1
        with urllib.request.urlopen(f"{base_url}/api/step/1") as resp:
            assert resp.status == 200
            step_detail = json.loads(resp.read().decode("utf-8"))
            assert step_detail["step_number"] == 1
            assert "diff" in step_detail

        # Test GET / (HTML Dashboard)
        with urllib.request.urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            html_text = resp.read().decode("utf-8")
            assert "AgentBisect Dashboard" in html_text

        # Test POST /api/bisect
        bisect_req = urllib.request.Request(
            f"{base_url}/api/bisect",
            data=json.dumps({"test_command": "python -c 'exit(0)'"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(bisect_req) as resp:
            assert resp.status == 200
            bisect_data = json.loads(resp.read().decode("utf-8"))
            assert "classification" in bisect_data
            assert "session_id" in bisect_data

        # Test POST /api/fork
        fork_req = urllib.request.Request(
            f"{base_url}/api/fork",
            data=json.dumps({"target_step": 1, "hint": "test hint"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(fork_req) as resp:
            assert resp.status == 200
            fork_data = json.loads(resp.read().decode("utf-8"))
            assert fork_data["forked_step_number"] == 1
            assert "prompt_file_path" in fork_data

    finally:
        server.shutdown()
        server.server_close()
