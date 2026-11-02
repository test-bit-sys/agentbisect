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
                        "retries": {
                            "type": "integer",
                            "description": "Retry attempts for flaky test handling (default 1).",
                            "default": 1,
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["binary", "heuristic"],
                            "description": "Search strategy (default 'binary').",
                            "default": "binary",
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

        try:
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
                test_cmd = arguments.get("test_command")
                if not test_cmd or not str(test_cmd).strip():
                    return {
                        "content": [{"type": "text", "text": "Error: 'test_command' argument is required and cannot be empty."}],
                        "isError": True,
                    }
                timeout = arguments.get("timeout_seconds", 60)
                retries = arguments.get("retries", 1)
                strategy = arguments.get("strategy", "binary")

                engine = BisectEngine(
                    session=self.session,
                    ledger=self.ledger,
                    test_command=test_cmd,
                    timeout_seconds=timeout,
                    retries=retries,
                    strategy=strategy,
                )
                report = engine.run()
                if report.is_found():
                    bad = report.first_bad_step
                    good = report.last_good_step
                    text_parts = [
                        f"Classification: {report.classification.value}",
                        f"Confidence: {int(report.confidence * 100)}%",
                        f"First faulty step found: Step #{bad.step_number}",
                        f"Action: {bad.summary()}",
                        f"Reason: {report.divergence_reason}",
                        f"Last good state: Step #{good.step_number if good else 0}",
                        f"Suggested recovery: Call agentbisect_rewind with target_step={good.step_number if good else 0}.",
                    ]
                    if report.non_monotonic_detected:
                        text_parts.append("\n[!] Non-monotonic trajectory detected: code regression was fixed later or multiple regressions occurred.")
                    if report.diagnostics:
                        text_parts.append("\nDiagnostics:\n" + "\n".join(f"- {d}" for d in report.diagnostics))
                    text_res = "\n".join(text_parts)
                else:
                    text_parts = [
                        f"Classification: {report.classification.value}",
                        report.divergence_reason or "No regression detected.",
                    ]
                    if report.diagnostics:
                        text_parts.append("\nDiagnostics:\n" + "\n".join(f"- {d}" for d in report.diagnostics))
                    text_res = "\n".join(text_parts)
                return {"content": [{"type": "text", "text": text_res}]}

            elif name == "agentbisect_rewind":
                target_step = arguments.get("target_step")
                if target_step is None:
                    return {
                        "content": [{"type": "text", "text": "Error: 'target_step' argument is required."}],
                        "isError": True,
                    }
                try:
                    target_step_int = int(target_step)
                except (ValueError, TypeError):
                    return {
                        "content": [{"type": "text", "text": f"Error: 'target_step' must be an integer, got: {target_step}"}],
                        "isError": True,
                    }

                hint = arguments.get("hint")
                fork_engine = ForkEngine(self.session, self.ledger)
                res = fork_engine.fork_to_step(target_step_num=target_step_int, custom_hint=hint)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Workspace rewound to Step #{target_step_int}.\nFork guidance:\n{res.generated_prompt}",
                        }
                    ]
                }

            elif name == "agentbisect_get_diff":
                step_num = arguments.get("step_number")
                if step_num is None:
                    return {
                        "content": [{"type": "text", "text": "Error: 'step_number' argument is required."}],
                        "isError": True,
                    }
                try:
                    step_num_int = int(step_num)
                except (ValueError, TypeError):
                    return {
                        "content": [{"type": "text", "text": f"Error: 'step_number' must be an integer, got: {step_num}"}],
                        "isError": True,
                    }

                diff = self.ledger.get_step_diff(step_num_int)
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

        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Execution error in {name}: {type(e).__name__}: {e}"}],
                "isError": True,
            }

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handles a single JSON-RPC request or notification according to MCP specification."""
        if not isinstance(request, dict):
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request: request must be a JSON object"},
            }

        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # Handle notifications: requests without an 'id' member or notifications/* methods
        if "id" not in request or (isinstance(method, str) and method.startswith("notifications/")):
            # JSON-RPC 2.0 & MCP: Server MUST NOT reply to notifications
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agentbisect", "version": "0.1.0"},
                },
            }
        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tool_definitions()},
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            result = self.handle_call_tool(tool_name, arguments)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    def run_stdio(self, in_stream=None, out_stream=None) -> None:
        """Runs the standard MCP JSON-RPC protocol over stdin/stdout."""
        stdin_stream = in_stream or sys.stdin
        stdout_stream = out_stream or sys.stdout

        while True:
            line = stdin_stream.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    err_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request: expected JSON object"},
                    }
                    stdout_stream.write(json.dumps(err_response) + "\n")
                    stdout_stream.flush()
                    continue

                response = self.handle_request(request)
                if response is not None:
                    stdout_stream.write(json.dumps(response) + "\n")
                    stdout_stream.flush()
            except json.JSONDecodeError as e:
                err_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
                stdout_stream.write(json.dumps(err_response) + "\n")
                stdout_stream.flush()
            except Exception as e:
                err_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                }
                stdout_stream.write(json.dumps(err_response) + "\n")
                stdout_stream.flush()


def main():
    server = AgentBisectMCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
