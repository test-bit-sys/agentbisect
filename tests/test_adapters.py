"""
Unit tests for Transcript Adapters.
"""

import json
import tempfile
from pathlib import Path
import pytest
from agentbisect.adapters import load_session
from agentbisect.adapters.antigravity import AntigravityAdapter
from agentbisect.adapters.claude_code import ClaudeCodeAdapter
from agentbisect.adapters.cline import ClineAdapter
from agentbisect.adapters.openhands import OpenHandsAdapter
from agentbisect.adapters.generic_json import GenericJsonAdapter


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_antigravity_adapter(temp_dir):
    transcript_file = temp_dir / "transcript.jsonl"
    lines = [
        {"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "Please implement feature X"},
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "thinking": "Creating main.py",
            "tool_calls": [{"name": "write_file", "args": {"path": "main.py", "content": "print(1)"}}],
        },
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    assert AntigravityAdapter.can_handle(transcript_file)
    session = load_session(transcript_file, temp_dir)
    assert len(session.steps) == 2
    assert session.metadata.framework == "antigravity"
    assert session.steps[1].tool_name == "write_file"


def test_claude_code_adapter(temp_dir):
    transcript_file = temp_dir / "session.claude.jsonl"
    lines = [
        {"type": "user_message", "message": "Fix the bug"},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "app.py", "text": "new code"}},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    assert ClaudeCodeAdapter.can_handle(transcript_file)
    session = load_session(transcript_file, temp_dir)
    assert len(session.steps) == 2
    assert session.metadata.framework == "claude_code"
    assert session.steps[1].tool_name == "Edit"


def test_cline_adapter(temp_dir):
    transcript_file = temp_dir / "cline_task_ui_messages.json"
    messages = [
        {"say": "user_feedback", "text": "Fix tests", "ts": 1234567890},
        {"say": "command", "text": "npm test", "ts": 1234567895},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        json.dump(messages, f)

    assert ClineAdapter.can_handle(transcript_file)
    session = load_session(transcript_file, temp_dir)
    assert len(session.steps) == 2
    assert session.metadata.framework == "cline"
    assert session.steps[0].step_type.value == "prompt_turn"
    assert session.steps[1].step_type.value == "command"


def test_openhands_adapter(temp_dir):
    transcript_file = temp_dir / "openhands_trajectory.jsonl"
    lines = [
        {"action": "edit", "args": {"path": "server.py", "content": "pass"}, "thought": "fixing"},
        {"action": "run", "args": {"command": "pytest"}},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    assert OpenHandsAdapter.can_handle(transcript_file)
    session = load_session(transcript_file, temp_dir)
    assert len(session.steps) == 2
    assert session.metadata.framework == "openhands"
    assert session.steps[0].files_affected == ["server.py"]


def test_generic_json_adapter(temp_dir):
    transcript_file = temp_dir / "custom_trajectory.jsonl"
    lines = [
        {"step_number": 1, "tool_name": "bash", "tool_args": {"command": "ls"}},
    ]
    with open(transcript_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    assert GenericJsonAdapter.can_handle(transcript_file)
    session = load_session(transcript_file, temp_dir)
    assert len(session.steps) == 1
    assert session.steps[0].tool_name == "bash"

