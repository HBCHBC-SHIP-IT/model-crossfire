# AgentRelay

AgentRelay is a small file-queue workbench for coordinating a lead AI agent
with one or more worker agents.

It was originally published as **Model Crossfire**.  The old entry point still
works:

```powershell
python model_crossfire.py doctor
```

The preferred entry point is now:

```powershell
python agent_relay.py doctor
```

## Purpose

AgentRelay helps a strong lead model reduce token usage by delegating scoped
work to cheaper or secondary models:

```text
Lead agent
  -> writes scoped task files
  -> assigns them to worker queues
  -> workers run through CLI tools
  -> workers write durable reports
  -> lead reads reports, reviews, and decides
```

Good worker tasks:

- read-only project reconnaissance;
- test execution and failure summaries;
- first-draft documentation;
- web selector reconnaissance;
- repetitive scoped implementation;
- independent option research.

Worker outputs are not automatically accepted.  A lead/reviewer agent should
review the reports before changes are trusted.

## Why Files Instead Of GUI Automation?

Screen scraping and simulated clicks are brittle:

- focus can move to the wrong window;
- coordinates break when layouts change;
- long outputs are hard to capture;
- autonomous chat loops can run away.

AgentRelay uses files and CLI commands.  One command processes one task, and
all inputs, outputs, and logs remain visible on disk.

## Requirements

- Python 3.10+
- Claude Code CLI available as `claude`
- Codex CLI available as `codex`

Check your environment:

```powershell
python agent_relay.py doctor
```

## Core Commands

Queue a task for a worker:

```powershell
python agent_relay.py queue claude-research --file examples\readonly_status_check.md --title status_check --role "read-only researcher"
```

Run that worker with Claude as the backend:

```powershell
python agent_relay.py run-worker --worker claude-research --backend claude --cwd C:\path\to\project
```

Run a trusted Claude worker with permission bypass:

```powershell
python agent_relay.py run-worker --worker claude-impl --backend claude --cwd C:\path\to\project --permission-mode bypassPermissions --dangerously-skip-permissions
```

Relay a worker report to Codex for review:

```powershell
python agent_relay.py relay-worker --source-worker claude-research --target-worker codex
```

Run Codex as the reviewer:

```powershell
python agent_relay.py run-worker --worker codex --backend codex --cwd C:\path\to\project
```

Show queues, outputs, and worker locks:

```powershell
python agent_relay.py status
```

## Compatibility Commands

The original two-agent commands still work:

```powershell
python agent_relay.py queue claude --file examples\readonly_status_check.md --title status_check
python agent_relay.py run-claude --cwd C:\path\to\project --permission-mode bypassPermissions --dangerously-skip-permissions
python agent_relay.py relay-claude-to-codex
python agent_relay.py run-codex --cwd C:\path\to\project
python agent_relay.py run-cycle --cwd C:\path\to\project --claude-dangerously-skip-permissions
```

The old script name also remains compatible:

```powershell
python model_crossfire.py run-cycle --cwd C:\path\to\project --claude-dangerously-skip-permissions
```

## Multi-Worker Pattern

Independent read-only work can be split across workers:

```text
claude-kimi      -> Kimi web reconnaissance report
claude-doubao    -> Doubao web reconnaissance report
claude-deepseek  -> DeepSeek web reconnaissance report
codex            -> review and choose the safest provider
```

Example:

```powershell
python agent_relay.py queue claude-kimi --file tasks\kimi_recon.md --role "read-only web researcher"
python agent_relay.py queue claude-doubao --file tasks\doubao_recon.md --role "read-only web researcher"
python agent_relay.py queue claude-deepseek --file tasks\deepseek_recon.md --role "read-only web researcher"

python agent_relay.py run-worker --worker claude-kimi --backend claude --cwd C:\path\to\project
python agent_relay.py run-worker --worker claude-doubao --backend claude --cwd C:\path\to\project
python agent_relay.py run-worker --worker claude-deepseek --backend claude --cwd C:\path\to\project
```

Run these in separate terminals only when the tasks are independent and do not
write the same files.

## Safety Model

AgentRelay intentionally does not implement an infinite autonomous loop.

The recommended flow is human-gated:

1. Queue scoped tasks.
2. Run workers.
3. Relay reports to a lead/reviewer.
4. Review outputs.
5. Decide the next step.

Rules for safe use:

- Prefer read-only worker tasks.
- Require reports for every worker task.
- Do not queue secrets, cookies, browser profiles, account data, private
  screenshots, API keys, or tokens.
- Do not let worker outputs merge directly into production work.
- Avoid concurrent workers that edit the same files.

## Discovery & Installation

AgentRelay ships with integrations that make it discoverable by other AI agents.

### Codex Skill

A Codex skill lives at `skills/agent-relay/`. When installed, Codex CLI
automatically activates it for multi-agent collaboration, worker delegation,
and review-flow tasks.

To install the skill manually:

```powershell
# Copy the skill into Codex's skills directory
Copy-Item -Recurse -Force skills\agent-relay `
  "$HOME\.codex\skills\agent-relay"
```

### Codex Plugin

A plugin bundle at `plugins/agent-relay/` packages the skill with a valid
`.codex-plugin/plugin.json` manifest. After cloning this repository, add its
marketplace and install the plugin:

```powershell
codex plugin marketplace add .
codex plugin add agent-relay@agent-relay
```

### Claude Code Integration

`integrations/claude-code/CLAUDE.md` explains how a Claude Code worker reads a
queued task, follows report constraints, and avoids expanding scope. Point
Claude Code at this file when configuring a worker:

```powershell
python agent_relay.py run-worker --worker claude-research `
  --backend claude `
  --cwd C:\path\to\project `
  --add-dir integrations\claude-code
```

### Generic Agent Integration

`integrations/generic-agents/AGENTS.md` provides a concise fragment for agents
without native Skill support. Copy or reference this file in any agent's
context to teach it AgentRelay worker discipline.

## Directory Layout

```text
skills/agent-relay/        # Codex skill (SKILL.md + agents/)
plugins/agent-relay/       # Codex plugin bundle
.agents/plugins/           # Repo marketplace manifest
integrations/              # Agent-specific integration guides
  claude-code/
  generic-agents/
queue/
  to_<worker>/
  processed/
out/
  <worker>/
logs/
locks/
examples/
```

Generated queue, output, log, and lock files are ignored by Git.

## Current Status

Early but usable.  Tested on Windows with Claude Code CLI and Codex CLI.
