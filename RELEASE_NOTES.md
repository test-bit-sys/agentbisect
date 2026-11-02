# Release Notes — AgentBisect v0.1.0

**AgentBisect: Git Bisect & Time-Travel Debugging for Autonomous AI Coding Agents**

---

## 🌟 Overview

AgentBisect v0.1.0 is the initial production-ready release of the time-travel debugging engine designed specifically for AI coding agents. When an autonomous coding agent (Claude Code, Cursor, Google Antigravity, Devin, Cline, or Aider) drifts off-course during a multi-step session, AgentBisect uses deterministic binary search over an isolated shadow Git ledger to locate the exact step that broke the test suite, rewind the filesystem, and synthesize an intelligent recovery prompt.

---

## 🚀 Key Capabilities

1. **Non-Polluting Shadow Git Ledger**
   - Automatically snapshots workspace checkpoints inside `.agentbisect/shadow_git/` without polluting your real `.git` history or modifying existing branches.
2. **Deterministic $\mathcal{O}(\log_2 N)$ Search (`agentbisect find`)**
   - Pinpoints regression culprits in logarithmic evaluations (e.g. 5 test runs for 32 steps).
3. **Workspace & Context Forking (`agentbisect fork`)**
   - Restores files to the last verified good step and writes `AGENT_FORK_PROMPT.md` explaining the divergence reason so the agent can resume without repeating the error.
4. **Self-Healing MCP Server (`agentbisect mcp`)**
   - Implements the Model Context Protocol (MCP) over standard stdio JSON-RPC 2.0, allowing agents in Cursor, Claude Desktop, and Antigravity to autonomously debug and rewind themselves.
5. **Interactive Local Web Dashboard (`agentbisect ui`)**
   - Full dark-mode web dashboard displaying visual step trajectories, side-by-side git diffs, and token/cost waste analytics.
6. **Hardened Portable Evidence Bundles (`agentbisect bundle export/import`)**
   - Package failed sessions as `.bisect.zip` archives with full cryptographic path traversal validation and transactional extraction.

---

## 🛡️ Reliability & Security Hardening

- **Broken Baseline Safeguard**: The bisect engine strictly validates baseline endpoints and never blames subsequent steps when the test suite was already failing or inconclusive at Step 1.
- **Transactional Bundle Import**: Staged extraction into temporary sandboxes with automatic rollback ensures existing `.agentbisect` data is never corrupted or lost if an archive is corrupted or interrupted.
- **Process Tree Cleanup**: Recursive termination (`taskkill /F /T /PID` on Windows, `os.killpg` process groups on POSIX) prevents hanging test runners or orphaned background workers from leaking file locks.
- **MCP Protocol Spec Compliance**: Conforms strictly to MCP and JSON-RPC 2.0 specifications with silent notification handling, standard `ping` method support, and standard error codes (`-32700`, `-32600`, `-32601`).
- **Scoped Cache & Immutability**: Evaluation memoization is run-bound and returns deep copies to prevent state leakage across different runs or consumer mutation.
- **Defensive Model Metrics**: Resilient parsing of agent transcripts with missing, null, or malformed `token_usage` metrics.
- **UTF-8 Path Handling**: Bare shadow repositories configure `core.quotePath = false` to eliminate Git C-style quoting on filenames with spaces and Unicode characters.

---

## 📦 Installation Instructions

### Standard Installation (PyPI)
```bash
pip install agentbisect
```

### From Source
```bash
git clone https://github.com/test-bit-sys/agentbisect.git
cd agentbisect
pip install -e .
```

### Pre-flight Diagnostic
```bash
agentbisect doctor
```

---

## 💻 Supported Environments

### Supported Python Versions
- **Python 3.10**
- **Python 3.11**
- **Python 3.12** *(Locally verified on 3.12.10)*

### Supported Operating Systems
- **Windows**: Windows 10, Windows 11 *(Locally verified on Windows 11 win32)*
- **Linux**: Ubuntu 20.04+, Debian, Fedora, RHEL *(CI-verified in GitHub Actions)*
- **macOS**: macOS 12 Monterey or newer *(CI-verified in GitHub Actions)*

---

## 🧪 Test Verification Summary

### Locally Verified Results
- **Environment**: Windows 11 (win32), Python 3.12.10
- **Test Runner**: Pytest 8.3.3
- **Test Command**: `python -m pytest`
- **Results**: **69 passed**, 0 failed, 1 warning (`test_bundle_import_rejects_duplicate_entries`) in 324.26s.

### CI-Verified Results (GitHub Actions)
- **Workflow**: `.github/workflows/ci.yml`
- **Last Verified CI Run on `main`**: Run #41498637598 (commit `eead82a`)
- **Matrix Status**: **9 / 9 jobs passed**
  - Ubuntu (Python 3.10, 3.11, 3.12): `success`
  - macOS (Python 3.10, 3.11, 3.12): `success`
  - Windows (Python 3.10, 3.11, 3.12): `success`
- **Pending CI Status**: CI for the adversarial verification branch `verify/adversarial-qa` will execute upon opening a pull request into `main`.

---

## ⚠️ Known Limitations

1. **Windows Restricted Environments**: If `taskkill.exe` execution is prohibited by Windows AppLocker or Group Policy, process tree termination falls back to single-process `proc.kill()`.
2. **Non-Monotonic Inversion Detection**: For trajectories where an agent intermittently introduces and fixes multiple distinct bugs, passing `--verify-monotonicity` (`verify_monotonicity=True`) is recommended for an intermediate sweep.
3. **Symlink Bundles**: Symlinks inside imported ZIP bundles are rejected to prevent host filesystem path traversal.
