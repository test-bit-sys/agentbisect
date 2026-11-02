# Show HN: AgentBisect – Git bisect for autonomous AI coding agents

**Submission Title:**
`Show HN: AgentBisect – Git bisect for autonomous AI coding agents`

**Target URL:**
`https://github.com/your-username/agentbisect`

---

### First Comment (The Maker's Story):

Hey HN!

I built AgentBisect because I was tired of a problem that happens to almost everyone using autonomous coding agents (Claude Code, Cursor Agent, Antigravity, Devin, Aider): **Compounding Agent Drift**.

### The Problem
When you let an agent work on a multi-step task (say, 30 to 45 steps involving tool calls, bash commands, and edits across multiple files), the agent often does great until around Step 14. At Step 14, it introduces a subtle semantic regression—for example, inverting a conditional, changing a function signature, or dropping an edge-case test check.

Because the agent doesn't realize this immediately, steps 15 through 40 turn into compounding hallucinations. It writes patches on top of bad assumptions. At the end, 10 unit tests are red.

Right now, developers only have two choices:
1. Manually comb through a 2,000-line JSON transcript trying to guess where the train went off the rails.
2. Run `git checkout .` — wiping out the entire session, throwing away 40,000 tokens, \$1.50 in API costs, and 25 minutes of waiting.

### How AgentBisect works
`AgentBisect` is an open-source, local-first CLI and MCP server that brings `git bisect` to agent trajectories:

1. **Non-polluting Shadow Git Ledger:** It captures step checkpoints in an isolated `.agentbisect/shadow_git/` object store. It doesn't pollute your project's real git log, create dirty commits, or touch your branches.
2. **Binary Search Engine (`agentbisect find`):** Given your test command (e.g. `npm test` or `pytest`), it performs binary search over the session steps. In $\mathcal{O}(\log_2 N)$ runs (just 5 test runs for a 32-step session), it isolates the exact first bad step.
3. **Workspace & Context Forking (`agentbisect fork <step>`):** It rolls back the filesystem to the last known good step and synthesizes a prompt injection (`AGENT_FORK_PROMPT.md`) explaining to the agent exactly what broke and what diff caused it.
4. **Self-Healing MCP Server:** Agents running inside Cursor, Claude, or Antigravity can call `agentbisect_bisect` and rewind themselves autonomously when tests fail!
5. **Interactive HTML Dashboard:** Generates a standalone, dependency-free HTML report with visual step graphs, unified diffs, and estimated token savings.

### Try the built-in demo:
You don't need any pre-recorded session to test it. Just run:
```bash
pip install agentbisect
agentbisect demo
```
It spins up a 20-step simulated microservice session, runs the binary search live, pinpoints Step 12 in 6 evaluations, and generates the HTML report.

The code is MIT licensed, lightweight (Python 3.10+, Click, Rich, Pydantic), and has no heavy external server dependencies.

Would love your feedback on the heuristic analyzer, transcript adapter support, and edge-case handling for flaky tests!
