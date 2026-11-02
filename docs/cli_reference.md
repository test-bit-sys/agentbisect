# AgentBisect — Command Line Interface (CLI) Reference

## Synopsis
```bash
agentbisect [OPTIONS] COMMAND [ARGS]...
```

---

## Commands

### `agentbisect find`
Performs binary search over the recorded steps to locate the exact step that broke the verification command.

```bash
agentbisect find [OPTIONS] TEST_COMMAND
```

**Options:**
- `-t, --transcript PATH`: Explicit path to transcript file (`.json` or `.jsonl`). Auto-detects if omitted.
- `-w, --workspace PATH`: Root path of the workspace (default: `.`).
- `--timeout SECONDS`: Maximum timeout in seconds per test execution (default: `60`).
- `--html / --no-html`: Whether to generate the interactive HTML report (default: `True`).
- `--open / --no-open`: Automatically open the report in the default browser (default: `False`).

**Examples:**
```bash
agentbisect find "pytest"
agentbisect find "npm test" --open
agentbisect find "cargo test" --timeout 90
```

---

### `agentbisect fork`
Restores the workspace filesystem to a target step and generates a context-aware post-mortem prompt.

```bash
agentbisect fork [OPTIONS] STEP_NUMBER
```

**Options:**
- `-h, --hint TEXT`: Optional guidance text injected into `AGENT_FORK_PROMPT.md`.
- `-w, --workspace PATH`: Workspace directory (default: `.`).

**Examples:**
```bash
agentbisect fork 11
agentbisect fork 14 --hint "Do not alter the JWT secret key logic."
```

---

### `agentbisect wrap`
Transparent execution wrapper. Runs any command or process while recording file modifications as a discrete shadow checkpoint.

```bash
agentbisect wrap [OPTIONS] -- COMMAND...
```

**Examples:**
```bash
agentbisect wrap -- npm run build
agentbisect wrap -- python generate_schema.py
```

---

### `agentbisect ui`
Launches the local interactive Web UI dashboard server.

```bash
agentbisect ui [OPTIONS]
```

**Options:**
- `-p, --port INTEGER`: Port to bind (default: `8765`).
- `--host TEXT`: Host IP (default: `127.0.0.1`).
- `--open / --no-open`: Automatically open browser (default: `True`).

---

### `agentbisect snapshot`
Creates an immediate checkpoint in the shadow git ledger.

```bash
agentbisect snapshot [SUMMARY]
```

---

### `agentbisect demo`
Runs built-in multi-step failure simulations to test and demonstrate `AgentBisect`.

```bash
agentbisect demo [OPTIONS]
```

**Options:**
- `-l, --lang [python|node]`: Language scenario (default: `python`).
- `--open / --no-open`: Open HTML report in browser (default: `False`).

---

### `agentbisect mcp`
Starts the stdio Model Context Protocol (MCP) server for agents to call.

```bash
agentbisect mcp
```

---

### `agentbisect status`
Displays the active session ID, framework, total steps recorded, and storage paths.
