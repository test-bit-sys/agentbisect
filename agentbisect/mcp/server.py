"""
Model Context Protocol (MCP) server for AgentBisect.
Implements stdio JSON-RPC protocol exposing AgentBisect capabilities directly to AI agents.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.bisect_engine import BisectEngine
from agentbisect.core.fork_engine import ForkEngine
from agentbisect.core.models import AgentSession
from agentbisect.core.shadow_ledger import ShadowLedger


class AgentBisectMCPServer:
    """Stdio-based Model Context Protocol (MCP) Server for AgentBisect."""

    def __init__(self, workspace_root: Path | str = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self.ledger = ShadowLedger(self.workspace_root)
        self.session_file = self.workspace_root / ".agentbisect" / "current_session.json"
        self._load_or_init_session()

    def _load_or_init_session(self) -> None:
        if self.session_file.exists():
            try:
                self.session = AgentSession.load_json(self.session_file)
                return
            except Exception:
                pass
        # Initialize recorder
        rec = LiveRecorder(self.workspace_root)
        self.session = rec.session

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns tool schemas according to the MCP specification."""
        return [
            {
                "name": "agentbisect_snapshot",
                "description": "Snapshot the current workspace state to shadow git before or after performing changes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Short description of the action performed at this step.",
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of files touched.",
                        },
                    },
                    "required": ["summary"],
                },
            },
            {
                "name": "agentbisect_bisect",
                "description": "Run automated binary search over recorded steps to locate the exact step that broke the test command.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "test_command": {
                            "type": "string",
                            "description": "Command to run at each step, e.g. 'pytest' or 'npm test'.",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Max seconds to wait per test run (default 60).",
                            "default": 60,
                        },
                    },
                    "required": ["test_command"],
                },
            },
            {
                "name": "agentbisect_rewind",
                "description": "Rewind workspace files to a known good step and generate a post-mortem recovery prompt.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_step": {
                            "type": "integer",
                            "description": "The step number to roll back to.",
                        },
                        "hint": {
                            "type": "string",
                            "description": "Guidance hint for self-correction.",
                        },
                    },
                    "required": ["target_step"],
                },
            },
            {
                "name": "agentbisect_get_diff",
                "description": "Get the git diff introduced at a specific step.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "step_number": {
                            "type": "integer",
                            "description": "Step number to view diff for.",
                        },
                    },
                    "required": ["step_number"],
                },
            },
            {
                "name": "agentbisect_status",
                "description": "Inspect current session status, total recorded steps, and active checkpoints.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def handle_call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the requested tool and returns MCP tool response."""
        self._load_or_init_session()

        if name == "agentbisect_snapshot":
            summary = arguments.get("summary", "Checkpoint")
            files = arguments.get("files")
            recorder = LiveRecorder(self.workspace_root, session_id=self.session.metadata.session_id)
            step = recorder.record_step(tool_name="snapshot", agent_thought=summary, files_affected=files)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Snapshot created: Step #{step.step_number} [{step.commit_hash[:7]}].",
                    }
                ]
            }

        elif name == "agentbisect_bisect":
            test_cmd = arguments["test_command"]
            timeout = arguments.get("timeout_seconds", 60)
            engine = BisectEngine(
                session=self.session,
                ledger=self.ledger,
                test_command=test_cmd,
                timeout_seconds=timeout,
            )
            report = engine.run()
            if report.is_found():
                bad = report.first_bad_step
                good = report.last_good_step
                text_res = (
                    f"First faulty step found: Step #{bad.step_number}\n"
                    f"Action: {bad.summary()}\n"
                    f"Reason: {report.divergence_reason}\n"
                    f"Last good state: Step #{good.step_number if good else 0}\n"
                    f"Suggested recovery: Call agentbisect_rewind with target_step={good.step_number if good else 0}."
                )
            else:
                text_res = report.divergence_reason or "No regression detected."
            return {"content": [{"type": "text", "text": text_res}]}

        elif name == "agentbisect_rewind":
            target_step = arguments["target_step"]
            hint = arguments.get("hint")
            fork_engine = ForkEngine(self.session, self.ledger)
            res = fork_engine.fork_to_step(target_step_num=target_step, custom_hint=hint)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Workspace rewound to Step #{target_step}.\nFork guidance:\n{res.generated_prompt}",
                    }
                ]
            }

        elif name == "agentbisect_get_diff":
            step_num = arguments["step_number"]
            diff = self.ledger.get_step_diff(step_num)
            return {
                "content": [
                    {"type": "text", "text": diff if diff else "(No diff recorded for this step)"}
                ]
            }

        elif name == "agentbisect_status":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "session_id": self.session.metadata.session_id,
                                "total_steps": len(self.session.steps),
                                "workspace": str(self.workspace_root),
                            },
                            indent=2,
                        ),
                    }
                ]
            }

        raise ValueError(f"Unknown tool: {name}")

    def run_stdio(self) -> None:
        """Runs the standard MCP JSON-RPC protocol over stdin/stdout."""
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                req_id = request.get("id")
                method = request.get("method")
                params = request.get("params", {})

                if method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "agentbisect", "version": "0.1.0"},
                        },
                    }
                elif method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"tools": self.get_tool_definitions()},
                    }
                elif method == "tools/call":
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})
                    result = self.handle_call_tool(tool_name, arguments)
                    response = {"jsonrpc": "2.0", "id": req_id, "result": result}
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(err_response) + "\n")
                sys.stdout.flush()


def main():
    server = AgentBisectMCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
