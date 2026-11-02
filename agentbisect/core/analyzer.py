"""
Analyzer engine for AgentBisect:
Performs root-cause analysis, diff breakdown, and token waste calculations.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from agentbisect.core.models import AgentStep, AgentSession, WasteEstimate


class SessionAnalyzer:
    """Analyzes step diffs, test outputs, and calculates waste metrics."""

    @staticmethod
    def calculate_waste(session: AgentSession, first_bad_step_num: int) -> WasteEstimate:
        """
        Calculates how many steps, tokens, and estimated dollars/time were wasted
        after the first bad step.
        """
        total_steps = len(session.steps)
        if first_bad_step_num > total_steps:
            return WasteEstimate(
                wasted_steps=0,
                wasted_tokens=0,
                estimated_cost_usd=0.0,
                time_saved_minutes=0.0,
            )

        wasted_steps = total_steps - first_bad_step_num + 1
        total_wasted_tokens = 0
        total_duration_ms = 0

        for step in session.steps:
            if step.step_number >= first_bad_step_num:
                tokens = 0
                if step.token_usage and isinstance(step.token_usage, dict):
                    raw = (
                        step.token_usage.get("total")
                        or step.token_usage.get("total_tokens")
                    )
                    if raw is None:
                        prompt_t = step.token_usage.get("prompt_tokens") or 0
                        comp_t = step.token_usage.get("completion_tokens") or 0
                        try:
                            raw = int(prompt_t) + int(comp_t)
                        except (ValueError, TypeError):
                            raw = 0
                    try:
                        tokens = int(raw)
                    except (ValueError, TypeError):
                        tokens = 0

                if not tokens or tokens <= 0:
                    # Default heuristic estimation: ~1,800 tokens per agent turn
                    tokens = 1800
                total_wasted_tokens += tokens

                dur = 0
                if step.duration_ms is not None:
                    try:
                        dur = int(step.duration_ms)
                    except (ValueError, TypeError):
                        dur = 0
                if dur <= 0:
                    dur = 25000
                total_duration_ms += dur

        # Typical blended LLM API price (e.g. Claude 3.5 Sonnet / GPT-4o blend ~$0.000025 per token)
        estimated_cost = round((total_wasted_tokens / 1000.0) * 0.02, 3)
        time_saved_mins = round(total_duration_ms / (1000.0 * 60.0), 1)

        return WasteEstimate(
            wasted_steps=wasted_steps,
            wasted_tokens=total_wasted_tokens,
            estimated_cost_usd=estimated_cost,
            time_saved_minutes=time_saved_mins,
        )

    @staticmethod
    def extract_divergence_reason(
        bad_step: AgentStep,
        test_stderr: str,
        test_stdout: str,
    ) -> str:
        """
        Analyzes the diff of the bad step and test failure output to explain
        *why* this step caused the failure.
        """
        combined_output = f"{test_stdout}\n{test_stderr}"

        # Check for Python / JS / Go error signatures
        reasons = []

        # 1. Assertion Errors
        assert_match = re.search(r"AssertionError[:\s]*(.*)", combined_output)
        if assert_match:
            reasons.append(f"Assertion failed: {assert_match.group(1).strip()[:80]}")

        # 2. NameError / ReferenceError / Undefined
        undef_match = re.search(r"(NameError|ReferenceError|TypeError|AttributeError)[:\s]*(.*)", combined_output)
        if undef_match:
            reasons.append(f"{undef_match.group(1)}: {undef_match.group(2).strip()[:80]}")

        # 3. Import / Module errors
        import_match = re.search(r"(ModuleNotFoundError|ImportError)[:\s]*(.*)", combined_output)
        if import_match:
            reasons.append(f"{import_match.group(1)}: {import_match.group(2).strip()[:80]}")

        # 4. Check modified files
        if bad_step.files_affected:
            files_str = ", ".join(bad_step.files_affected[:3])
            file_context = f"Modified files: [{files_str}]"
        else:
            file_context = ""

        # 5. Tool call context
        action_context = f"Executed {bad_step.summary()}"

        if reasons:
            primary_error = " | ".join(reasons)
            return f"{action_context} -> Triggered {primary_error} ({file_context})"

        return f"{action_context} broke test expectations ({file_context})"
