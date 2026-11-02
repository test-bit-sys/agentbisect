# ⚡ AgentBisect

<p align="center">
  <pre>
   ___                    __   ____  _               __ 
  / _ | ___ ____ ___  ___/ /_ / __ )(_)__ ___  ____/ /_
 / __ |/ _ `/ -_) _ \/ _  // / /_/ / (_-</ -_)/ __/ __/
/_/ |_|\_, /\__/_//_/\_,_/___/_____/_/___/\__/\__/\__/  
      /___/                                             
  </pre>
  <b>Git bisect for AI coding agents.</b><br>
  <i>Stop restarting 40-step agent sessions from scratch. Pinpoint, diff, and fork the exact step where your agent broke the codebase.</i>
</p>

<p align="center">
  <a href="https://github.com/your-username/agentbisect/actions"><img src="https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square" alt="Tests"></a>
  <a href="https://pypi.org/project/agentbisect/"><img src="https://img.shields.io/badge/pypi-v0.1.0-blue?style=flat-square" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/supports-Claude_Code_|_Cursor_|_Antigravity_|_Aider-blueviolet?style=flat-square" alt="Compatible Agents"></a>
</p>

---

## 💥 The Problem: "Compounding Agent Drift"

When you ask an autonomous coding agent (Claude Code, Cursor Agent, Antigravity, Devin, Aider) to implement a feature or refactor a module, it often takes **20 to 50 sequential steps** (tool calls, file edits, bash commands).

Inevitably:
1. At **Step 12**, the agent makes a subtle semantic error (e.g. inverts a condition or changes a function signature).
2. Steps **13 to 40** are spent in **compounding hallucinations**, writing broken patches on top of broken assumptions.
3. At the end of the session, the test suite is completely broken.

Today, developers face a frustrating dilemma:
- **Guess manually** by reading a 2,000-line JSON transcript.
- Or run `git checkout .` — **wasting 40,000+ API tokens, $1.50+, and 30 minutes of time.**

---

## 🚀 The Solution: `AgentBisect`

`AgentBisect` brings the power of **Git Bisect and Time-Travel Trajectory Debugging** to the AI Agent era:

1. **Non-Polluting Shadow Git Ledger:** Automatically tracks workspace checkpoints in `.agentbisect/` without cluttering your real `git log` or touching your branches.
2. **Binary Search Trajectory Engine (`agentbisect find`):** Locates the exact first broken step in $\mathcal{O}(\log_2 N)$ test executions (5 runs for 32 steps).
3. **Workspace & Context Forking (`agentbisect fork <step>`):** Rewinds your filesystem to the last verified good step and synthesizes an intelligent post-mortem prompt (`AGENT_FORK_PROMPT.md`) for the agent to resume with guidance.
4. **Self-Healing MCP Server & Skill:** Agents can bisect themselves via Model Context Protocol tools!
5. **Interactive HTML Dashboard:** Generates a standalone, beautiful HTML timeline report with visual step trees, side-by-side diffs, and token waste calculations.

```
 Traditional:  [Step 1] ────────────────► [Step 12: BUG] ────────────────► [Step 40: FAIL] ❌
               └─── Wipe whole session (git checkout .)! 40k tokens wasted!

 AgentBisect:  [Step 1] ───► [Step 12: FIRST BAD] ───► [Step 11: FORK HERE] ───► [SUCCESS] ✅
               └─── Bisect isolated Step 12 in 5 test runs! Saved 28k tokens!
```

---

## ⚡ 10-Second Playground Demo

Try `AgentBisect` immediately without configuring any transcript or repo:

```bash
pip install agentbisect
agentbisect demo
```

This launches a pre-packaged simulation of a 20-step microservice agent session, runs the binary search live in your terminal, catches the exact line inverted at Step 12, and produces an interactive HTML report!

---

## 📦 Installation

```bash
pip install agentbisect
```

Or install from source:
```bash
git clone https://github.com/your-username/agentbisect.git
cd agentbisect
pip install -e .
```

---

## 🛠️ CLI Usage

### 1. Find the Culprit Step
Run binary search over your agent's session against any test or validation command:

```bash
# Using pytest
agentbisect find "pytest tests/"

# Using npm
agentbisect find "npm test"

# Specify a transcript file explicitly
agentbisect find "pytest" --transcript .claude/session.jsonl
```

### 2. Fork and Rewind
Rewind your workspace to the last good step and generate a post-mortem prompt:

```bash
agentbisect fork 11 --hint "Avoid modifying the token expiration comparison."
```

This creates `AGENT_FORK_PROMPT.md`:
```markdown
# AgentBisect Session Fork Notice
**Action Taken:** Workspace rewound to Step 11.
- At Step 12, 'edit_file(auth.py)' broke the test with:
  AssertionError: Expired token should not verify
- Guidance: Avoid modifying the token expiration comparison.
```

### 3. Real-Time Flight Recorder
Record steps manually or in scripts:

```bash
agentbisect snapshot "Completed database migration"
```

### 4. Inspect Session Status
```bash
agentbisect status
```

---

## 🤖 MCP Server & Self-Healing Agent Skill

`AgentBisect` includes a built-in **Model Context Protocol (MCP)** server, enabling agents in Cursor, Claude Desktop, Antigravity, and Cline to debug themselves.

### Add to your MCP Config (`cursor_mcp.json` / `claude_desktop_config.json`):

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

### Available Tools:
| Tool Name | Description |
| :--- | :--- |
| `agentbisect_snapshot` | Create an instant shadow git checkpoint of current workspace |
| `agentbisect_bisect` | Run automated binary search to find which step broke tests |
| `agentbisect_rewind` | Revert workspace to a known good step and get recovery prompt |
| `agentbisect_get_diff` | View the unified diff of any historical step |
| `agentbisect_status` | Get current session metadata and step count |

---

## 📊 Feature Comparison

| Feature | Standard Git Bisect | LLM Observability (Langfuse/Arize) | **AgentBisect** |
| :--- | :---: | :---: | :---: |
| **Target** | Human git commits | API prompt logs | **Agent trajectory steps** |
| **Workspace Isolation** | ❌ Pollutes user `.git` | ❌ No workspace control | ✅ **Shadow Git (Zero pollution)** |
| **Automated Search** | ✅ Semi-manual | ❌ No regression search | ✅ **Autonomous $\mathcal{O}(\log N)$ Search** |
| **Context Forking** | ❌ None | ❌ None | ✅ **Workspace Rollback + Prompt Injection** |
| **Agent MCP Integration**| ❌ None | ❌ None | ✅ **Built-in MCP Server & Skill** |
| **Token Waste Analytics**| ❌ None | ✅ Logs tokens only | ✅ **Calculates compounding waste saved** |

---

## 🤝 Supported Agent Frameworks
- [x] **Google Antigravity & Gemini CLI** (`transcript.jsonl`)
- [x] **Claude Code** (`.claude/` session transcripts)
- [x] **Cursor Agent / Composer**
- [x] **Aider**
- [x] **OpenHands / SWE-bench format**
- [x] **Generic JSON / JSONL Trajectories**

---

## 🧪 Testing

Run the comprehensive test suite:

```bash
pytest tests/ -v
```

---

## 📄 License
MIT License. See [LICENSE](LICENSE) for details.
