# AgentBisect — Architecture & Technical Specifications

## 1. Overview
`AgentBisect` is designed from first principles to solve **Compounding Agent Drift** without modifying the user's primary git history.

```
+-------------------------------------------------------------------------------------------------+
|                                     AGENTBISECT ARCHITECTURE                                    |
+-------------------------------------------------------------------------------------------------+
|                                                                                                 |
|   User Project Work Tree (e.g. /my-project/)                                                    |
|   ├── .git/  <--------------------------------- [100% UNTOUCHED! NO POLLUTION]                  |
|   ├── src/                                                                                      |
|   └── .agentbisect/                                                                             |
|       ├── shadow_git/  <----------------------- [Bare Object DB + reflog for steps]             |
|       │   ├── refs/tags/step-1                                                                  |
|       │   ├── refs/tags/step-2                                                                  |
|       │   └── ...                                                                               |
|       ├── current_session.json <--------------- [Step trajectory metadata & token counts]       |
|       └── fork_state.json <-------------------- [Fork context & guidance cache]                |
|                                                                                                 |
+-------------------------------------------------------------------------------------------------+
```

---

## 2. The Shadow Git Ledger (`shadow_ledger.py`)
Traditional version control pollutes `git log` if an agent commits after every single file edit or bash command.

`AgentBisect` decouples the Git Object Database from the work tree:
1. Initializes a bare repository inside `.agentbisect/shadow_git/`.
2. Sets `core.bare = false` inside the shadow configuration.
3. Adds `.agentbisect/` to `info/exclude` to prevent recursive tracking.
4. Executes state mutations using explicit `--git-dir` and `--work-tree` arguments.
5. Tags each step as `step-{k}`, where $k \in [1..N]$.

### Isolation Guarantees:
- **Clean Git Status:** Running `git status` in the user's workspace shows normal working files.
- **Branch Independence:** Switching branches or rebasing in the user's repository does not corrupt the shadow ledger.
- **Zero Remote Leaks:** Shadow commits are never pushed to GitHub or remote origins unless explicitly requested.

---

## 3. The Binary Search Trajectory Engine (`bisect_engine.py`)

### Mathematical Complexity
Let $N$ be the total number of steps in an agent trajectory.
Let $T_{eval}$ be the time required to execute the test command.

The total number of evaluations required to isolate the first broken step is bounded by:

$$\text{Evaluations} \le \lfloor \log_2(N) \rfloor + 2$$

Where $+2$ accounts for the optional boundary verification (testing Step $N$ and Step $1$).

| Trajectory Length ($N$) | Linear Search Runs | AgentBisect Runs | Time Reduction |
| :---: | :---: | :---: | :---: |
| 16 steps | 16 | **4 to 6** | **~70% faster** |
| 32 steps | 32 | **5 to 7** | **~80% faster** |
| 64 steps | 64 | **6 to 8** | **~89% faster** |

---

## 4. Root Cause Correlation (`analyzer.py`)
When a test failure occurs at Step $k$, `AgentBisect` extracts:
1. The standard error (`stderr`) and output (`stdout`) of the test runner.
2. The unified git diff introduced at Step $k$.
3. Matches stack trace frames, function names, and assertion failures against the lines modified in the diff hunks.

---

## 5. Model Context Protocol (MCP) Integration
`AgentBisect` exposes a stdio-based JSON-RPC server implementing the 2024-11-05 MCP specification:
- `agentbisect_snapshot`
- `agentbisect_bisect`
- `agentbisect_rewind`
- `agentbisect_get_diff`
- `agentbisect_status`
