"""
Shadow Git Ledger for AgentBisect.
Manages isolated, non-polluting versioning of agent workspace states without affecting user's main git repository.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple
from agentbisect.core.models import AgentStep, StepType


class ShadowLedger:
    """
    Manages an isolated Git repository located inside `.agentbisect/shadow_git`.
    Executes git commands with explicit `--git-dir` and `--work-tree` so the user's
    existing `.git` (if any) is completely untouched and clean.
    """

    def __init__(self, workspace_root: Path | str, ledger_dir: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve()
        if ledger_dir:
            self.ledger_dir = Path(ledger_dir).resolve()
        else:
            self.ledger_dir = (self.workspace_root / ".agentbisect" / "shadow_git").resolve()

        self.git_dir = self.ledger_dir
        self.work_tree = self.workspace_root
        self._init_shadow_repo()

    @contextlib.contextmanager
    def lock(self, timeout_seconds: float = 10.0):
        """Cross-platform advisory file lock for atomic shadow ledger operations."""
        lock_file = self.ledger_dir / "agentbisect.lock"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        start = time.time()
        acquired = False
        lock_fd = None
        try:
            while time.time() - start < timeout_seconds:
                try:
                    lock_fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    os.write(lock_fd, f"{os.getpid()}\n".encode("utf-8"))
                    acquired = True
                    break
                except FileExistsError:
                    try:
                        mtime = lock_file.stat().st_mtime
                        if time.time() - mtime > 60:
                            lock_file.unlink(missing_ok=True)
                            continue
                    except OSError:
                        pass
                    time.sleep(0.05)
            if not acquired:
                raise TimeoutError(f"Could not acquire shadow ledger lock on {lock_file} within {timeout_seconds}s")
            yield
        finally:
            if acquired and lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    pass

    def _run_git(
        self,
        args: List[str],
        check: bool = True,
        include_work_tree: bool = True,
    ) -> subprocess.CompletedProcess:
        """Executes a git command targeted at the shadow repo and the workspace work-tree."""
        cmd = ["git", f"--git-dir={str(self.git_dir)}"]
        if include_work_tree:
            cmd.append(f"--work-tree={str(self.work_tree)}")
        cmd.extend(args)

        # Set dummy committer/author so git never fails on missing user.name/email
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "AgentBisect"
        env["GIT_AUTHOR_EMAIL"] = "agentbisect@local"
        env["GIT_COMMITTER_NAME"] = "AgentBisect"
        env["GIT_COMMITTER_EMAIL"] = "agentbisect@local"

        result = subprocess.run(
            cmd,
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {' '.join(cmd)}\nExit code: {result.returncode}\nStderr: {result.stderr}\nStdout: {result.stdout}"
            )
        return result

    def _init_shadow_repo(self) -> None:
        """Initializes the shadow git repository if not already initialized."""
        if not (self.git_dir / "HEAD").exists():
            self.git_dir.mkdir(parents=True, exist_ok=True)
            # 1. Bare init without work-tree argument
            subprocess.run(
                ["git", "init", "--bare", str(self.git_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            # 2. Allow work tree operations
            self._run_git(["config", "core.bare", "false"], include_work_tree=False)

            # 3. Exclude internal files from shadow tracking
            info_exclude = self.git_dir / "info" / "exclude"
            info_exclude.parent.mkdir(parents=True, exist_ok=True)
            with open(info_exclude, "w", encoding="utf-8") as f:
                f.write(".agentbisect/\n.agentbisect/**\n__pycache__/\nnode_modules/\n.git/\n.git/**\n")

    def snapshot_step(
        self,
        step_number: int,
        summary: str = "",
        files: Optional[List[str]] = None,
    ) -> str:
        """
        Creates a commit in the shadow repo representing the exact state at this step.
        Returns the commit hash.
        """
        with self.lock():
            # Add files to index
            if files:
                # Add specific files
                existing_files = [f for f in files if (self.workspace_root / f).exists()]
                if existing_files:
                    self._run_git(["add"] + existing_files)
            else:
                # Add all workspace files (respecting exclude)
                self._run_git(["add", "-A"])

            msg = f"Step {step_number}: {summary}" if summary else f"Step {step_number}"
            # Commit with --allow-empty so every step is recorded even if file didn't change
            res = self._run_git(["commit", "--allow-empty", "-m", msg])
            # Get latest commit hash
            hash_res = self._run_git(["rev-parse", "HEAD"])
            commit_hash = hash_res.stdout.strip()

            # Tag this step for quick reference: step-1, step-2, etc.
            self._run_git(["tag", "-f", f"step-{step_number}", commit_hash])
            return commit_hash

    def get_commit_for_step(self, step_number: int) -> Optional[str]:
        """Resolves the commit hash for a given step tag."""
        res = self._run_git(["rev-parse", f"step-{step_number}"], check=False)
        if res.returncode == 0:
            return res.stdout.strip()
        return None

    def get_current_head(self) -> Optional[str]:
        """Resolves current HEAD commit hash if repository has any commits."""
        res = self._run_git(["rev-parse", "HEAD"], check=False)
        if res.returncode == 0:
            return res.stdout.strip()
        return None

    def restore_step(self, step_number: int) -> None:
        """Restores workspace files to the exact state at the given step number."""
        commit = self.get_commit_for_step(step_number)
        if not commit:
            raise ValueError(f"Step {step_number} not found in shadow ledger.")
        self.restore_commit(commit)

    def restore_commit(self, commit_hash: str) -> None:
        """Restores workspace files to a specific commit hash safely preserving user .git."""
        # Clean untracked files (except excluded) and checkout commit
        self._run_git(["checkout", "-f", commit_hash])
        # Clean any files that shouldn't exist at this commit while protecting critical directories
        self._run_git([
            "clean", "-fd",
            "-e", ".agentbisect",
            "-e", ".agentbisect/**",
            "-e", ".git",
            "-e", ".git/**"
        ])

    def get_step_diff(self, step_number: int) -> str:
        """Returns the git diff introduced at this specific step."""
        commit = self.get_commit_for_step(step_number)
        if not commit:
            return ""
        # Check if parent commit exists
        parent_res = self._run_git(["rev-parse", f"{commit}^"], check=False)
        if parent_res.returncode == 0:
            parent = parent_res.stdout.strip()
            diff_res = self._run_git(["diff", parent, commit])
            return diff_res.stdout
        else:
            # First commit diff
            diff_res = self._run_git(["show", "--pretty=format:", commit], check=False)
            return diff_res.stdout

    def get_diff_between(self, step_a: int, step_b: int) -> str:
        """Returns the diff between step_a and step_b."""
        commit_a = self.get_commit_for_step(step_a)
        commit_b = self.get_commit_for_step(step_b)
        if not commit_a or not commit_b:
            return ""
        res = self._run_git(["diff", commit_a, commit_b], check=False)
        return res.stdout

    def get_affected_files(self, step_number: int) -> List[str]:
        """Returns list of files modified/added/deleted at this step."""
        commit = self.get_commit_for_step(step_number)
        if not commit:
            return []
        parent_res = self._run_git(["rev-parse", f"{commit}^"], check=False)
        if parent_res.returncode == 0:
            parent = parent_res.stdout.strip()
            res = self._run_git(["diff", "--name-only", parent, commit], check=False)
        else:
            res = self._run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", commit], check=False)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return lines

    def create_initial_baseline(self) -> str:
        """Creates an initial baseline commit before any steps run."""
        with self.lock():
            self._run_git(["add", "-A"])
            self._run_git(["commit", "--allow-empty", "-m", "AgentBisect Baseline"])
            hash_res = self._run_git(["rev-parse", "HEAD"])
            commit_hash = hash_res.stdout.strip()
            self._run_git(["tag", "-f", "baseline", commit_hash])
            return commit_hash

    def stash_worktree(self) -> bool:
        """Stashes any uncommitted working tree changes into a temporary shadow tag."""
        with self.lock():
            res = self._run_git(["status", "--porcelain"])
            if not res.stdout.strip():
                return False  # Worktree was clean

            self._run_git(["add", "-A"])
            self._run_git(["commit", "--allow-empty", "-m", "AgentBisect Pre-Run Stash"])
            hash_res = self._run_git(["rev-parse", "HEAD"])
            self._run_git(["tag", "-f", "stash_backup", hash_res.stdout.strip()])
            return True

    def restore_stash(self, parent_commit: Optional[str] = None) -> None:
        """Restores the stashed working tree changes and resets shadow index."""
        with self.lock():
            stash_res = self._run_git(["rev-parse", "stash_backup"], check=False)
            if stash_res.returncode == 0:
                stash_commit = stash_res.stdout.strip()
                parent = parent_commit
                if not parent:
                    p_res = self._run_git(["rev-parse", "stash_backup^"], check=False)
                    if p_res.returncode == 0:
                        parent = p_res.stdout.strip()
                self.restore_commit(stash_commit)
                self._run_git(["tag", "-d", "stash_backup"], check=False)
                if parent:
                    self._run_git(["reset", parent], check=False)

