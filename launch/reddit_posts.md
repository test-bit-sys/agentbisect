# Reddit Launch Posts Playbook

---

## 1. Post for `r/programming` & `r/softwareengineering`

**Title:**
`I built a "git bisect" for AI coding agents to solve the compounding hallucination problem`

**Body:**
A common frustration with multi-step coding agents (Claude Code, Cursor, Aider, Devin) is what researchers call "compounding error drift":
An agent starts implementing a feature, runs 30 sequential tool calls, and introduces a subtle bug at Step 11. Steps 12 to 30 are hallucinations building on top of broken code. At the end, tests fail and the developer has to discard everything with `git checkout .`.

I built **AgentBisect**, a local-first CLI and MCP server that brings deterministic binary search to agent trajectories.

**Key Technical Decisions:**
- **Shadow Git Engine:** Instead of polluting the user's `.git/` history with 50 dirty commits, AgentBisect maintains an isolated bare object database in `.agentbisect/shadow_git` using explicit `--git-dir` and work-tree pointers.
- **$\mathcal{O}(\log N)$ Trajectory Search:** Tests are automatically executed at binary intervals ($N/2, N/4, \dots$). For a 40-step trajectory, it pinpoints the exact first broken step in ~5 executions.
- **Context Forking:** It rolls back the filesystem to the last good step and synthesizes an `AGENT_FORK_PROMPT.md` containing the diff and failure trace so the agent can resume with corrective guidance.
- **MCP Server:** Built-in stdio Model Context Protocol server allowing agents to call `agentbisect_bisect` and self-heal.

GitHub repo: https://github.com/your-username/agentbisect  
License: MIT.

---

## 2. Post for `r/cursor` & `r/ChatGPTCoding`

**Title:**
`Tired of Cursor/Claude breaking tests at step 30? I made an open-source tool that binary-searches the exact tool call that broke your build`

**Body:**
Hey everyone!

How many times has this happened to you?
You give Cursor Composer or Claude Code a prompt. It runs 35 edits. At step 35, `npm test` fails. You have no idea if it broke at step 5 or step 28. You end up hitting "revert all" and start from scratch.

I created **AgentBisect**:
- It tracks every tool call/edit as a lightweight shadow snapshot.
- You run `agentbisect find "npm test"`.
- It binary-searches your steps and says: *"First broken step: Step 14 (edit_file on auth.ts). Inverted condition broke 3 tests. Wasted tokens: 32,000"*.
- You run `agentbisect fork 13` and continue with a generated prompt.

You can try the zero-setup demo in your terminal:
```bash
pip install agentbisect
agentbisect demo
```
Would love to know what frameworks you want adapters for next!

---

## 3. Post for `r/LocalLLaMA`

**Title:**
`AgentBisect: Autonomous trajectory debugging and self-healing for local & cloud AI agents`

**Body:**
Sharing a project for anyone building multi-step agent loops or SWE-bench benchmarks:

One of the largest bottlenecks in autonomous agent evaluation is that once an agent takes a wrong path, it rarely recovers without trajectory rewinding.

`AgentBisect` implements deterministic binary search across agent trajectories:
1. Records step transitions (tool calls, state diffs).
2. Runs binary search against a verification condition.
3. Automatically computes divergence root cause and token waste metrics.
4. Exposes MCP tools (`agentbisect_snapshot`, `agentbisect_bisect`, `agentbisect_rewind`) so local LLMs (like Llama 3.3, Qwen 2.5 Coder) can inspect and bisect their own execution history.

Check out the repo: https://github.com/your-username/agentbisect
