"""
Fork engine for AgentBisect:
Restores workspace to the target step and synthesizes an intelligent continuation prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from agentbisect.core.models import AgentSession, AgentStep
from agentbisect.core.shadow_ledger import ShadowLedger


class ForkResult(BaseModel):
    """Result of a fork operation."""
    forked_step_number: int
    commit_hash: str
    prompt_file_path: str
    state_file_path: str
    generated_prompt: str


class ForkEngine:
    """Manages workspace rollback and generation of continuation prompts."""

    def __init__(self, session: AgentSession, ledger: ShadowLedger):
        self.session = session
        self.ledger = ledger

    def fork_to_step(
        self,
        target_step_num: int,
        culprit_step_num: Optional[int] = None,
        custom_hint: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ForkResult:
        """
        Rolls back the workspace to target_step_num and writes the fork guidance prompt.
        """
        step = self.session.get_step(target_step_num)
        if not step:
            raise ValueError(f"Step {target_step_num} does not exist in session.")

        # 1. Restore files in workspace
        self.ledger.restore_step(target_step_num)
        commit = self.ledger.get_commit_for_step(target_step_num) or ""

        # 2. Build intelligent fork prompt
        culprit_step = self.session.get_step(culprit_step_num) if culprit_step_num else None

        prompt_lines = [
            f"# AgentBisect Session Fork Notice",
            f"",
            f"**Action Taken:** Workspace state has been safely rewound to **Step {target_step_num}**.",
            f"",
        ]

        if culprit_step:
            prompt_lines.extend([
                f"### Divergence Analysis (Why we rewound):",
                f"- At **Step {culprit_step.step_number}**, the action `{culprit_step.summary()}` introduced a regression or broken state.",
            ])
            if culprit_step.files_affected:
                prompt_lines.append(f"- Files altered at faulty step: `{', '.join(culprit_step.files_affected)}`")
            if error_message:
                prompt_lines.extend([
                    f"",
                    f"**Failure Message / Test Error:**",
                    f"```",
                    error_message.strip(),
                    f"```",
                ])

        if custom_hint:
            prompt_lines.extend([
                f"",
                f"### User Guidance for Continuation:",
                f"> {custom_hint.strip()}",
            ])

        prompt_lines.extend([
            f"",
            f"### Next Steps for the Agent:",
            f"1. Acknowledge that you are resuming from the clean state of Step {target_step_num}.",
            f"2. Formulate a different approach that avoids the issue described above.",
            f"3. Run validation tests after your next change to verify correctness.",
        ])

        generated_prompt = "\n".join(prompt_lines)

        # 3. Write prompt file to workspace root and .agentbisect
        output_prompt_file = self.ledger.workspace_root / "AGENT_FORK_PROMPT.md"
        with open(output_prompt_file, "w", encoding="utf-8") as f:
            f.write(generated_prompt)

        # 4. Save fork state metadata
        fork_state = {
            "session_id": self.session.metadata.session_id,
            "rewound_to_step": target_step_num,
            "commit_hash": commit,
            "culprit_step": culprit_step_num,
            "hint": custom_hint,
            "error_message": error_message,
        }
        state_dir = self.ledger.workspace_root / ".agentbisect"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "fork_state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(fork_state, f, indent=2)

        return ForkResult(
            forked_step_number=target_step_num,
            commit_hash=commit,
            prompt_file_path=str(output_prompt_file),
            state_file_path=str(state_file),
            generated_prompt=generated_prompt,
        )
