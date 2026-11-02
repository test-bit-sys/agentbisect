"""
System health and pre-flight diagnostics module for AgentBisect.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class SystemDoctor:
    """Performs environment and dependency health checks."""

    @staticmethod
    def run_diagnostics(workspace_root: Path | str = ".") -> List[Tuple[str, bool, str]]:
        ws_path = Path(workspace_root).resolve()
        checks: List[Tuple[str, bool, str]] = []

        # 1. Python version check
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 10):
            checks.append(("Python Version", True, f"Python {py_ver} (>= 3.10)"))
        else:
            checks.append(("Python Version", False, f"Python {py_ver} is too old; requires >= 3.10"))

        # 2. Git binary check
        git_path = shutil.which("git")
        if git_path:
            try:
                res = subprocess.run(["git", "--version"], capture_output=True, text=True)
                git_ver = res.stdout.strip()
                checks.append(("Git Executable", True, f"{git_ver} at {git_path}"))
            except Exception as e:
                checks.append(("Git Executable", False, f"Failed executing git: {e}"))
        else:
            checks.append(("Git Executable", False, "git was not found on PATH"))

        # 3. Workspace write permissions
        try:
            test_file = ws_path / ".agentbisect_perm_test.tmp"
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            checks.append(("Workspace Permissions", True, f"Read/Write OK on {ws_path}"))
        except Exception as e:
            checks.append(("Workspace Permissions", False, f"Permission error: {e}"))

        # 4. Node.js check (optional helper)
        node_path = shutil.which("node")
        if node_path:
            try:
                res = subprocess.run(["node", "--version"], capture_output=True, text=True)
                node_ver = res.stdout.strip()
                checks.append(("Node.js Runtime", True, f"{node_ver} (node --test enabled)"))
            except Exception:
                checks.append(("Node.js Runtime", False, "node binary found but execution failed"))
        else:
            checks.append(("Node.js Runtime", True, "Not installed (Optional for Node.js projects)"))

        # 5. AgentBisect Storage Status
        dot_bisect = ws_path / ".agentbisect"
        if dot_bisect.exists():
            checks.append(("AgentBisect Ledger", True, f"Active ledger found at {dot_bisect}"))
        else:
            checks.append(("AgentBisect Ledger", True, "No active ledger initialized yet (Will initialize on first step)"))

        return checks
