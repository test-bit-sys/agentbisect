# Viral X / Twitter Launch Thread

### Tweet 1 (The Hook):
Coding agents have a dirty secret: "Compounding Drift."

Your agent runs 40 steps. At Step 12, it makes a tiny mistake in an auth function. Steps 13–40 are pure hallucinations trying to patch it.

In the end, you run `git checkout .` and waste 45k tokens.

Introducing **AgentBisect**: Git bisect for AI coding agents. ⚡🧵👇

[ATTACH: 45-second high-energy GIF/MP4 of `agentbisect demo` running in terminal, showing the green/red binary search tree and HTML report popup]

---

### Tweet 2 (The Mental Model):
Why can't you just use standard `git bisect`?
Because agents don't make 40 git commits—they make tool calls (`edit_file`, `bash`).

AgentBisect introduces a **Shadow Git Ledger** that snapshots every agent action into an isolated object store without polluting your real `git log` or touching your branches.

---

### Tweet 3 (The Binary Search Magic):
When tests fail at the end of a 40-step session:

Instead of guessing, run:
`agentbisect find "pytest"`

In just $\log_2(40) \approx 5$ runs:
✅ Tests Step 20
✅ Tests Step 10
✅ Tests Step 15
🎯 "Culprit found: Step 12! Inverted comparison in `auth.py`"

---

### Tweet 4 (Forking, Not Restarting):
Don't throw away the whole session!

Run `agentbisect fork 11 --hint "Don't touch expiration logic"`

AgentBisect:
1. Restores the workspace to Step 11
2. Synthesizes an intelligent `AGENT_FORK_PROMPT.md`
3. Tells the agent: "You're resuming from Step 11. Avoid the bug in Step 12."

Saves ~70% of tokens and 20 mins.

---

### Tweet 5 (Self-Healing MCP Server):
The wildest part? Agents can bisect themselves!

AgentBisect ships with a built-in Model Context Protocol (MCP) server. When Claude Code, Cursor Agent, or Antigravity breaks the build, it can invoke:
`agentbisect_bisect` -> rewind itself -> continue autonomously!

---

### Tweet 6 (CTA & Open Source):
AgentBisect is 100% free, local-first, and open source under MIT.

You can try the 10-second live demo right now:
```bash
pip install agentbisect
agentbisect demo
```

⭐ Star the repo on GitHub:
https://github.com/your-username/agentbisect

Retweet the first tweet if you're tired of resetting agent sessions! 🔁
