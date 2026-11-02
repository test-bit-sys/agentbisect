---
name: agentbisect
description: "Autonomous trajectory debugging and binary-search regression locator for AI coding agents. Enables agents to locate the exact step that broke tests and rewind the workspace to a clean state."
---

# AgentBisect Skill

Use this skill whenever an agent coding session encounters test failures, compilation errors, or broken functionality after multi-step autonomous modifications.

## Core Problem Solved
When agents execute 10 to 50 sequential steps, a subtle mistake at Step $k$ often causes compounding hallucinations in subsequent steps. Instead of scrapping the entire workspace or manually guessing which tool call introduced the bug, `AgentBisect` applies deterministic binary search over the session steps to isolate the first broken step in $\mathcal{O}(\log N)$ evaluations and rewinds the workspace.

---

## Available MCP Tools

### 1. `agentbisect_snapshot`
Creates a non-polluting shadow git snapshot before or after significant workspace edits.
```json
{
  "summary": "Refactored database query to use connection pooling",
  "files": ["src/db/connection.py"]
}
```

### 2. `agentbisect_bisect`
Executes automated binary search over the recorded steps to locate the exact step that caused a test regression.
```json
{
  "test_command": "pytest tests/test_auth.py",
  "timeout_seconds": 45
}
```
**Returns:**
- The first faulty step number and summary.
- The unified diff introduced at that step.
- The root-cause divergence reason.
- The last known good step number.

### 3. `agentbisect_rewind`
Restores the workspace to a specified step number (typically the last good step) and generates an actionable recovery prompt.
```json
{
  "target_step": 11,
  "hint": "Avoid changing the verify_token expiration comparator; keep using greater-than."
}
```

### 4. `agentbisect_get_diff`
Inspects the git diff introduced at any specific historical step.
```json
{
  "step_number": 12
}
```

---

## Autonomous Agent Workflow

```
[Agent runs multi-step tasks]
            │
      Tests FAIL ❌
            │
   ┌────────┴────────┐
   │ Can fix easily? │
   └────────┬────────┘
     NO     │     YES ──► Fix directly
            ▼
Invoke `agentbisect_bisect`
(Runs binary search: tests Step 20, Step 1, Step 10, Step 12...)
            │
🎯 Culprit Identified: Step 12
            │
Invoke `agentbisect_rewind` (target_step=11)
            │
Workspace is restored to clean state of Step 11
Agent continues with corrected hypothesis!
```

---

## Best Practices
1. **Snapshot key milestones:** When finishing a coherent feature or passing a test milestone, invoke `agentbisect_snapshot` with a descriptive summary.
2. **Never compound hallucinations:** If tests fail after 3 consecutive attempts to patch a problem, stop digging deeper. Run `agentbisect_bisect` to find where the regression originated.
3. **Inspect the culprit diff:** Before resuming work from the rewound state, always examine the diff of the faulty step to understand the mistake and prevent repeating it.
