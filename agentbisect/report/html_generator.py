"""
HTML report generator for AgentBisect:
Produces a self-contained, interactive single-file HTML dashboard with timelines, diffs, and metrics.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional
from agentbisect.core.models import BisectReport, AgentSession, BisectStatus


class HTMLReportGenerator:
    """Generates a standalone, beautiful HTML dashboard report."""

    @staticmethod
    def generate(
        report: BisectReport,
        session: AgentSession,
        output_path: Path | str,
    ) -> Path:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        evaluated_map = {e.step_number: e for e in report.steps_evaluated}
        bad_num = report.first_bad_step.step_number if report.first_bad_step else None
        good_num = report.last_good_step.step_number if report.last_good_step else None

        # Prepare step items
        step_items_html = []
        for step in session.steps:
            num = step.step_number
            is_bad = (num == bad_num)
            is_good = (num == good_num)
            eval_res = evaluated_map.get(num)

            node_class = "step-untested"
            status_badge = '<span class="badge badge-untested">UNTESTED</span>'
            if eval_res:
                if eval_res.status == BisectStatus.PASS:
                    node_class = "step-pass"
                    status_badge = '<span class="badge badge-pass">PASS</span>'
                elif eval_res.status == BisectStatus.FAIL:
                    node_class = "step-fail"
                    status_badge = '<span class="badge badge-fail">FAIL</span>'

            if is_bad:
                node_class += " step-culprit"
                status_badge = '<span class="badge badge-culprit">FIRST BAD</span>'

            diff_html = ""
            if step.diff:
                escaped_diff = html.escape(step.diff)
                diff_html = f"""
                <div class="diff-container">
                    <div class="diff-header">Unified Diff (Step #{num})</div>
                    <pre><code>{escaped_diff}</code></pre>
                </div>
                """

            step_items_html.append(f"""
            <div class="step-card {node_class}" id="step-{num}">
                <div class="step-card-header" onclick="toggleStep({num})">
                    <div class="step-num">#{num}</div>
                    <div class="step-summary">
                        <strong>{html.escape(step.summary())}</strong>
                        <div class="step-meta">{html.escape(', '.join(step.files_affected) if step.files_affected else 'No files listed')}</div>
                    </div>
                    <div class="step-badge-wrap">
                        {status_badge}
                    </div>
                </div>
                <div class="step-card-body" id="step-body-{num}">
                    {f'<p><strong>Agent Thought:</strong> {html.escape(step.agent_thought)}</p>' if step.agent_thought else ''}
                    {diff_html}
                </div>
            </div>
            """)

        # Escape strings for template
        wasted_steps_str = str(report.waste_estimate.wasted_steps) if report.waste_estimate else "0"
        wasted_tokens_str = f"{report.waste_estimate.wasted_tokens:,}" if report.waste_estimate else "0"
        cost_saved_str = f"${report.waste_estimate.estimated_cost_usd:.2f}" if report.waste_estimate else "$0.00"
        time_saved_str = f"{report.waste_estimate.time_saved_minutes}m" if report.waste_estimate else "0m"

        culprit_banner = ""
        if report.is_found():
            non_mono_alert = ""
            if report.non_monotonic_detected:
                non_mono_alert = '<p style="color: #fca5a5; font-weight: bold; margin-top: 0.5rem;">⚠️ Non-monotonic trajectory detected: regressions were fixed later or multiple regressions occurred.</p>'

            diag_html = ""
            if report.diagnostics:
                diag_items = "".join(f"<li>{html.escape(d)}</li>" for d in report.diagnostics)
                diag_html = f'<div style="margin-top: 0.8rem; font-size: 0.9rem; color: #cbd5e1;"><strong>Diagnostics:</strong><ul style="margin-left: 1.2rem; margin-top: 0.3rem;">{diag_items}</ul></div>'

            culprit_banner = f"""
            <div class="alert-culprit">
                <h2>🎯 First Broken Step Located: Step #{bad_num}</h2>
                <p><strong>Classification:</strong> <span style="color: var(--accent); font-weight: bold;">{html.escape(report.classification.value)}</span> ({int(report.confidence * 100)}% confidence)</p>
                <p><strong>Action:</strong> {html.escape(report.first_bad_step.summary())}</p>
                <p><strong>Divergence Reason:</strong> {html.escape(report.divergence_reason or '')}</p>
                <p><strong>Last Good State:</strong> Step #{good_num}</p>
                {non_mono_alert}
                {diag_html}
            </div>
            """
        elif report.divergence_reason:
            culprit_banner = f"""
            <div class="alert-culprit" style="border-color: var(--card-border); background: var(--card-bg);">
                <h2>Notice: {html.escape(report.classification.value)}</h2>
                <p>{html.escape(report.divergence_reason)}</p>
            </div>
            """

        fork_prompt_escaped = html.escape(report.suggested_fork_prompt or "")

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentBisect Report - {html.escape(session.metadata.session_id)}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --pass-color: #22c55e;
            --fail-color: #ef4444;
            --culprit-color: #f97316;
            --accent: #38bdf8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: var(--bg); color: var(--text-main); padding: 2rem; line-height: 1.5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        
        /* Header */
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 1.5rem; margin-bottom: 2rem; }}
        .header h1 {{ font-size: 1.8rem; display: flex; align-items: center; gap: 0.5rem; color: var(--accent); }}
        .header .session-id {{ font-size: 0.9rem; color: var(--text-muted); background: var(--card-bg); padding: 0.3rem 0.8rem; border-radius: 6px; border: 1px solid var(--card-border); }}
        
        /* Metrics Grid */
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .metric-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 1.25rem; }}
        .metric-title {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }}
        .metric-value {{ font-size: 1.8rem; font-weight: bold; margin-top: 0.4rem; color: var(--text-main); }}
        .metric-value.highlight {{ color: var(--culprit-color); }}
        .metric-value.green {{ color: var(--pass-color); }}
        
        /* Culprit Alert */
        .alert-culprit {{ background: rgba(249, 115, 22, 0.15); border: 2px solid var(--culprit-color); border-radius: 10px; padding: 1.5rem; margin-bottom: 2rem; }}
        .alert-culprit h2 {{ color: var(--culprit-color); margin-bottom: 0.5rem; }}
        .alert-culprit p {{ margin: 0.3rem 0; }}
        
        /* Prompt Box */
        .prompt-box {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 1.5rem; margin-bottom: 2rem; }}
        .prompt-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .copy-btn {{ background: var(--accent); color: #000; border: none; padding: 0.4rem 1rem; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; }}
        .copy-btn:hover {{ opacity: 0.9; }}
        .prompt-content {{ background: #0b1120; padding: 1rem; border-radius: 6px; border: 1px solid #1e293b; font-family: monospace; font-size: 0.9rem; white-space: pre-wrap; }}
        
        /* Timeline Cards */
        .timeline-section {{ margin-top: 2rem; }}
        .timeline-section h3 {{ margin-bottom: 1rem; font-size: 1.3rem; }}
        .step-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; margin-bottom: 0.8rem; overflow: hidden; }}
        .step-card.step-pass {{ border-left: 5px solid var(--pass-color); }}
        .step-card.step-fail {{ border-left: 5px solid var(--fail-color); }}
        .step-card.step-culprit {{ border: 2px solid var(--culprit-color); border-left: 6px solid var(--culprit-color); background: #26191b; }}
        
        .step-card-header {{ padding: 1rem; display: flex; align-items: center; gap: 1rem; cursor: pointer; user-select: none; }}
        .step-num {{ font-weight: bold; font-size: 1.1rem; color: var(--accent); min-width: 45px; }}
        .step-summary {{ flex-grow: 1; }}
        .step-meta {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem; }}
        
        .badge {{ padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
        .badge-pass {{ background: rgba(34, 197, 94, 0.2); color: var(--pass-color); border: 1px solid var(--pass-color); }}
        .badge-fail {{ background: rgba(239, 68, 68, 0.2); color: var(--fail-color); border: 1px solid var(--fail-color); }}
        .badge-culprit {{ background: rgba(249, 115, 22, 0.3); color: var(--culprit-color); border: 1px solid var(--culprit-color); }}
        .badge-untested {{ background: rgba(148, 163, 184, 0.1); color: var(--text-muted); border: 1px solid var(--card-border); }}
        
        .step-card-body {{ display: none; padding: 1rem; border-top: 1px solid var(--card-border); background: #131c2e; }}
        .step-card-body.open {{ display: block; }}
        
        .diff-container {{ margin-top: 0.8rem; border-radius: 6px; overflow: hidden; border: 1px solid var(--card-border); }}
        .diff-header {{ background: #0b1120; padding: 0.5rem 1rem; font-size: 0.8rem; color: var(--text-muted); font-family: monospace; }}
        pre {{ margin: 0; padding: 1rem; background: #070c18; overflow-x: auto; font-size: 0.85rem; color: #e2e8f0; }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div>
                <h1>⚡ AgentBisect Report</h1>
                <p style="color: var(--text-muted); font-size: 0.95rem; margin-top: 0.3rem;">
                    Test: <code>{html.escape(report.test_command)}</code>
                </p>
            </div>
            <div class="session-id">{html.escape(session.metadata.session_id)}</div>
        </header>

        {culprit_banner}

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">First Bad Step</div>
                <div class="metric-value highlight">#{bad_num or 'N/A'}</div>
            </div>
            <div class="metric-card">
                <div class="metric-title">Evaluations Run</div>
                <div class="metric-value">{report.evaluations_count} <span style="font-size: 1rem; color: var(--text-muted);">of {report.total_steps}</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-title">Wasted Tokens Saved</div>
                <div class="metric-value green">~{wasted_tokens_str}</div>
            </div>
            <div class="metric-card">
                <div class="metric-title">Est. Cost Saved</div>
                <div class="metric-value green">{cost_saved_str}</div>
            </div>
        </div>

        {f'''
        <div class="prompt-box">
            <div class="prompt-header">
                <h3>📋 Generated Fork Prompt for Agent</h3>
                <button class="copy-btn" onclick="copyPrompt()">Copy Fork Prompt</button>
            </div>
            <div class="prompt-content" id="prompt-text">{fork_prompt_escaped}</div>
        </div>
        ''' if report.is_found() else ''}

        <div class="timeline-section">
            <h3>Execution Timeline ({session.metadata.total_steps} Steps)</h3>
            <div class="steps-list">
                {''.join(step_items_html)}
            </div>
        </div>
    </div>

    <script>
        function toggleStep(num) {{
            const el = document.getElementById('step-body-' + num);
            if (el) {{
                el.classList.toggle('open');
            }}
        }}

        function copyPrompt() {{
            const text = document.getElementById('prompt-text').innerText;
            navigator.clipboard.writeText(text).then(() => {{
                alert('Fork prompt copied to clipboard!');
            }}).catch(err => {{
                console.error('Failed to copy text: ', err);
            }});
        }}

        // Automatically expand the culprit card
        {f'document.addEventListener("DOMContentLoaded", () => toggleStep({bad_num}));' if bad_num else ''}
    </script>
</body>
</html>
"""
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        return out_file
