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
