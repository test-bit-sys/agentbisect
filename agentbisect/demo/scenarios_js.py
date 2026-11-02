"""
Built-in realistic Node.js / JavaScript agent failure scenario.
Uses Node's native test runner (node --test) for zero-dependency execution.
"""

from __future__ import annotations

from pathlib import Path
from agentbisect.adapters.live_recorder import LiveRecorder
from agentbisect.core.models import AgentSession


def setup_node_demo_environment(target_dir: Path) -> AgentSession:
    """
    Sets up a realistic JavaScript/Node.js project with 15 agent steps.
    Step 1: Baseline math utility and passing test suite using native `node --test`.
    Steps 2..8: Agent implements math helpers (power, factorial, modulo).
    Step 9: REGRESSION! Agent modifies `divide()` to return NaN or incorrect error code.
    Steps 10..15: Subsequent additions unaware of broken test.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = target_dir / "src"
    test_dir = target_dir / "test"
    src_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    recorder = LiveRecorder(workspace_root=target_dir, session_id="demo_node_service", framework="cursor")

    # Step 1: Package.json and baseline implementation
    package_json = """{
  "name": "math-service",
  "version": "1.0.0",
  "type": "commonjs",
  "scripts": {
    "test": "node --test"
  }
}
"""
    (target_dir / "package.json").write_text(package_json, encoding="utf-8")

    math_js_v1 = """function add(a, b) {
  return a + b;
}

function divide(a, b) {
  if (b === 0) {
    throw new Error("Division by zero");
  }
  return a / b;
}

module.exports = { add, divide };
"""
    (src_dir / "math.js").write_text(math_js_v1, encoding="utf-8")

    test_js = """const test = require('node:test');
const assert = require('node:assert');
const { add, divide } = require('../src/math.js');

test('adds numbers correctly', () => {
  assert.strictEqual(add(2, 3), 5);
});

test('throws on division by zero', () => {
  assert.throws(() => divide(10, 0), /Division by zero/);
});
"""
    (test_dir / "math.test.js").write_text(test_js, encoding="utf-8")

    recorder.record_step(
        tool_name="write_file",
        tool_args={"path": "src/math.js"},
        agent_thought="Initial baseline: Implemented math module with add and divide functions",
        files_affected=["src/math.js", "test/math.test.js", "package.json"],
    )

    # Steps 2 to 8: Math helpers (all passing)
    for i in range(2, 9):
        helper_file = src_dir / f"helper_{i}.js"
        helper_file.write_text(f"// Helper {i}\nmodule.exports = {{ helper_{i}: () => {i} }};\n", encoding="utf-8")
        recorder.record_step(
            tool_name="write_file",
            tool_args={"path": f"src/helper_{i}.js"},
            agent_thought=f"Implemented helper utility #{i}",
            files_affected=[f"src/helper_{i}.js"],
        )

    # Step 9: THE REGRESSION! Agent hallucinates and changes divide() to return null instead of throwing
    buggy_math_js = """function add(a, b) {
  return a + b;
}

function divide(a, b) {
  // BUG INTRODUCED HERE: returns null instead of throwing Error
  if (b === 0) {
    return null;
  }
  return a / b;
}

module.exports = { add, divide };
"""
    (src_dir / "math.js").write_text(buggy_math_js, encoding="utf-8")
    recorder.record_step(
        tool_name="edit_file",
        tool_args={"path": "src/math.js"},
        agent_thought="Refactored divide to handle zero gracefully without exceptions",
        files_affected=["src/math.js"],
    )

    # Steps 10 to 15: Subsequent features
    for i in range(10, 16):
        feature_file = src_dir / f"feature_{i}.js"
        feature_file.write_text(f"module.exports = {{ feat_{i}: () => 'ok' }};\n", encoding="utf-8")
        recorder.record_step(
            tool_name="write_file",
            tool_args={"path": f"src/feature_{i}.js"},
            agent_thought=f"Added extended analytics feature #{i}",
            files_affected=[f"src/feature_{i}.js"],
        )

    return recorder.session
