# Model Context Protocol (MCP) Setup Guide

This guide explains how to connect `AgentBisect` to your favorite AI coding agent IDE or client.

---

## 1. Claude Desktop
Add `agentbisect` to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "agentbisect": {
      "command": "agentbisect",
      "args": ["mcp"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

## 2. Cursor
1. Open Cursor Settings -> **Features** -> **MCP**.
2. Click **+ Add New MCP Server**.
3. Set:
   - **Name:** `agentbisect`
   - **Type:** `command`
   - **Command:** `agentbisect mcp`

---

## 3. Google Antigravity & Gemini CLI
`AgentBisect` is natively compatible with Antigravity.
Copy the `skills/agentbisect/` directory into your `.gemini/skills/` or active workspace, or install via `plugin.json`:

```bash
agy plugin install ./agentbisect
```

---

## 4. Cline / Roo-Code (VS Code Extension)
In `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "agentbisect": {
      "command": "python",
      "args": ["-m", "agentbisect.mcp.server"],
      "disabled": false,
      "autoApprove": [
        "agentbisect_snapshot",
        "agentbisect_status"
      ]
    }
  }
}
```

---

## 5. Windsurf / Codeium
Add to `~/.codeium/windsurf/mcp_config.json`:

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
