"""
Zero-dependency, high-performance Web UI Server for AgentBisect:
Uses Python standard library ThreadingHTTPServer.
Provides an interactive browser dashboard for exploring agent sessions,
running visual bisects, inspecting diffs, and forking trajectories.
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.bisect_engine import BisectEngine
from agentbisect.core.fork_engine import ForkEngine
from agentbisect.core.models import AgentSession
from agentbisect.core.shadow_ledger import ShadowLedger


def create_handler_class(workspace_root: Path | str = "."):
    ws_path = Path(workspace_root).resolve()

    class AgentBisectRequestHandler(SimpleHTTPRequestHandler):
        def _get_ledger(self) -> ShadowLedger:
            return ShadowLedger(ws_path)

        def _get_session(self) -> AgentSession:
            session_file = ws_path / ".agentbisect" / "current_session.json"
            if session_file.exists():
                return AgentSession.load_json(session_file)
            recorder = LiveRecorder(ws_path)
            return recorder.session

        def _send_json(self, data: Any, status_code: int = 200) -> None:
            raw = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(raw)

        def _send_html(self, html_str: str, status_code: int = 200) -> None:
            raw = html_str.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path in ("", "/"):
                self._send_html(self._render_dashboard_html())
            elif path == "/api/status":
                session = self._get_session()
                self._send_json({
                    "session_id": session.metadata.session_id,
                    "framework": session.metadata.framework,
                    "workspace": str(ws_path),
                    "total_steps": len(session.steps),
                    "created_at": session.metadata.created_at,
                })
            elif path == "/api/steps":
                session = self._get_session()
                steps = [
                    {
                        "step_number": s.step_number,
                        "step_id": s.step_id,
                        "summary": s.summary(),
                        "tool_name": s.tool_name,
                        "files_affected": s.files_affected,
                        "timestamp": s.timestamp,
                        "commit_hash": s.commit_hash,
                    }
                    for s in session.steps
                ]
                self._send_json(steps)
            elif path.startswith("/api/step/"):
                step_str = path.split("/api/step/")[1].strip("/")
                try:
                    step_num = int(step_str)
                    session = self._get_session()
                    step = session.get_step(step_num)
                    if not step:
                        self._send_json({"error": "Step not found"}, status_code=404)
                        return

                    ledger = self._get_ledger()
                    diff = ledger.get_step_diff(step_num)
                    affected = ledger.get_affected_files(step_num)

                    data = step.model_dump()
                    data["diff"] = diff
                    data["files_affected"] = affected or step.files_affected
                    self._send_json(data)
                except ValueError:
                    self._send_json({"error": "Invalid step number"}, status_code=400)
            else:
                self._send_json({"error": "Not found"}, status_code=404)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body) if body else {}

            if path == "/api/bisect":
                cmd = payload.get("test_command")
                if not cmd:
                    self._send_json({"error": "test_command required"}, status_code=400)
                    return
                timeout = payload.get("timeout_seconds", 60)
                session = self._get_session()
                ledger = self._get_ledger()

                if len(session.steps) == 0:
                    self._send_json({"error": "No steps in session to bisect"}, status_code=400)
                    return

                engine = BisectEngine(
                    session=session,
                    ledger=ledger,
                    test_command=cmd,
                    timeout_seconds=timeout,
                )
                report = engine.run()
                self._send_json(report.model_dump())

            elif path == "/api/fork":
                target = payload.get("target_step")
                hint = payload.get("hint")
                if target is None:
                    self._send_json({"error": "target_step required"}, status_code=400)
                    return

                session = self._get_session()
                ledger = self._get_ledger()
                fork_engine = ForkEngine(session, ledger)

                try:
                    res = fork_engine.fork_to_step(target_step_num=int(target), custom_hint=hint)
                    self._send_json(res.model_dump())
                except Exception as e:
                    self._send_json({"error": str(e)}, status_code=400)

            elif path == "/api/snapshot":
                summary = payload.get("summary", "Checkpoint")
                files = payload.get("files")
                recorder = LiveRecorder(ws_path)
                step = recorder.record_step(
                    tool_name="ui_snapshot",
                    agent_thought=summary,
                    files_affected=files,
                )
                self._send_json({"status": "ok", "step_number": step.step_number, "commit": step.commit_hash})
            else:
                self._send_json({"error": "Endpoint not found"}, status_code=404)

        def _render_dashboard_html(self) -> str:
            return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentBisect Dashboard</title>
    <style>
        :root {
            --bg: #090d16;
            --panel: #111827;
            --border: #1f2937;
            --accent: #38bdf8;
            --text: #f9fafb;
            --text-muted: #9ca3af;
            --green: #22c55e;
            --red: #ef4444;
            --orange: #f97316;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 340px; background: var(--panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
        .sidebar-header { padding: 1.2rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 1.2rem; font-weight: bold; color: var(--accent); display: flex; align-items: center; gap: 0.5rem; }
        .step-list { flex-grow: 1; overflow-y: auto; padding: 0.8rem; }
        .step-item { padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 0.5rem; background: #1a2234; border: 1px solid var(--border); cursor: pointer; transition: 0.15s; }
        .step-item:hover { border-color: var(--accent); background: #1e293b; }
        .step-item.active { border-color: var(--accent); background: #0e304f; }
        .step-item-title { display: flex; justify-content: space-between; font-weight: 600; font-size: 0.9rem; }
        .step-item-meta { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem; }
        .main-content { flex-grow: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar { padding: 1rem 1.5rem; background: var(--panel); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
        .bisect-bar { display: flex; align-items: center; gap: 0.8rem; width: 65%; }
        .input-test { flex-grow: 1; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem 1rem; color: #fff; font-family: monospace; font-size: 0.9rem; }
        .btn { background: var(--accent); color: #000; border: none; border-radius: 6px; padding: 0.6rem 1.2rem; font-weight: 600; cursor: pointer; }
        .btn:hover { opacity: 0.9; }
        .btn-fork { background: var(--orange); color: #fff; }
        .view-pane { flex-grow: 1; overflow-y: auto; padding: 1.5rem; }
        .diff-box { background: #0b1120; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-top: 1rem; }
        .diff-header { background: #162032; padding: 0.6rem 1rem; font-family: monospace; font-size: 0.85rem; color: var(--text-muted); }
        pre { margin: 0; padding: 1rem; font-family: monospace; font-size: 0.85rem; overflow-x: auto; color: #e2e8f0; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="logo">⚡ AgentBisect</div>
            <span id="step-count" style="font-size: 0.85rem; color: var(--text-muted);">- Steps</span>
        </div>
        <div class="step-list" id="step-list"></div>
    </div>

    <div class="main-content">
        <div class="topbar">
            <div class="bisect-bar">
                <input type="text" id="test-cmd" class="input-test" placeholder="Test command, e.g. pytest tests/ or npm test" value="pytest">
                <button class="btn" onclick="runBisect()">Run Bisect</button>
            </div>
            <div>
                <button class="btn btn-fork" onclick="forkCurrentStep()">Fork From This Step</button>
            </div>
        </div>

        <div class="view-pane" id="view-pane">
            <h2>Select a step on the left to inspect diff and execution details.</h2>
        </div>
    </div>

    <script>
        let currentStepNumber = null;

        async function loadSteps() {
            const res = await fetch('/api/steps');
            const steps = await res.json();
            document.getElementById('step-count').innerText = `${steps.length} Steps`;
            const list = document.getElementById('step-list');
            list.innerHTML = '';

            steps.forEach(s => {
                const item = document.createElement('div');
                item.className = 'step-item';
                item.id = `step-item-${s.step_number}`;
                item.innerHTML = `
                    <div class="step-item-title">
                        <span>#${s.step_number} ${s.summary}</span>
                    </div>
                    <div class="step-item-meta">${s.files_affected.join(', ') || 'No files'}</div>
                `;
                item.onclick = () => selectStep(s.step_number);
                list.appendChild(item);
            });

            if (steps.length > 0 && !currentStepNumber) {
                selectStep(steps[steps.length - 1].step_number);
            }
        }

        async function selectStep(num) {
            currentStepNumber = num;
            document.querySelectorAll('.step-item').forEach(el => el.classList.remove('active'));
            const activeEl = document.getElementById(`step-item-${num}`);
            if (activeEl) activeEl.classList.add('active');

            const res = await fetch(`/api/step/${num}`);
            const data = await res.json();

            const pane = document.getElementById('view-pane');
            pane.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <div>
                        <h2>Step #${data.step_number}: ${data.tool_name || 'Action'}</h2>
                        <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.3rem;">Commit: <code>${data.commit_hash || 'N/A'}</code></p>
                    </div>
                    <button class="btn btn-fork" onclick="forkCurrentStep()">Fork Step #${data.step_number}</button>
                </div>

                ${data.agent_thought ? `<div style="background: #1e293b; padding: 1rem; border-radius: 6px; margin-bottom: 1rem;"><strong>Agent Thought:</strong> ${data.agent_thought}</div>` : ''}

                <div class="diff-box">
                    <div class="diff-header">Unified Diff (${data.files_affected.join(', ') || 'Files'})</div>
                    <pre><code>${data.diff || '(No diff recorded for this step)'}</code></pre>
                </div>
            `;
        }

        async function runBisect() {
            const cmd = document.getElementById('test-cmd').value;
            if (!cmd) return alert('Enter a test command.');
            const pane = document.getElementById('view-pane');
            pane.innerHTML = `<h2>Running Binary Search against: <code>${cmd}</code>...</h2><p style="color: var(--text-muted);">Testing step checkpoints...</p>`;

            try {
                const res = await fetch('/api/bisect', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ test_command: cmd })
                });
                const report = await res.json();
                
                if (report.first_bad_step) {
                    pane.innerHTML = `
                        <div style="background: rgba(249, 115, 22, 0.15); border: 2px solid var(--orange); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
                            <h2 style="color: var(--orange);">🎯 Culprit Located: Step #${report.first_bad_step.step_number}</h2>
                            <p style="margin: 0.5rem 0;"><strong>Action:</strong> ${report.first_bad_step.tool_name}</p>
                            <p style="margin: 0.5rem 0;"><strong>Divergence Reason:</strong> ${report.divergence_reason}</p>
                            <p style="margin: 0.5rem 0;"><strong>Last Good State:</strong> Step #${report.last_good_step ? report.last_good_step.step_number : 0}</p>
                            <button class="btn btn-fork" style="margin-top: 1rem;" onclick="forkStep(${report.last_good_step ? report.last_good_step.step_number : 0})">Rewind to Last Good Step</button>
                        </div>
                    `;
                } else {
                    pane.innerHTML = `<div style="padding: 2rem;"><h2>${report.divergence_reason || 'No regression detected.'}</h2></div>`;
                }
            } catch (err) {
                alert('Bisect failed: ' + err);
            }
        }

        async function forkCurrentStep() {
            if (!currentStepNumber) return;
            forkStep(currentStepNumber);
        }

        async function forkStep(num) {
            const hint = prompt(`Enter optional guidance hint for the agent at Step #${num}:`);
            const res = await fetch('/api/fork', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ target_step: num, hint: hint || '' })
            });
            const data = await res.json();
            alert(`Workspace rewound to Step #${num}! Fork prompt created at ${data.prompt_file_path}`);
        }

        loadSteps();
    </script>
</body>
</html>
"""

    return AgentBisectRequestHandler


def run_server(workspace_root: Path | str = ".", host: str = "127.0.0.1", port: int = 8765):
    """Starts the ThreadingHTTPServer."""
    handler_cls = create_handler_class(workspace_root)
    server = ThreadingHTTPServer((host, port), handler_cls)
    server.serve_forever()
