"""
Built-in realistic agent failure scenarios for instant playground demos.
"""

from __future__ import annotations

from pathlib import Path
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.models import AgentSession


def setup_demo_environment(target_dir: Path) -> AgentSession:
    """
    Sets up a realistic microservice workspace with 20 agent steps.
    Step 1: Working auth service and passing tests.
    Steps 2..11: Adding user models, db connectors, utilities (all passing).
    Step 12: Agent introduces bug in verify_token logic (REGRESSION).
    Steps 13..20: Agent adds more features unaware of the broken test.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = target_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    recorder = LiveRecorder(workspace_root=target_dir, session_id="demo_auth_service", framework="antigravity")

    # Step 1: Baseline working service with test harness
    (target_dir / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (target_dir / "config.py").write_text("SECRET_KEY = 'supersecret'\nTOKEN_EXPIRY = 3600\n", encoding="utf-8")
    
    auth_code_v1 = """import time
import base64
import json

def create_token(user_id, expires_in=3600):
    payload = {"user_id": user_id, "exp": int(time.time()) + expires_in}
    return base64.b64encode(json.dumps(payload).encode()).decode()

def verify_token(token):
    try:
        raw = base64.b64decode(token.encode()).decode()
        data = json.loads(raw)
        if time.time() > data.get("exp", 0):
            return None
        return data
    except Exception:
        return None
"""
    (target_dir / "auth.py").write_text(auth_code_v1, encoding="utf-8")

    test_code = """import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
from auth import create_token, verify_token

def test_token_valid():
    token = create_token("user123")
    data = verify_token(token)
    assert data is not None
    assert data["user_id"] == "user123"

def test_token_expiration():
    token = create_token("user123", expires_in=-10)
    data = verify_token(token)
    assert data is None, "Expired token should not verify"

if __name__ == "__main__":
    test_token_valid()
    test_token_expiration()
    print("ALL TESTS PASSED")
"""
    (tests_dir / "test_auth.py").write_text(test_code, encoding="utf-8")
    (target_dir / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")

    recorder.record_step(
        tool_name="write_file",
        tool_args={"path": "auth.py"},
        agent_thought="Initial baseline: Implemented working create_token and verify_token functions",
        files_affected=["auth.py", "tests/test_auth.py", "config.py"],
    )

    # Steps 2 to 11: Agent builds user model, db connectors, hashing utils (all passing)
    for i in range(2, 12):
        util_file = target_dir / f"service_mod_{i}.py"
        util_file.write_text(f"# Component #{i}\ndef component_{i}():\n    return {i}\n", encoding="utf-8")
        recorder.record_step(
            tool_name="write_file",
            tool_args={"path": f"service_mod_{i}.py"},
            agent_thought=f"Implementing supporting microservice component #{i}",
            files_affected=[f"service_mod_{i}.py"],
        )

    # Step 12: THE REGRESSION! Agent hallucinates and refactors auth.py, breaking expiration check
    buggy_auth_code = """import time
import base64
import json

def create_token(user_id, expires_in=3600):
    payload = {"user_id": user_id, "exp": int(time.time()) + expires_in}
    return base64.b64encode(json.dumps(payload).encode()).decode()

def verify_token(token):
    try:
        raw = base64.b64decode(token.encode()).decode()
        data = json.loads(raw)
        # BUG INTRODUCED HERE: inverted logic (< instead of >)
        if time.time() < data.get("exp", 0):
            return None
        return data
    except Exception:
        return None
"""
    (target_dir / "auth.py").write_text(buggy_auth_code, encoding="utf-8")
    recorder.record_step(
        tool_name="edit_file",
        tool_args={"path": "auth.py"},
        agent_thought="Optimized token verification performance with early returns",
        files_affected=["auth.py"],
    )

    # Steps 13 to 20: Agent keeps adding features unaware of broken auth tests
    for i in range(13, 21):
        feature_file = target_dir / f"feature_{i}.py"
        feature_file.write_text(f"# Feature #{i}\ndef feature_{i}():\n    return 'feature_{i}'\n", encoding="utf-8")
        recorder.record_step(
            tool_name="write_file",
            tool_args={"path": f"feature_{i}.py"},
            agent_thought=f"Added analytics and telemetry feature #{i}",
            files_affected=[f"feature_{i}.py"],
        )

    return recorder.session
