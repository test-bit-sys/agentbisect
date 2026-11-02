"""
Command Line Interface (CLI) for AgentBisect.
"""

from __future__ import annotations

import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Optional
import click
from agentbisect.adapters import load_session, LiveRecorder
from agentbisect.adapters.antigravity import AntigravityAdapter
from agentbisect.core.bisect_engine import BisectEngine
from agentbisect.core.bundle import BundleManager
from agentbisect.core.doctor import SystemDoctor
from agentbisect.core.fork_engine import ForkEngine
from agentbisect.core.models import AgentSession
from agentbisect.core.shadow_ledger import ShadowLedger
from agentbisect.core.process_wrapper import ProcessWrapper
from agentbisect.demo.scenarios import setup_demo_environment
from agentbisect.demo.scenarios_js import setup_node_demo_environment
from agentbisect.mcp.server import AgentBisectMCPServer
from agentbisect.report.html_generator import HTMLReportGenerator
from agentbisect.report.server import run_server, create_handler_class
from agentbisect.report.terminal_ui import TerminalUI, console


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version="0.1.0", prog_name="agentbisect")
def main():
    """⚡ AgentBisect: Git bisect for AI coding agents ⚡"""
    pass


@main.command(name="find")
@click.argument("test_command", required=True)
@click.option("--transcript", "-t", type=click.Path(exists=True), help="Path to transcript file (JSON/JSONL).")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
@click.option("--timeout", type=int, default=60, help="Timeout in seconds per test run.")
@click.option("--retries", "-r", type=int, default=1, help="Retry attempts for flaky test handling (default: 1).")
@click.option("--strategy", "-s", type=click.Choice(["binary", "heuristic"]), default="binary", help="Search strategy (default: binary).")
@click.option("--html/--no-html", default=True, help="Generate HTML report (default: True).")
@click.option("--open/--no-open", "open_browser", default=False, help="Open HTML report in browser automatically.")
def find_cmd(
    test_command: str,
    transcript: Optional[str],
    workspace: str,
    timeout: int,
    retries: int,
    strategy: str,
    html: bool,
    open_browser: bool,
):
    """Run binary or heuristic search over agent steps to locate the exact step that broke TEST_COMMAND."""
    TerminalUI.print_banner()
    ws_path = Path(workspace).resolve()

    # Locate transcript file
    if transcript:
        trans_path = Path(transcript).resolve()
    else:
        # Check standard locations
        candidates = [
            ws_path / ".agentbisect" / "current_session.json",
            ws_path / "transcript.jsonl",
            ws_path / ".system_generated" / "logs" / "transcript.jsonl",
        ]
        trans_path = None
        for c in candidates:
            if c.exists():
                trans_path = c
                break

    if not trans_path or not trans_path.exists():
        console.print(
            "[bold red]Error:[/bold red] No transcript file found. "
            "Please specify one with [cyan]--transcript <path>[/cyan], "
            "or run [yellow]agentbisect demo[/yellow] to try a simulation."
        )
        sys.exit(1)

    console.print(f"[bold cyan]Workspace:[/bold cyan] {ws_path}")
    console.print(f"[bold cyan]Transcript:[/bold cyan] {trans_path}")
    console.print(f"[bold cyan]Test Command:[/bold cyan] [yellow]{test_command}[/yellow]")
    console.print(f"[bold cyan]Strategy:[/bold cyan] [white]{strategy}[/white] | [bold cyan]Retries:[/bold cyan] [white]{retries}[/white]\n")

    # Load session
    session = load_session(trans_path, ws_path)
    total_steps = len(session.steps)
    if total_steps == 0:
        console.print("[bold red]Error:[/bold red] Loaded session contains 0 steps.")
        sys.exit(1)

    console.print(f"Loaded session [bold white]{session.metadata.session_id}[/bold white] with [bold green]{total_steps}[/bold green] steps.")

    # Initialize ledger and ensure steps are committed
    ledger = ShadowLedger(ws_path)

    console.print("\n[bold cyan]Starting search across steps...[/bold cyan]")

    engine = BisectEngine(
        session=session,
        ledger=ledger,
        test_command=test_command,
        timeout_seconds=timeout,
        retries=retries,
        strategy=strategy,
        on_step_evaluated=TerminalUI.print_bisect_step_evaluated,
    )

    report = engine.run()
    TerminalUI.print_report(report)

    # Output to GitHub Step Summary if running in CI
    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary:
        try:
            with open(gh_summary, "a", encoding="utf-8") as f:
                f.write(f"\n## ⚡ AgentBisect Result for `{test_command}`\n")
                if report.is_found():
                    f.write(f"- **First Broken Step:** Step #{report.first_bad_step.step_number}\n")
                    f.write(f"- **Divergence Reason:** {report.divergence_reason}\n")
                    f.write(f"- **Last Known Good:** Step #{report.last_good_step.step_number if report.last_good_step else 0}\n")
                else:
                    f.write(f"- {report.divergence_reason}\n")
        except Exception:
            pass

    if html:
        report_file = ws_path / "agentbisect_report.html"
        HTMLReportGenerator.generate(report, session, report_file)
        console.print(f"\n[bold green][OK] Interactive HTML Report generated:[/bold green] {report_file}")
        if open_browser:
            webbrowser.open(report_file.as_uri())


@main.command(name="fork")
@click.argument("step_number", type=int, required=True)
@click.option("--hint", "-h", type=str, help="Optional guidance hint for the agent.")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def fork_cmd(step_number: int, hint: Optional[str], workspace: str):
    """Rewind workspace to STEP_NUMBER and generate recovery prompt for agent."""
    TerminalUI.print_banner()
    ws_path = Path(workspace).resolve()
    session_file = ws_path / ".agentbisect" / "current_session.json"

    if not session_file.exists():
        console.print("[bold red]Error:[/bold red] No active session found in .agentbisect/current_session.json.")
        sys.exit(1)

    session = AgentSession.load_json(session_file)
    ledger = ShadowLedger(ws_path)
    fork_engine = ForkEngine(session, ledger)

    try:
        res = fork_engine.fork_to_step(target_step_num=step_number, custom_hint=hint)
        console.print(f"[bold green][OK] Workspace rewound to Step #{step_number}[/bold green] [{res.commit_hash[:7]}].")
        console.print(f"[bold cyan]Fork Prompt generated at:[/bold cyan] {res.prompt_file_path}\n")
        console.print(res.generated_prompt)
    except Exception as e:
        console.print(f"[bold red]Error during fork:[/bold red] {e}")
        sys.exit(1)


@main.command(name="snapshot")
@click.argument("summary", default="Checkpoint", required=False)
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def snapshot_cmd(summary: str, workspace: str):
    """Create an immediate shadow git snapshot of current workspace."""
    ws_path = Path(workspace).resolve()
    recorder = LiveRecorder(ws_path)
    step = recorder.record_step(tool_name="manual_snapshot", agent_thought=summary)
    console.print(f"[bold green][OK] Snapshot created:[/bold green] Step #{step.step_number} [{step.commit_hash[:7]}] - '{summary}'")


@main.command(name="demo")
@click.option("--lang", "-l", type=click.Choice(["python", "node"], case_sensitive=False), default="python", help="Language scenario to demo (python or node).")
@click.option("--open/--no-open", "open_browser", default=False, help="Open HTML report in browser automatically.")
def demo_cmd(lang: str, open_browser: bool):
    """Run an interactive agent failure simulation (Python or Node.js) to watch AgentBisect in action."""
    TerminalUI.print_banner()
    temp_dir = Path(tempfile.mkdtemp(prefix="agentbisect_demo_"))

    try:
        if lang.lower() == "node":
            console.print("[bold yellow][>>] Setting up Node.js microservice scenario (15 steps with node --test)...[/bold yellow]")
            session = setup_node_demo_environment(temp_dir)
            console.print(f"[bold green][OK] Generated 15 Node.js agent steps in temporary sandbox:[/bold green] {temp_dir}")
            console.print("  - Steps 1..8: Math utilities and native tests (All Passing)")
            console.print("  - [bold red]Step 9: Agent modifies divide() to return null instead of throwing Error![/bold red]")
            console.print("  - Steps 10..15: Subsequent additions unaware of broken test\n")
            test_cmd = "node --test"
        else:
            console.print("[bold yellow][>>] Setting up realistic Python scenario (20-step Auth Microservice)...[/bold yellow]")
            session = setup_demo_environment(temp_dir)
            console.print(f"[bold green][OK] Generated 20 agent steps in temporary sandbox:[/bold green] {temp_dir}")
            console.print("  - Steps 1..11: User models, token creation, test harness (All Passing)")
            console.print("  - [bold red]Step 12: Agent hallucinates and breaks token expiration logic![/bold red]")
            console.print("  - Steps 13..20: Agent keeps adding features unaware of broken auth tests\n")
            test_cmd = "python -m pytest --rootdir=. -o pythonpath=. tests/test_auth.py"

        console.print(f"[bold cyan]Executing AgentBisect: Binary Search against test command '{test_cmd}'...[/bold cyan]\n")

        ledger = ShadowLedger(temp_dir)
        engine = BisectEngine(
            session=session,
            ledger=ledger,
            test_command=test_cmd,
            timeout_seconds=30,
            on_step_evaluated=TerminalUI.print_bisect_step_evaluated,
        )

        report = engine.run()
        TerminalUI.print_report(report)

        report_file = temp_dir / "agentbisect_demo_report.html"
        HTMLReportGenerator.generate(report, session, report_file)
        console.print(f"\n[bold green][OK] Interactive HTML Report generated:[/bold green] {report_file}")
        if open_browser:
            webbrowser.open(report_file.as_uri())

    except Exception as e:
        console.print(f"[bold red]Demo error:[/bold red] {e}")
        raise e


@main.command(name="wrap", context_settings=dict(ignore_unknown_options=True))
@click.argument("command", nargs=-1, required=True)
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def wrap_cmd(command, workspace: str):
    """Execute COMMAND transparently while recording filesystem changes as a shadow step."""
    wrapper = ProcessWrapper(workspace_root=workspace)
    exit_code = wrapper.run_wrapped(list(command))
    sys.exit(exit_code)


@main.command(name="ui")
@click.option("--port", "-p", default=8765, help="Port to run web UI server on (default: 8765).")
@click.option("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1).")
@click.option("--open/--no-open", "open_browser", default=True, help="Open browser automatically (default: True).")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def ui_cmd(port: int, host: str, open_browser: bool, workspace: str):
    """Launch the interactive local Web UI dashboard."""
    TerminalUI.print_banner()
    url = f"http://{host}:{port}"
    console.print(f"[bold green][OK] Starting AgentBisect Web UI at:[/bold green] [bold cyan]{url}[/bold cyan]")
    if open_browser:
        webbrowser.open(url)
    run_server(workspace_root=workspace, host=host, port=port)


@main.command(name="mcp")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def mcp_cmd(workspace: str):
    """Start the stdio Model Context Protocol (MCP) server."""
    server = AgentBisectMCPServer(workspace_root=workspace)
    server.run_stdio()


@main.command(name="status")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def status_cmd(workspace: str):
    """View active session status and step count."""
    ws_path = Path(workspace).resolve()
    session_file = ws_path / ".agentbisect" / "current_session.json"
    if not session_file.exists():
        console.print("[yellow]No active session found in current workspace.[/yellow]")
        return
    session = AgentSession.load_json(session_file)
    console.print(f"[bold cyan]Session ID:[/bold cyan] {session.metadata.session_id}")
    console.print(f"[bold cyan]Framework:[/bold cyan] {session.metadata.framework}")
    console.print(f"[bold cyan]Total Steps:[/bold cyan] {len(session.steps)}")
    console.print(f"[bold cyan]Created At:[/bold cyan] {session.metadata.created_at}")


@main.command(name="doctor")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def doctor_cmd(workspace: str):
    """Run pre-flight environment, dependency, and workspace diagnostics."""
    TerminalUI.print_banner()
    console.print("[bold cyan]Running AgentBisect System Diagnostics...[/bold cyan]\n")
    checks = SystemDoctor.run_diagnostics(workspace)
    all_ok = True
    for name, ok, msg in checks:
        if ok:
            console.print(f"  [bold green][PASS][/bold green] [bold white]{name}:[/bold white] {msg}")
        else:
            all_ok = False
            console.print(f"  [bold red][FAIL][/bold red] [bold white]{name}:[/bold white] {msg}")

    if all_ok:
        console.print("\n[bold green][OK] Environment is healthy and ready for AgentBisect![/bold green]")
    else:
        console.print("\n[bold yellow][!] Some diagnostic checks reported warnings or errors.[/bold yellow]")


@main.group(name="bundle")
def bundle_group():
    """Export and import portable .bisect evidence bundles for collaboration."""
    pass


@bundle_group.command(name="export")
@click.option("--output", "-o", type=click.Path(), help="Output path for .bisect.zip bundle.")
@click.option("--workspace", "-w", type=click.Path(exists=True), default=".", help="Workspace root directory.")
def bundle_export_cmd(output: Optional[str], workspace: str):
    """Export the current session trajectory and shadow ledger into a portable bundle."""
    try:
        out = BundleManager.export_bundle(workspace, output)
        console.print(f"[bold green][OK] Evidence bundle exported successfully:[/bold green] [cyan]{out}[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Export failed:[/bold red] {e}")
        sys.exit(1)


@bundle_group.command(name="import")
@click.argument("bundle_path", type=click.Path(exists=True), required=True)
@click.argument("target_dir", type=click.Path(), default=".", required=False)
def bundle_import_cmd(bundle_path: str, target_dir: str):
    """Import a portable .bisect.zip bundle into target directory for inspection."""
    try:
        session = BundleManager.import_bundle(bundle_path, target_dir)
        console.print(f"[bold green][OK] Successfully imported session:[/bold green] [cyan]{session.metadata.session_id}[/cyan] with {len(session.steps)} steps into [cyan]{target_dir}[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Import failed:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
