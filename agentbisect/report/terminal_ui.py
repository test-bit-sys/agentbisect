"""
Rich Terminal UI for AgentBisect:
Renders colorful step trees, binary search timelines, diffs, and waste summaries.
"""

from __future__ import annotations

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.syntax import Syntax
from rich.text import Text
from agentbisect.core.models import (
    BisectReport,
    BisectStatus,
    BisectStepResult,
    AgentSession,
)

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console()


class TerminalUI:
    """Renders interactive and colorful reporting in the developer's terminal."""

    @staticmethod
    def print_banner() -> None:
        banner = """
   ___                    __   ____  _               __ 
  / _ | ___ ____ ___  ___/ /_ / __ )(_)__ ___  ____/ /_
 / __ |/ _ `/ -_) _ \\/ _  // / /_/ / (_-</ -_)/ __/ __/
/_/ |_|\\_, /\\__/_//_/\\_,_/___/_____/_/___/\\__/\\__/\\__/  
      /___/                                             
  >> Git Bisect for Autonomous AI Coding Agents <<
"""
        console.print(Panel(Text(banner, style="bold cyan"), border_style="cyan"))

    @staticmethod
    def print_bisect_step_evaluated(
        result: BisectStepResult,
        current_eval: int,
        total_steps: int,
    ) -> None:
        """Prints live evaluation progress as binary search proceeds."""
        if result.status == BisectStatus.PASS:
            status_text = "[bold green][PASS][/bold green]"
        elif result.status == BisectStatus.FAIL:
            status_text = "[bold red][FAIL][/bold red]"
        else:
            status_text = f"[bold yellow][{result.status.value}][/bold yellow]"

        console.print(
            f"  [dim]Eval #{current_eval}[/dim] ---> Testing [bold white]Step {result.step_number}/{total_steps}[/bold white] "
            f"[{result.commit_hash[:7]}]: {status_text} "
            f"[dim]({result.duration_seconds}s)[/dim]"
        )

    @staticmethod
    def print_report(report: BisectReport) -> None:
        """Prints the full post-bisect report."""
        console.print("\n")

        if not report.is_found():
            console.print(
                Panel(
                    f"[bold yellow]{report.divergence_reason or 'No divergence step identified.'}[/bold yellow]",
                    title="[bold yellow]Bisect Finished: No Culprit Step Found[/bold yellow]",
                    border_style="yellow",
                )
            )
            return

        bad_step = report.first_bad_step
        good_step = report.last_good_step

        # Culprit Panel
        culprit_title = f"[bold red]>> Culprit Identified: Step #{bad_step.step_number}[/bold red]"
        culprit_body = [
            f"[bold white]Action:[/bold white] {bad_step.summary()}",
            f"[bold white]Files Affected:[/bold white] {', '.join(bad_step.files_affected) if bad_step.files_affected else 'None'}",
            f"[bold white]Divergence Reason:[/bold white] [red]{report.divergence_reason}[/red]",
            f"[bold white]Last Known Good State:[/bold white] [green]Step #{good_step.step_number if good_step else 0}[/green]",
        ]
        console.print(Panel("\n".join(culprit_body), title=culprit_title, border_style="red"))

        # Evaluations Table
        table = Table(title="[bold cyan]Binary Search Evaluations[/bold cyan]", border_style="dim")
        table.add_column("Order", justify="center", style="dim")
        table.add_column("Step #", justify="center", style="bold")
        table.add_column("Commit", justify="center", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Exit Code", justify="center")
        table.add_column("Duration", justify="right")

        for idx, eval_res in enumerate(report.steps_evaluated, 1):
            if eval_res.status == BisectStatus.PASS:
                st = "[green]PASS[/green]"
            elif eval_res.step_number == bad_step.step_number:
                st = "[bold red]FIRST BAD [!][/bold red]"
            else:
                st = "[red]FAIL[/red]"
            table.add_row(
                str(idx),
                str(eval_res.step_number),
                eval_res.commit_hash[:8],
                st,
                str(eval_res.exit_code),
                f"{eval_res.duration_seconds}s",
            )
        console.print(table)

        # Waste Estimate Panel
        if report.waste_estimate:
            w = report.waste_estimate
            waste_text = (
                f"- [bold red]{w.wasted_steps} steps[/bold red] wasted after the error\n"
                f"- [bold yellow]~{w.wasted_tokens:,} tokens[/bold yellow] spent on compounding hallucinations\n"
                f"- [bold green]~${w.estimated_cost_usd:.2f}[/bold green] estimated API cost saved by rewinding\n"
                f"- [bold cyan]~{w.time_saved_minutes} minutes[/bold cyan] developer time saved"
            )
            console.print(Panel(waste_text, title="[bold green]Value & Waste Saved[/bold green]", border_style="green"))

        # Diff Preview
        if bad_step.diff:
            console.print("\n[bold cyan]Diff introduced at Step #" + str(bad_step.step_number) + ":[/bold cyan]")
            syntax = Syntax(bad_step.diff[:1500], "diff", theme="monokai", line_numbers=True)
            console.print(syntax)
            if len(bad_step.diff) > 1500:
                console.print("[dim]... (diff truncated, full diff in HTML report) ...[/dim]")

        # Suggested Command
        good_num = good_step.step_number if good_step else 0
        console.print(
            Panel(
                f"[bold white]To rewind your workspace to the last good state and continue with guidance:[/bold white]\n\n"
                f"  [bold yellow]agentbisect fork {good_num}[/bold yellow]\n\n"
                f"A generated prompt file [bold cyan]AGENT_FORK_PROMPT.md[/bold cyan] will be created for your agent.",
                title="[bold yellow]Next Step[/bold yellow]",
                border_style="yellow",
            )
        )
