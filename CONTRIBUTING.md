# Contributing to AgentBisect

Thank you for your interest in contributing to **AgentBisect**! We are building the gold standard for trajectory debugging, regression isolation, and self-healing for autonomous AI coding agents.

This guide outlines our development workflow, architecture guidelines, and step-by-step instructions for extending AgentBisect.

---

## 🏛️ Architectural Principles

1. **Zero Workspace Pollution:** Never pollute the developer's primary git repository. All shadow commits must reside strictly in the isolated `.agentbisect/shadow_git` object store.
2. **Pluggable & Extensible:** Adding a new agent adapter, evaluation strategy, or report format must require writing only a single file without modifying the core engine.
3. **Local-First & Fast:** Every operation should run locally, with zero mandatory external network or telemetry calls.
4. **Deterministic & Resilient:** Heisenbugs, flaky tests, and unexpected process exits must be handled gracefully.

---

## 🚀 Setting Up Local Development

### 1. Clone & Install in Editable Mode
```bash
git clone https://github.com/your-username/agentbisect.git
cd agentbisect
python -m pip install -e ".[dev,mcp]"
```

### 2. Run the Diagnostic Doctor
```bash
agentbisect doctor
```

### 3. Run the Test Suite
```bash
pytest tests/ -v
```

---

## 🔌 How to Add a New Agent Transcript Adapter

AgentBisect uses a dynamic decorator registry (`@register_adapter`). To add support for a new AI agent framework (e.g. `NewAgent`):

1. Create a new file in `agentbisect/adapters/newagent.py`:

```python
from pathlib import Path
from agentbisect.adapters.base import BaseAdapter
from agentbisect.adapters.registry import register_adapter
from agentbisect.core.models import AgentSession, AgentStep, SessionMetadata, StepType

@register_adapter
class NewAgentAdapter(BaseAdapter):
    name = "newagent"

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        """Return True if this file matches the format of your agent."""
        return "newagent" in file_path.name.lower()

    @classmethod
    def parse(cls, file_path: Path, workspace_root: Path) -> AgentSession:
        """Parse your transcript into an AgentSession model."""
        steps = []
        # Parse steps...
        metadata = SessionMetadata(
            session_id=file_path.stem,
            framework="newagent",
            workspace_root=str(workspace_root.resolve()),
            total_steps=len(steps),
        )
        return AgentSession(metadata=metadata, steps=steps)
```

2. Add a unit test in `tests/test_adapters.py` verifying your parser.
3. Import your adapter in `agentbisect/adapters/__init__.py`.

---

## 🧪 How to Add a New Evaluator

Evaluators verify whether a given step in the workspace PASSES or FAILS:

1. Create a class inheriting from `BaseEvaluator` in `agentbisect/evaluators/`:

```python
from pathlib import Path
from agentbisect.evaluators.base import BaseEvaluator
from agentbisect.core.models import BisectStepResult, BisectStatus

class DockerEvaluator(BaseEvaluator):
    name = "docker_evaluator"

    def __init__(self, container_image: str):
        self.container_image = container_image

    def evaluate(self, step_number: int, commit_hash: str, workspace_root: Path) -> BisectStepResult:
        # Run evaluation inside container...
        ...
```

2. Add unit tests in `tests/test_evaluators.py`.

---

## 🎨 Code Style & Quality

We adhere to standard modern Python practices:
- Type annotations across all public APIs (`PEP 561` compliant).
- Use `pydantic` v2 for schemas.
- Format with standard 4-space indentation.
- Document docstrings in Google / Sphinx style.

---

## 📬 Submitting a Pull Request

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/my-new-adapter
   ```
2. Commit your changes with conventional commit messages:
   ```bash
   git commit -m "feat(adapters): add support for Devin trajectory format"
   ```
3. Ensure all tests pass:
   ```bash
   pytest tests/ -v
   ```
4. Push to your fork and submit a Pull Request on GitHub using our PR template.
