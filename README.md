<p align="center">
  <img src="assets/logo.png" alt="AgentBisect Logo" width="180" style="border-radius: 24px; box-shadow: 0 8px 32px rgba(56, 189, 248, 0.25);" />
</p>

<h1 align="center">⚡ AgentBisect</h1>

<p align="center">
  <b>Git Bisect & Time-Travel Debugging for Autonomous AI Coding Agents.</b><br>
  <i>Stop restarting 40-step agent sessions from scratch. Pinpoint, diff, and fork the exact step where your agent broke the codebase.</i>
</p>

<p align="center">
  <a href="https://github.com/test-bit-sys/agentbisect/actions"><img src="https://img.shields.io/badge/tests-15%20passed-brightgreen?style=for-the-badge&logo=pytest" alt="Tests"></a>
  <a href="https://github.com/test-bit-sys/agentbisect/stargazers"><img src="https://img.shields.io/github/stars/test-bit-sys/agentbisect?style=for-the-badge&color=yellow" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License"></a>
  <a href="https://pypi.org/project/agentbisect/"><img src="https://img.shields.io/badge/pypi-v0.1.0-blueviolet?style=for-the-badge&logo=pypi" alt="PyPI"></a>
  <a href="#"><img src="https://img.shields.io/badge/MCP-Compatible-orange?style=for-the-badge" alt="MCP Ready"></a>
</p>

---

## 💥 The Problem: "Compounding Agent Drift"

When you ask an autonomous coding agent (**Claude Code**, **Cursor Agent**, **Google Antigravity**, **Devin**, **Cline**, or **Aider**) to implement a multi-file feature or perform a large refactor, it executes **20 to 50 sequential steps** (tool calls, file edits, bash commands).

Inevitably:
1. At **Step 12**, the agent makes a subtle semantic error (e.g., inverts an authorization check or changes a function signature).
2. Steps **13 to 40** turn into **compounding hallucinations**, writing broken patches on top of invalid assumptions.
3. At the end of the session, the test suite is completely broken.

Today, developers face a frustrating dilemma:
- **Guess manually** by reading through a 2,000-line JSON transcript.
- Or run `git checkout .` — **wasting 40,000+ API tokens, $1.50+ in costs, and 30 minutes of waiting.**

```
 Traditional:  [Step 1] ────────────────► [Step 12: BUG] ────────────────► [Step 40: FAIL] ❌
               └─── Wipe whole session (git checkout .)! 40k tokens wasted!

 AgentBisect:  [Step 1] ───► [Step 12: FIRST BAD] ───► [Step 11: FORK HERE] ───► [SUCCESS] ✅
               └─── Bisect isolated Step 12 in 5 test runs! Saved 28k tokens!
```

---

## 🚀 The Solution: `AgentBisect`

`AgentBisect` brings deterministic binary search and time-travel trajectory debugging to AI coding agents:

1. **Non-Polluting Shadow Git Ledger:** Automatically snapshots workspace checkpoints inside `.agentbisect/shadow_git/` without polluting your real `.git` log or creating unwanted branches.
2. **Binary Search Trajectory Engine (`agentbisect find`):** Locates the exact first broken step in $\mathcal{O}(\log_2 N)$ test executions (just 5 test runs for 32 steps).
3. **Workspace & Context Forking (`agentbisect fork <step>`):** Rewinds your filesystem to the last verified good step and synthesizes an intelligent post-mortem prompt (`AGENT_FORK_PROMPT.md`) for the agent to resume without repeating the error.
4. **Self-Healing MCP Server & Skill:** Agents running inside Cursor, Claude Desktop, or Antigravity can invoke `agentbisect_bisect` to autonomously debug and rewind themselves.
5. **Interactive Local Web Dashboard (`agentbisect ui`):** Full-featured dark-mode web dashboard with visual step graphs, side-by-side diffs, and token waste analytics.
6. **Zero-Overhead Portable Evidence Bundles (`agentbisect bundle export/import`):** Package faulty sessions as `.bisect.zip` for instant sharing and post-mortem review.

---

## ⚡ 10-Second Playground Demo

Try `AgentBisect` immediately without configuring any transcript or repo:

```bash
pip install agentbisect
agentbisect demo
```

*(Also supports Node.js microservices via `agentbisect demo --lang node`)*

This launches a pre-packaged simulation of an autonomous agent session, executes binary search live in your terminal, pinpoints the exact line broken at Step 12, and produces an interactive HTML report!

---

## 📦 Installation

Install via pip:

```bash
pip install agentbisect
```

Or install latest from source:

```bash
git clone https://github.com/test-bit-sys/agentbisect.git
cd agentbisect
pip install -e .
```

---

## 🔌 10-Second Setup on ANY Agent

`AgentBisect` can automatically configure itself for your preferred agent with a single command:

```bash
# 🎯 1-Click Auto Configuration:
agentbisect setup --agent cursor --write       # Configures .cursor/mcp.json
agentbisect setup --agent antigravity --write  # Installs skill in .gemini/skills/
agentbisect setup --agent claude --write       # Configures Claude Desktop
agentbisect setup --agent cline --write        # Configures .cline/mcp.json
agentbisect setup --agent windsurf --write     # Configures Windsurf MCP

# Or view snippets for all agents without writing:
agentbisect setup
```

---

## 🛠️ CLI Quick Reference

| Command | Description |
| :--- | :--- |
| `agentbisect setup --agent <name>` | Automatically configure MCP server & skills for any agent |
| `agentbisect find "<test_cmd>"` | Binary search across agent steps to locate regression step |
| `agentbisect fork <step_num>` | Rewind workspace to `<step_num>` and generate `AGENT_FORK_PROMPT.md` |
| `agentbisect ui` | Launch the local web UI dashboard with interactive visual diffs |
| `agentbisect snapshot "<msg>"` | Create an immediate shadow git snapshot of current workspace |
| `agentbisect wrap "<cmd>"` | Execute command transparently and auto-record a shadow step |
| `agentbisect doctor` | Run pre-flight environment, dependency, and permission diagnostics |
| `agentbisect bundle export` | Package current session into a portable `.bisect.zip` bundle |
| `agentbisect bundle import <pkg>`| Import and inspect a `.bisect.zip` evidence bundle |
| `agentbisect mcp` | Launch the stdio Model Context Protocol (MCP) server |

---

## 🤖 MCP Server Setup (Self-Healing Agent)

Enable your agent in **Cursor**, **Claude Desktop**, or **Antigravity** to debug itself:

Add to your MCP configuration (`claude_desktop_config.json` or Cursor Settings):

```json
{
  "mcpServers": {
    "agentbisect": {
      "command": "agentbisect",
      "args": ["mcp"]
    }
  }
}
```

### Available MCP Tools:

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `agentbisect_snapshot` | `summary`, `files?` | Snapshots current workspace to shadow git |
| `agentbisect_bisect` | `test_command`, `timeout_seconds?` | Runs binary search over recorded steps |
| `agentbisect_rewind` | `target_step`, `hint?` | Rewinds workspace and generates recovery prompt |
| `agentbisect_get_diff` | `step_number` | Retrieves unified git diff of any step |
| `agentbisect_status` | *none* | Returns active session metadata and step count |

---

## 📊 Feature Comparison

| Feature | Standard `git bisect` | LLM Tracing (Langfuse/Arize) | **AgentBisect** |
| :--- | :---: | :---: | :---: |
| **Target Unit** | Human git commits | API prompt logs | **Agent trajectory steps** |
| **Workspace Isolation** | ❌ Pollutes user `.git` | ❌ No workspace control | ✅ **Shadow Git (Zero pollution)** |
| **Autonomous Search** | ❌ Manual marking | ❌ No regression search | ✅ **Autonomous $\mathcal{O}(\log_2 N)$ Search** |
| **Context Forking** | ❌ None | ❌ None | ✅ **Workspace Rollback + Guidance Prompt** |
| **Agent Self-Healing (MCP)**| ❌ None | ❌ None | ✅ **Native MCP Server & Skill** |
| **Token Waste Analytics** | ❌ None | ✅ Logs tokens only | ✅ **Calculates compounding waste saved** |

---

## 🤝 Supported Agent Frameworks

- [x] **Google Antigravity & Gemini CLI** (`transcript.jsonl`)
- [x] **Claude Code** (`.claude/` session transcripts)
- [x] **Cursor Agent / Composer**
- [x] **Cline**
- [x] **OpenHands / SWE-bench format**
- [x] **Aider**
- [x] **Generic JSON / JSONL Trajectories**

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
